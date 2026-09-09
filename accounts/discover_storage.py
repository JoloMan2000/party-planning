"""SQLite-Persistenz für das Discover-Events-MVP (Swipe-Deck über bereits
existierende, vom Host veröffentlichte Parties).

Mirrort exakt das etablierte Muster aus ``accounts/discovery_storage.py``:
kurzlebige ``with sqlite3.connect(db_path) as conn:``-Blöcke, ``CREATE
TABLE IF NOT EXISTS``, ein ``init_*(db_path)``, ausführbarer
``__main__``-Selbsttest.

WICHTIG (Scope-Entscheidung, siehe Plan): "Veröffentlicht" wird über die
BLOSSE EXISTENZ einer ``public_events``-Zeile modelliert (nicht über ein
Boolean-Flag auf ``parties``) - Publish = Upsert, Unpublish = DELETE. Das
gibt Discovery-Metadaten (``event_type``/``interest_tags``) ein eigenes,
sauberes Zuhause statt die private Party-Kerntabelle zu verunreinigen."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from accounts.domain import DiscoverAction, DiscoverActionRecord, Party, PublicEvent
from accounts.party_storage import _row_to_party
from geo.distance import bounding_box, haversine_km
from geo.domain import GeoPoint
import accounts.discover_learning as discover_learning
import geo.storage as geo_storage

# Geo Platform (Spec §123-124): erweiterter Radius für als "Major Event"
# markierte Parties, NUR wenn der User zusätzlich
# ``allow_major_events_outside_radius`` gesetzt hat - überschreibt niemals
# stillschweigend den vom User gewählten Standard-Radius.
MAJOR_EVENT_RADIUS_KM = 100.0


def init_discover_storage(db_path: str | Path) -> None:
    """Legt ``public_events``/``discover_actions`` an, falls nicht
    vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar.

    Initialisiert zusätzlich ``geo.storage`` (``party_locations``), da
    ``list_candidate_publications`` seit der Geo Platform hart gegen diese
    Tabelle joint (Spec §123-124) - jeder bestehende Aufrufer von
    ``init_discover_storage`` (Tests inkl.) bekommt die Tabelle damit ohne
    eigene Anpassung. Gleiches Prinzip fürs ``discover_learning``-Modul
    (Discover-Engine-Phase-1): ``get_discover_deck`` schreibt seit Phase 1
    Exposure-Zeilen, jeder bestehende Aufrufer von ``init_discover_storage``
    bekommt diese Tabelle damit ebenfalls ohne eigene Anpassung."""
    geo_storage.init_geo_storage(db_path)
    discover_learning.init_discover_learning_storage(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public_events (
                id TEXT PRIMARY KEY,
                party_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL DEFAULT '',
                interest_tags TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL,
                FOREIGN KEY (party_id) REFERENCES parties(id)
            )
            """
        )
        # Schema-Migration (mirrors party_storage.py::init_party_storage's
        # cover_image-Migration) - max_guests kam nach dem initialen Rollout
        # dazu, damit bereits existierende Dev-DBs nicht brechen.
        existing_public_event_cols = {row[1] for row in conn.execute("PRAGMA table_info(public_events)")}
        public_event_migrations = {
            "max_guests": "ALTER TABLE public_events ADD COLUMN max_guests INTEGER NOT NULL DEFAULT 0",
            "is_major_event": "ALTER TABLE public_events ADD COLUMN is_major_event INTEGER NOT NULL DEFAULT 0",
        }
        for column, ddl in public_event_migrations.items():
            if column not in existing_public_event_cols:
                conn.execute(ddl)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discover_actions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                party_id TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, party_id),
                FOREIGN KEY (party_id) REFERENCES parties(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        # Schema-Migration (Build-Schritt 3, gleiches Muster wie
        # public_events' max_guests/is_major_event oben) - reason kam nach
        # dem initialen Rollout dazu.
        existing_discover_action_cols = {row[1] for row in conn.execute("PRAGMA table_info(discover_actions)")}
        discover_action_migrations = {
            "reason": "ALTER TABLE discover_actions ADD COLUMN reason TEXT NOT NULL DEFAULT ''",
        }
        for column, ddl in discover_action_migrations.items():
            if column not in existing_discover_action_cols:
                conn.execute(ddl)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discover_actions_user ON discover_actions(user_id)")


def _encode_list(values: list[str]) -> str:
    return ",".join(values)


def _decode_list(raw: str) -> list[str]:
    return [v for v in raw.split(",") if v]


def _row_to_public_event(row: sqlite3.Row) -> PublicEvent:
    return PublicEvent(
        id=row["id"],
        party_id=row["party_id"],
        event_type=row["event_type"] or "",
        interest_tags=_decode_list(row["interest_tags"] or ""),
        max_guests=row["max_guests"],
        is_major_event=bool(row["is_major_event"]) if "is_major_event" in row.keys() else False,
        published_at=datetime.fromisoformat(row["published_at"]),
    )


def _row_to_discover_action(row: sqlite3.Row) -> DiscoverActionRecord:
    return DiscoverActionRecord(
        id=row["id"],
        user_id=row["user_id"],
        party_id=row["party_id"],
        action=DiscoverAction(row["action"]),
        reason=(row["reason"] if "reason" in row.keys() else None) or "",
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def publish_party(
    db_path: str | Path,
    party_id: str,
    event_type: str = "",
    interest_tags: list[str] | None = None,
    max_guests: int = 0,
    is_major_event: bool = False,
) -> PublicEvent:
    """Veröffentlicht (oder aktualisiert, falls bereits veröffentlicht) eine
    Party fürs Discover-Deck - Upsert per ``party_id``, damit erneutes
    Publish Tags/Zeitstempel aktualisiert statt einen Duplikat-Datensatz
    anzulegen. ``max_guests=0`` bedeutet unbegrenzt (siehe
    ``list_candidate_publications``/``is_party_full``)."""
    now = datetime.now().isoformat()
    event_id = f"public_event:{party_id}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO public_events (id, party_id, event_type, interest_tags, max_guests, is_major_event, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(party_id) DO UPDATE SET
                event_type = excluded.event_type,
                interest_tags = excluded.interest_tags,
                max_guests = excluded.max_guests,
                is_major_event = excluded.is_major_event,
                published_at = excluded.published_at
            """,
            (event_id, party_id, event_type, _encode_list(interest_tags or []), max_guests, 1 if is_major_event else 0, now),
        )
    result = get_publication(db_path, party_id)
    assert result is not None
    return result


def unpublish_party(db_path: str | Path, party_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM public_events WHERE party_id = ?", (party_id,))


def get_publication(db_path: str | Path, party_id: str) -> PublicEvent | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM public_events WHERE party_id = ?", (party_id,)).fetchone()
    return _row_to_public_event(row) if row is not None else None


def upsert_discover_action(
    db_path: str | Path, action_id: str, user_id: str, party_id: str, action: DiscoverAction, reason: str = ""
) -> DiscoverActionRecord:
    """Erneutes Swipen derselben Party überschreibt die vorherige Aktion
    statt einen zweiten Datensatz anzulegen (UNIQUE(user_id, party_id)).

    ``reason`` (Build-Schritt 3) wird IMMER mitgeschrieben, auch als leerer
    String bei ``GOING``/``MAYBE`` oder einem grundlosen ``NOT_INTERESTED`` -
    die Enum-Gültigkeit ("nur bei NOT_INTERESTED, nur bekannte Werte") wird
    an der API-Grenze geprüft (``backend/app/schemas/discover.py``), nicht
    hier; ein erneutes Swipen ohne Grund überschreibt einen zuvor
    gespeicherten Grund bewusst (der alte Grund gehörte zur alten Aktion)."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO discover_actions (id, user_id, party_id, action, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, party_id) DO UPDATE SET
                action = excluded.action, reason = excluded.reason, created_at = excluded.created_at
            """,
            (action_id, user_id, party_id, action.value, reason, now),
        )
    result = get_discover_action(db_path, user_id, party_id)
    assert result is not None
    return result


def get_discover_action(db_path: str | Path, user_id: str, party_id: str) -> DiscoverActionRecord | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM discover_actions WHERE user_id = ? AND party_id = ?", (user_id, party_id)
        ).fetchone()
    return _row_to_discover_action(row) if row is not None else None


def delete_discover_action(db_path: str | Path, user_id: str, party_id: str) -> None:
    """Löscht den Swipe-Datensatz - Teil des Discover-Undo-Flows
    (``discover.py::undo_discover_action``), damit die Party wieder in
    ``list_candidate_publications`` auftauchen kann (siehe dortige Filter)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM discover_actions WHERE user_id = ? AND party_id = ?",
            (user_id, party_id),
        )


def list_candidate_publications(
    db_path: str | Path,
    user_id: str,
    *,
    user_point: GeoPoint | None = None,
    user_radius_km: float = 25.0,
    allow_major_events_outside_radius: bool = False,
    blocked_organizer_ids: set[str] | None = None,
) -> list[tuple[Party, PublicEvent]]:
    """Alle für [user_id] noch swipbaren veröffentlichten Parties - EIN
    Query kodiert drei Hard-Filter gleichzeitig: nicht die eigene Party,
    noch nicht Mitglied (deckt sowohl frühere Discover-Joins als auch
    akzeptierte persönliche Einladungen ab - persönliche Einladungen haben
    dadurch faktisch Vorrang, siehe Spec §58), noch nicht in irgendeine
    Richtung geswiped (auch 'going'/'maybe' - ein bereits akzeptiertes
    Event nochmal anzuzeigen wäre ohnehin nutzlos, da erneutes Beitreten
    nicht möglich ist).

    Geo Platform (Spec §123-124): ein VIERTER, bewusst BEDINGTER Hard-Filter -
    nur aktiv, wenn ``user_point`` gesetzt ist (User hat Discovery-
    Koordinaten). Fehlen sie, oder fehlt einer Kandidaten-Party die
    strukturierte ``party_locations``-Koordinate, bleibt das Verhalten exakt
    wie zuvor (nur das weiche ``_city_fit``-Signal im Ranking) - siehe Plan,
    Backward-Compat-Regel. ``bounding_box`` ist NUR ein günstiges SQL-
    Prefilter; die tatsächliche Radius-Entscheidung fällt danach in Python
    per ``haversine_km`` (Spec §50).

    Discover-Engine-Phase-1 (Spec §40): ein FÜNFTER Hard-Filter - geblockte
    Organizer (``accounts/discover_learning.py::get_blocked_organizer_ids``)
    werden VOR dem Ranking entfernt, damit ein Block niemals durch
    Diversity/Exploration überschrieben werden kann. Post-Fetch in Python
    gefiltert, analog zum bestehenden Radius-Filter."""
    bbox_clause = ""
    bbox_params: tuple = ()
    if user_point is not None:
        prefilter_radius_km = max(user_radius_km, MAJOR_EVENT_RADIUS_KM if allow_major_events_outside_radius else 0.0)
        lat_min, lat_max, lon_min, lon_max = bounding_box(user_point, prefilter_radius_km)
        bbox_clause = """
              AND (
                  pl.latitude IS NULL OR pl.longitude IS NULL
                  OR (pl.latitude BETWEEN ? AND ? AND pl.longitude BETWEEN ? AND ?)
              )
        """
        bbox_params = (lat_min, lat_max, lon_min, lon_max)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT p.*, pe.id AS public_event_id, pe.event_type AS pe_event_type,
                   pe.interest_tags AS pe_interest_tags, pe.max_guests AS pe_max_guests,
                   pe.is_major_event AS pe_is_major_event, pe.published_at AS pe_published_at,
                   pl.latitude AS pl_latitude, pl.longitude AS pl_longitude
            FROM parties p
            JOIN public_events pe ON pe.party_id = p.id
            LEFT JOIN party_locations pl ON pl.party_id = p.id
            WHERE p.host_user_id != ?
              AND p.id NOT IN (SELECT party_id FROM party_memberships WHERE user_id = ?)
              AND p.id NOT IN (SELECT party_id FROM discover_actions WHERE user_id = ?)
              AND (
                  pe.max_guests = 0
                  OR (
                      SELECT COUNT(*) FROM party_memberships pm
                      WHERE pm.party_id = p.id AND pm.role = 'guest' AND pm.rsvp_status = 'accepted'
                  ) < pe.max_guests
              )
              {bbox_clause}
            ORDER BY pe.published_at DESC
            """,
            (user_id, user_id, user_id, *bbox_params),
        ).fetchall()
    result = []
    for row in rows:
        party = _row_to_party(row)
        if blocked_organizer_ids and party.host_user_id in blocked_organizer_ids:
            continue
        publication = PublicEvent(
            id=row["public_event_id"],
            party_id=row["id"],
            event_type=row["pe_event_type"] or "",
            interest_tags=_decode_list(row["pe_interest_tags"] or ""),
            max_guests=row["pe_max_guests"],
            is_major_event=bool(row["pe_is_major_event"]),
            published_at=datetime.fromisoformat(row["pe_published_at"]),
        )
        if user_point is not None and row["pl_latitude"] is not None and row["pl_longitude"] is not None:
            candidate_point = GeoPoint(latitude=row["pl_latitude"], longitude=row["pl_longitude"])
            effective_radius_km = (
                MAJOR_EVENT_RADIUS_KM
                if publication.is_major_event and allow_major_events_outside_radius
                else user_radius_km
            )
            if haversine_km(user_point, candidate_point) > effective_radius_km:
                continue
        result.append((party, publication))
    return result


def is_party_full(db_path: str | Path, party_id: str) -> bool:
    """Sicherheitsnetz für ``discover.py::act_on_discover_card`` - eine
    Party kann direkt per Action-Endpoint angesprochen werden, auch wenn sie
    zwischenzeitlich aus dem Deck gefiltert wurde (siehe
    ``list_candidate_publications``), z.B. durch eine Race Condition
    zwischen Deck-Abruf und Swipe."""
    publication = get_publication(db_path, party_id)
    if publication is None or publication.max_guests == 0:
        return False
    with sqlite3.connect(db_path) as conn:
        accepted_count = conn.execute(
            "SELECT COUNT(*) FROM party_memberships WHERE party_id = ? AND role = 'guest' AND rsvp_status = 'accepted'",
            (party_id,),
        ).fetchone()[0]
    return accepted_count >= publication.max_guests


def get_discover_deck(
    db_path: str | Path, user_id: str, limit: int = 30
) -> list[tuple[Party, PublicEvent, float, float | None, str]]:
    """Orchestriert Kandidaten-Auswahl + regelbasiertes Ranking (siehe
    ``accounts/discover_ranking.py``) - liefert die Top [limit] Kandidaten
    inkl. ``distance_km`` (``None``, wenn einer Seite Koordinaten fehlen -
    Spec §83, nie eine vorgetäuschte Präzision) und ``why`` (Build-Schritt 7,
    Explainability - siehe ``discover_ranking.explain_candidate``, nie ein
    leerer String).

    Schreibt als Nebeneffekt eine ``EventRecommendationExposure``-Zeile pro
    zurückgegebenem Kandidaten (Discover-Engine-Phase-1, Spec §74-75) - damit
    spätere Learning-Auswertungen "nie gezeigt" von "gezeigt, aber ignoriert"
    unterscheiden können. Reine Protokollierung, beeinflusst das Ranking
    dieses Aufrufs nicht."""
    import accounts.discover_ranking as discover_ranking
    import accounts.discovery_storage as discovery_storage

    preferences = discovery_storage.get_discovery_preferences(db_path, user_id)
    user_point = None
    if preferences is not None and preferences.discovery_lat is not None and preferences.discovery_lon is not None:
        user_point = GeoPoint(latitude=preferences.discovery_lat, longitude=preferences.discovery_lon)

    blocked_organizer_ids = discover_learning.get_blocked_organizer_ids(db_path, user_id)

    candidates = list_candidate_publications(
        db_path,
        user_id,
        user_point=user_point,
        user_radius_km=preferences.discovery_radius_km if preferences is not None else 25.0,
        allow_major_events_outside_radius=(
            preferences.allow_major_events_outside_radius if preferences is not None else False
        ),
        blocked_organizer_ids=blocked_organizer_ids,
    )
    event_type_interests = {
        p.item_id for p in discovery_storage.get_event_interests(db_path, user_id, category="event_type")
    }
    interest_tag_interests = {
        p.item_id for p in discovery_storage.get_event_interests(db_path, user_id, category="interest_tag")
    }
    # Build-Schritt 5 (Blended Ranking): personalized_recommendations_enabled=False
    # ist der explizite Bypass - in diesem Fall bleibt learned_affinities None,
    # identisch zum Cold-Start-Pfad in discover_ranking.py (kein Sonderfall
    # dort noetig, siehe dessen Docstring). Default (kein Preferences-Datensatz)
    # ist EIN (siehe UserDiscoveryPreferences.personalized_recommendations_enabled),
    # daher wird ohne Preferences trotzdem personalisiert.
    learned_affinities = None
    if preferences is None or preferences.personalized_recommendations_enabled:
        learned_affinities = discover_learning.get_learned_affinities_for_user(db_path, user_id)
    ranked = discover_ranking.rank_candidates(
        candidates, preferences, event_type_interests, interest_tag_interests, learned_affinities
    )

    result = []
    # Build-Schritt 6: Diversity + Exploration Post-Pass ersetzt das vormals
    # nackte ranked[:limit] (siehe accounts/discover_ranking.py::apply_diversity_and_exploration).
    top = discover_ranking.apply_diversity_and_exploration(ranked, limit)
    for party, publication, score in top:
        distance_km = None
        if user_point is not None:
            location = geo_storage.get_party_location(db_path, party.id)
            if location is not None and location.point is not None:
                distance_km = round(haversine_km(user_point, location.point), 1)
        why = discover_ranking.explain_candidate(
            party, publication, preferences, event_type_interests, interest_tag_interests, learned_affinities
        )
        result.append((party, publication, score, distance_km, why))

    discover_learning.record_exposures(
        db_path,
        user_id,
        [(party.id, rank) for rank, (party, _publication, _score) in enumerate(top)],
        discover_learning.CURRENT_MODEL_VERSION,
    )
    return result


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_discover_storage.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        init_discover_storage(db_path)
        init_discover_storage(db_path)  # idempotent

        host = user_storage.create_user(db_path, uuid.uuid4().hex, "host@example.com", "hash", "Host")
        guest = user_storage.create_user(db_path, uuid.uuid4().hex, "guest@example.com", "hash", "Guest")

        party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Rooftop Rave", location="Berlin")

        assert get_publication(db_path, party.id) is None
        assert list_candidate_publications(db_path, guest.id) == []

        publication = publish_party(db_path, party.id, event_type="club_event", interest_tags=["techno", "outdoor"])
        assert publication.event_type == "club_event"
        assert publication.interest_tags == ["techno", "outdoor"]

        candidates = list_candidate_publications(db_path, guest.id)
        assert len(candidates) == 1
        assert candidates[0][0].id == party.id

        # Host sieht die eigene Party nicht im eigenen Deck.
        assert list_candidate_publications(db_path, host.id) == []

        # Re-Publish aktualisiert, statt zu duplizieren.
        publish_party(db_path, party.id, event_type="rave", interest_tags=["techno"])
        assert get_publication(db_path, party.id).event_type == "rave"

        # Bereits Mitglied -> verschwindet aus dem Kandidaten-Pool.
        party_storage.upsert_membership(db_path, party.id, guest.id, party_storage.PartyRole.GUEST, party_storage.RsvpStatus.ACCEPTED)
        assert list_candidate_publications(db_path, guest.id) == []

        # Zweite Party: geswiped -> verschwindet ebenfalls.
        party2 = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Beach Party")
        publish_party(db_path, party2.id, event_type="open_air")
        assert len(list_candidate_publications(db_path, guest.id)) == 1
        upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party2.id, DiscoverAction.NOT_INTERESTED)
        assert list_candidate_publications(db_path, guest.id) == []

        # Erneutes Swipen überschreibt, statt zu duplizieren.
        upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party2.id, DiscoverAction.GOING)
        action = get_discover_action(db_path, guest.id, party2.id)
        assert action.action == DiscoverAction.GOING

        unpublish_party(db_path, party.id)
        assert get_publication(db_path, party.id) is None

        # Kapazitätslimit: voll -> raus aus dem Deck, is_party_full stimmt.
        guest2 = user_storage.create_user(db_path, uuid.uuid4().hex, "guest2@example.com", "hash", "Guest2")
        party3 = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Tiny Loft Party")
        publish_party(db_path, party3.id, event_type="house_party", max_guests=1)
        assert is_party_full(db_path, party3.id) is False
        assert any(p.id == party3.id for p, _pe in list_candidate_publications(db_path, guest2.id))
        party_storage.upsert_membership(
            db_path, party3.id, guest.id, party_storage.PartyRole.GUEST, party_storage.RsvpStatus.ACCEPTED
        )
        assert is_party_full(db_path, party3.id) is True
        assert all(p.id != party3.id for p, _pe in list_candidate_publications(db_path, guest2.id))
        # max_guests=0 bleibt unbegrenzt, auch mit Gästen.
        assert is_party_full(db_path, party2.id) is False

        # Undo: Discover-Action löschen -> Party taucht wieder im Deck auf.
        delete_discover_action(db_path, guest.id, party3.id)
        assert get_discover_action(db_path, guest.id, party3.id) is None

        # reason (Build-Schritt 3): optional mitgeschrieben, per Default leer.
        assert action.reason == ""
        upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party3.id, DiscoverAction.NOT_INTERESTED, reason="too_far")
        with_reason = get_discover_action(db_path, guest.id, party3.id)
        assert with_reason.reason == "too_far"
        # Erneutes Swipen ohne reason ueberschreibt den alten Grund (leer statt "too_far").
        upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party3.id, DiscoverAction.GOING)
        assert get_discover_action(db_path, guest.id, party3.id).reason == ""

        # Geblockter Organizer -> dessen Parties verschwinden hart aus dem Pool.
        import accounts.discover_learning as discover_learning

        party4 = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Warehouse Rave")
        publish_party(db_path, party4.id, event_type="rave")
        assert any(p.id == party4.id for p, _pe in list_candidate_publications(db_path, guest.id))
        discover_learning.block_organizer(db_path, guest.id, host.id)
        candidates_after_block = list_candidate_publications(
            db_path, guest.id, blocked_organizer_ids=discover_learning.get_blocked_organizer_ids(db_path, guest.id)
        )
        assert all(p.host_user_id != host.id for p, _pe in candidates_after_block)
        discover_learning.unblock_organizer(db_path, guest.id, host.id)

        print("accounts/discover_storage.py sanity check OK.")
