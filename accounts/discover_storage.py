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


def init_discover_storage(db_path: str | Path) -> None:
    """Legt ``public_events``/``discover_actions`` an, falls nicht
    vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar."""
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
        published_at=datetime.fromisoformat(row["published_at"]),
    )


def _row_to_discover_action(row: sqlite3.Row) -> DiscoverActionRecord:
    return DiscoverActionRecord(
        id=row["id"],
        user_id=row["user_id"],
        party_id=row["party_id"],
        action=DiscoverAction(row["action"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def publish_party(
    db_path: str | Path,
    party_id: str,
    event_type: str = "",
    interest_tags: list[str] | None = None,
    max_guests: int = 0,
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
            INSERT INTO public_events (id, party_id, event_type, interest_tags, max_guests, published_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(party_id) DO UPDATE SET
                event_type = excluded.event_type,
                interest_tags = excluded.interest_tags,
                max_guests = excluded.max_guests,
                published_at = excluded.published_at
            """,
            (event_id, party_id, event_type, _encode_list(interest_tags or []), max_guests, now),
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
    db_path: str | Path, action_id: str, user_id: str, party_id: str, action: DiscoverAction
) -> DiscoverActionRecord:
    """Erneutes Swipen derselben Party überschreibt die vorherige Aktion
    statt einen zweiten Datensatz anzulegen (UNIQUE(user_id, party_id))."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO discover_actions (id, user_id, party_id, action, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, party_id) DO UPDATE SET
                action = excluded.action, created_at = excluded.created_at
            """,
            (action_id, user_id, party_id, action.value, now),
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


def list_candidate_publications(db_path: str | Path, user_id: str) -> list[tuple[Party, PublicEvent]]:
    """Alle für [user_id] noch swipbaren veröffentlichten Parties - EIN
    Query kodiert drei Hard-Filter gleichzeitig: nicht die eigene Party,
    noch nicht Mitglied (deckt sowohl frühere Discover-Joins als auch
    akzeptierte persönliche Einladungen ab - persönliche Einladungen haben
    dadurch faktisch Vorrang, siehe Spec §58), noch nicht in irgendeine
    Richtung geswiped (auch 'going'/'maybe' - ein bereits akzeptiertes
    Event nochmal anzuzeigen wäre ohnehin nutzlos, da erneutes Beitreten
    nicht möglich ist)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT p.*, pe.id AS public_event_id, pe.event_type AS pe_event_type,
                   pe.interest_tags AS pe_interest_tags, pe.max_guests AS pe_max_guests,
                   pe.published_at AS pe_published_at
            FROM parties p
            JOIN public_events pe ON pe.party_id = p.id
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
            ORDER BY pe.published_at DESC
            """,
            (user_id, user_id, user_id),
        ).fetchall()
    result = []
    for row in rows:
        party = _row_to_party(row)
        publication = PublicEvent(
            id=row["public_event_id"],
            party_id=row["id"],
            event_type=row["pe_event_type"] or "",
            interest_tags=_decode_list(row["pe_interest_tags"] or ""),
            max_guests=row["pe_max_guests"],
            published_at=datetime.fromisoformat(row["pe_published_at"]),
        )
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


def get_discover_deck(db_path: str | Path, user_id: str, limit: int = 30) -> list[tuple[Party, PublicEvent, float]]:
    """Orchestriert Kandidaten-Auswahl + regelbasiertes Ranking (siehe
    ``accounts/discover_ranking.py``) - liefert die Top [limit] Kandidaten."""
    import accounts.discover_ranking as discover_ranking
    import accounts.discovery_storage as discovery_storage

    candidates = list_candidate_publications(db_path, user_id)
    preferences = discovery_storage.get_discovery_preferences(db_path, user_id)
    event_type_interests = {
        p.item_id for p in discovery_storage.get_event_interests(db_path, user_id, category="event_type")
    }
    interest_tag_interests = {
        p.item_id for p in discovery_storage.get_event_interests(db_path, user_id, category="interest_tag")
    }
    ranked = discover_ranking.rank_candidates(candidates, preferences, event_type_interests, interest_tag_interests)
    return ranked[:limit]


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

        print("accounts/discover_storage.py sanity check OK.")
