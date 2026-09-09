"""SQLite-Persistenz für den Learning-Layer des Discover-Decks (Discover
Engine Phase 1 - siehe ``discover_nearby_event_engine_full_spec.txt`` §25-41,
§74-75).

Mirrort exakt das etablierte Muster aus ``accounts/discover_storage.py``:
kurzlebige ``with sqlite3.connect(db_path) as conn:``-Blöcke, ``CREATE
TABLE IF NOT EXISTS``, ein ``init_*(db_path)``, ausführbarer
``__main__``-Selbsttest.

WICHTIG (Architektur-Entscheidung, siehe Plan): dieser Layer ist bewusst
GETRENNT von ``accounts/discovery_storage.py`` (explizite User-Preferences) -
gelernte Affinitäten dürfen explizite Preferences nie überschreiben, nur
ergänzen (Bayesian-Shrinkage-Blend in ``accounts/discover_ranking.py``).
``accounts/discover_ranking.py`` bleibt storage-frei; jede Persistenz für den
Learning-Layer lebt ausschließlich hier.

Phase-1-Build-Reihenfolge (siehe Plan): Exposure-Tracking (Schritt 1) und
Blocked Organizers (Schritt 2) sind verhaltensneutral bzw. reine Hard-Filter.
Build-Schritt 4 ergänzt den Learned-Affinity-Schreibpfad
(``apply_signal``/``record_signal_from_action``) - dieser Schritt schreibt
NUR, er wird von ``discover_ranking.py`` noch nicht gelesen (Build-Schritt 5,
Blended Ranking)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from accounts.domain import (
    BlockedOrganizer,
    DiscoverAction,
    DiscoverNotInterestedReason,
    EventRecommendationExposure,
    LearnedAffinitySignal,
    PublicEvent,
)

# Versionskennung fürs aktuell aktive Ranking-Modell - wird auf jeder
# Exposure-Zeile mitgespeichert, damit spätere Auswertungen/Modellwechsel
# Exposures verschiedener Ranking-Generationen sauber trennen können.
CURRENT_MODEL_VERSION = "phase1-rule-based-v1"

# Gleiche Neutral-Konstante wie discover_ranking.py::_NEUTRAL - hier
# bewusst dupliziert statt importiert, da discover_ranking.py storage-frei
# bleiben MUSS (siehe dessen Moduldoku) und dieses Modul umgekehrt keine
# Ranking-Logik importieren soll (reine Persistenz-Schicht).
_NEUTRAL_FIT = 0.5

# Halbwertszeit für die Alters-Abschwächung gelernter Affinitäten (Tage) -
# siehe ``get_learned_affinity``. Nach ``AFFINITY_HALF_LIFE_DAYS`` Tagen ohne
# neue Beobachtung ist die Auslenkung vom Neutralwert nur noch halb so groß.
AFFINITY_HALF_LIFE_DAYS = 30.0


def init_discover_learning_storage(db_path: str | Path) -> None:
    """Legt ``event_recommendation_exposures``/``blocked_organizers`` an,
    falls nicht vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar
    (siehe ``backend/app/main.py::on_startup``, direkt neben
    ``discover_storage.init_discover_storage``)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_recommendation_exposures (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                party_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                model_version TEXT NOT NULL,
                shown_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (party_id) REFERENCES parties(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exposures_user ON event_recommendation_exposures(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exposures_user_party "
            "ON event_recommendation_exposures(user_id, party_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_organizers (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                organizer_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, organizer_user_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (organizer_user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_blocked_organizers_user ON blocked_organizers(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_affinity_signals (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                attribute_category TEXT NOT NULL,
                attribute_value TEXT NOT NULL,
                value REAL NOT NULL,
                observation_count REAL NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, attribute_category, attribute_value),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_learned_affinity_user ON learned_affinity_signals(user_id)"
        )


def _row_to_exposure(row: sqlite3.Row) -> EventRecommendationExposure:
    return EventRecommendationExposure(
        id=row["id"],
        user_id=row["user_id"],
        party_id=row["party_id"],
        rank=row["rank"],
        model_version=row["model_version"],
        shown_at=datetime.fromisoformat(row["shown_at"]),
    )


def record_exposures(
    db_path: str | Path,
    user_id: str,
    party_ids_by_rank: list[tuple[str, int]],
    model_version: str = CURRENT_MODEL_VERSION,
) -> None:
    """Schreibt einen Exposure-Datensatz pro (party_id, rank) - EIN Aufruf
    pro Deck-Abruf (siehe ``discover_storage.get_discover_deck``). Bewusst
    ein reiner Batch-Insert ohne Dedup: jeder Deck-Abruf ist ein eigenes
    Exposure-Ereignis, auch für dieselbe Party."""
    if not party_ids_by_rank:
        return
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO event_recommendation_exposures
                (id, user_id, party_id, rank, model_version, shown_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (uuid.uuid4().hex, user_id, party_id, rank, model_version, now)
                for party_id, rank in party_ids_by_rank
            ],
        )


def list_exposures_for_user(
    db_path: str | Path, user_id: str, party_id: str | None = None
) -> list[EventRecommendationExposure]:
    """Test-/Debug-Helfer - liest alle Exposure-Zeilen für einen User
    (optional gefiltert auf eine Party), neueste zuerst."""
    query = "SELECT * FROM event_recommendation_exposures WHERE user_id = ?"
    params: tuple = (user_id,)
    if party_id is not None:
        query += " AND party_id = ?"
        params = (user_id, party_id)
    query += " ORDER BY shown_at DESC"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [_row_to_exposure(row) for row in rows]


def _row_to_blocked_organizer(row: sqlite3.Row) -> BlockedOrganizer:
    return BlockedOrganizer(
        id=row["id"],
        user_id=row["user_id"],
        organizer_user_id=row["organizer_user_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def block_organizer(db_path: str | Path, user_id: str, organizer_user_id: str) -> BlockedOrganizer:
    """Blockiert einen Organizer hart (Spec §40) - idempotent per
    ``UNIQUE(user_id, organizer_user_id)``: ein erneuter Block-Aufruf gibt
    einfach die bestehende Zeile zurück, statt zu duplizieren oder zu
    crashen."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM blocked_organizers WHERE user_id = ? AND organizer_user_id = ?",
            (user_id, organizer_user_id),
        ).fetchone()
        if existing is not None:
            return _row_to_blocked_organizer(existing)

        row_id = uuid.uuid4().hex
        now = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO blocked_organizers (id, user_id, organizer_user_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (row_id, user_id, organizer_user_id, now),
        )
        row = conn.execute(
            "SELECT * FROM blocked_organizers WHERE id = ?", (row_id,)
        ).fetchone()
    return _row_to_blocked_organizer(row)


def unblock_organizer(db_path: str | Path, user_id: str, organizer_user_id: str) -> None:
    """Entfernt einen Organizer-Block. No-Op, falls keine Zeile existiert."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM blocked_organizers WHERE user_id = ? AND organizer_user_id = ?",
            (user_id, organizer_user_id),
        )


def get_blocked_organizer_ids(db_path: str | Path, user_id: str) -> set[str]:
    """Liefert die Menge geblockter Organizer-User-IDs für einen User - vom
    Deck-Aufbau (``discover_storage.list_candidate_publications``) VOR dem
    Ranking als Hard-Filter angewendet, damit ein Block niemals durch
    Diversity/Exploration überschrieben werden kann."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT organizer_user_id FROM blocked_organizers WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {row[0] for row in rows}


def _row_to_affinity_signal(row: sqlite3.Row) -> LearnedAffinitySignal:
    return LearnedAffinitySignal(
        id=row["id"],
        user_id=row["user_id"],
        attribute_category=row["attribute_category"],
        attribute_value=row["attribute_value"],
        value=row["value"],
        observation_count=row["observation_count"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def apply_signal(
    db_path: str | Path,
    user_id: str,
    attribute_category: str,
    attribute_value: str,
    target_fit: float,
    weight: float = 1.0,
) -> LearnedAffinitySignal:
    """Verrechnet EINE Beobachtung in den laufenden gewichteten Mittelwert
    für (``user_id``, ``attribute_category``, ``attribute_value``) -
    idempotent-per-Konstruktion (kein Duplicate-Risiko: jeder Aufruf blendet
    additiv in denselben Datensatz ein, mirrort damit konzeptionell
    ``block_organizer``'s Upsert-Form, nur mit einer Blend-Formel statt
    SELECT-then-return-existing).

    Bewusst OHNE Decay hier - der gespeicherte ``value`` ist der rohe,
    undecayed laufende Mittelwert; die Alters-Abschwächung passiert
    ausschließlich lesend in ``get_learned_affinity`` (siehe dortige Doku
    und ``LearnedAffinitySignal``-Docstring). Bekannte Vereinfachung für
    Phase 1: der laufende Mittelwert selbst gewichtet alte und neue
    Beobachtungen gleich (kein Recency-Bias im Online-Average) - nur der
    RANKING-seitige Lesezugriff bevorzugt aktuelle Signale."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM learned_affinity_signals WHERE user_id = ? AND attribute_category = ? AND attribute_value = ?",
            (user_id, attribute_category, attribute_value),
        ).fetchone()

        if existing is None:
            row_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO learned_affinity_signals
                    (id, user_id, attribute_category, attribute_value, value, observation_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, user_id, attribute_category, attribute_value, target_fit, weight, now),
            )
        else:
            row_id = existing["id"]
            old_count = existing["observation_count"]
            new_count = old_count + weight
            new_value = (existing["value"] * old_count + target_fit * weight) / new_count
            conn.execute(
                "UPDATE learned_affinity_signals SET value = ?, observation_count = ?, updated_at = ? WHERE id = ?",
                (new_value, new_count, now, row_id),
            )
        row = conn.execute("SELECT * FROM learned_affinity_signals WHERE id = ?", (row_id,)).fetchone()
    return _row_to_affinity_signal(row)


def get_learned_affinity(
    db_path: str | Path, user_id: str, attribute_category: str, attribute_value: str, now: datetime | None = None
) -> tuple[float, float] | None:
    """Liefert ``(decayed_fit, observation_count)`` oder ``None``, wenn noch
    keine Beobachtung existiert (Cold-Start - Aufrufer in
    ``discover_ranking.py`` fällt dann auf den expliziten Fit zurück, siehe
    Build-Schritt 5). Decay zieht die Auslenkung vom Neutralwert
    (``_NEUTRAL_FIT``) exponentiell zurück, NICHT den Wert selbst gegen 0 -
    ein alter starker POSITIV-Wert verblasst zu neutral, nicht zu
    negativ, wenn er lange nicht mehr bestätigt wurde."""
    now = now or datetime.now(timezone.utc)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM learned_affinity_signals WHERE user_id = ? AND attribute_category = ? AND attribute_value = ?",
            (user_id, attribute_category, attribute_value),
        ).fetchone()
    if row is None:
        return None
    signal = _row_to_affinity_signal(row)
    updated_at = signal.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - updated_at).total_seconds() / 86400)
    decay_factor = 0.5 ** (age_days / AFFINITY_HALF_LIFE_DAYS)
    decayed_fit = _NEUTRAL_FIT + (signal.value - _NEUTRAL_FIT) * decay_factor
    return decayed_fit, signal.observation_count


def get_learned_affinities_for_user(
    db_path: str | Path, user_id: str, now: datetime | None = None
) -> dict[tuple[str, str], tuple[float, float]]:
    """Bulk-Variante von ``get_learned_affinity`` - EIN Query statt N
    Einzel-Queries pro Kandidat beim Ranking (siehe
    ``discover_storage.get_discover_deck``, das dies einmal pro Deck-Abruf
    aufruft und das Ergebnis an ``discover_ranking.rank_candidates``
    weiterreicht). Key ist ``(attribute_category, attribute_value)``, Value
    ist bereits decayed (gleiche Formel wie ``get_learned_affinity``)."""
    now = now or datetime.now(timezone.utc)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM learned_affinity_signals WHERE user_id = ?", (user_id,)
        ).fetchall()
    result: dict[tuple[str, str], tuple[float, float]] = {}
    for row in rows:
        signal = _row_to_affinity_signal(row)
        updated_at = signal.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - updated_at).total_seconds() / 86400)
        decay_factor = 0.5 ** (age_days / AFFINITY_HALF_LIFE_DAYS)
        decayed_fit = _NEUTRAL_FIT + (signal.value - _NEUTRAL_FIT) * decay_factor
        result[(signal.attribute_category, signal.attribute_value)] = (decayed_fit, signal.observation_count)
    return result


# Attribut-Routing pro (action, reason) - siehe record_signal_from_action.
# NOT_INTERESTED mit einem Grund, der nichts über die Event-ATTRIBUTE
# aussagt (Distanz/Timing/Organizer), erzeugt bewusst KEIN Signal für
# event_type/interest_tag - diese Ablehnungsgründe sagen nichts darüber aus,
# ob der User Techno/Club-Events grundsätzlich mag (siehe
# DiscoverNotInterestedReason-Docstring in accounts/domain.py).
_NOT_INTERESTED_ATTRIBUTE_SIGNAL = {
    "": (0.3, 0.5),  # kein Grund angegeben - schwaches, unsicheres Signal
    DiscoverNotInterestedReason.WRONG_VIBE.value: (0.1, 1.0),  # eindeutig, starkes Signal
}


def record_signal_from_action(
    db_path: str | Path, user_id: str, publication: PublicEvent, action: DiscoverAction, reason: str = ""
) -> list[LearnedAffinitySignal]:
    """Attribut-Routing-Funktion: leitet EINE Swipe-Aktion auf 0..N
    ``apply_signal``-Aufrufe um (ein Aufruf pro gesetztem ``event_type`` +
    einer pro ``interest_tag``). Wird vom Discover-Action-Router direkt nach
    ``discover_storage.upsert_discover_action`` aufgerufen (siehe
    ``backend/app/routers/discover.py::act_on_discover_card``) - reiner
    Schreibpfad, ``discover_ranking.py`` konsumiert diese Signale noch
    nicht (Build-Schritt 5)."""
    if action == DiscoverAction.GOING:
        target_fit, weight = 1.0, 1.0
    elif action == DiscoverAction.MAYBE:
        target_fit, weight = 0.7, 0.6
    else:
        signal_params = _NOT_INTERESTED_ATTRIBUTE_SIGNAL.get(reason)
        if signal_params is None:
            return []  # Grund sagt nichts über die Attribute aus - kein Signal.
        target_fit, weight = signal_params

    attributes: list[tuple[str, str]] = []
    if publication.event_type:
        attributes.append(("event_type", publication.event_type))
    attributes.extend(("interest_tag", tag) for tag in publication.interest_tags)

    return [
        apply_signal(db_path, user_id, category, value, target_fit, weight) for category, value in attributes
    ]


def reset_learned_profile(db_path: str | Path, user_id: str) -> None:
    """Build-Schritt 8: löscht ALLE ``learned_affinity_signals``-Zeilen
    eines Users - der User bekommt danach wieder ein reines
    Cold-Start-Ranking (nur explizite Preferences, siehe
    ``accounts/discover_ranking.py::_blend_learned``'s ``learned=None``-Pfad).

    Bewusst NUR ``learned_affinity_signals`` - ``blocked_organizers``
    (siehe deren Docstring in ``accounts/domain.py``: "übersteht deshalb
    auch ein reset-learning") und ``event_recommendation_exposures`` (reines
    Audit-Log, keine Präferenz) sind explizite Entscheidungen bzw.
    Protokoll-Daten, kein gelerntes Verhalten, und bleiben unangetastet."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM learned_affinity_signals WHERE user_id = ?", (user_id,))


if __name__ == "__main__":
    import tempfile

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_discover_learning.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        init_discover_learning_storage(db_path)
        init_discover_learning_storage(db_path)  # idempotent

        host = user_storage.create_user(db_path, uuid.uuid4().hex, "host@example.com", "hash", "Host")
        guest = user_storage.create_user(db_path, uuid.uuid4().hex, "guest@example.com", "hash", "Guest")
        party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Rooftop Rave", location="Berlin")

        assert list_exposures_for_user(db_path, guest.id) == []

        record_exposures(db_path, guest.id, [(party.id, 0)])
        exposures = list_exposures_for_user(db_path, guest.id)
        assert len(exposures) == 1
        assert exposures[0].party_id == party.id
        assert exposures[0].rank == 0
        assert exposures[0].model_version == CURRENT_MODEL_VERSION

        # Zweiter Deck-Abruf derselben Party -> zweite, unabhängige Zeile
        # (kein Dedup - jede Exposure ist ein eigenes Ereignis).
        record_exposures(db_path, guest.id, [(party.id, 2)])
        assert len(list_exposures_for_user(db_path, guest.id)) == 2

        # Leere Liste -> No-Op, kein Crash.
        record_exposures(db_path, guest.id, [])
        assert len(list_exposures_for_user(db_path, guest.id)) == 2

        assert get_blocked_organizer_ids(db_path, guest.id) == set()

        blocked = block_organizer(db_path, guest.id, host.id)
        assert blocked.user_id == guest.id
        assert blocked.organizer_user_id == host.id
        assert get_blocked_organizer_ids(db_path, guest.id) == {host.id}

        # Erneuter Block derselben (user, organizer)-Kombination -> idempotent.
        blocked_again = block_organizer(db_path, guest.id, host.id)
        assert blocked_again.id == blocked.id
        assert get_blocked_organizer_ids(db_path, guest.id) == {host.id}

        unblock_organizer(db_path, guest.id, host.id)
        assert get_blocked_organizer_ids(db_path, guest.id) == set()

        # Unblock ohne bestehenden Eintrag -> No-Op, kein Crash.
        unblock_organizer(db_path, guest.id, host.id)

        # Learned Affinity (Build-Schritt 4): Cold-Start -> None.
        assert get_learned_affinity(db_path, guest.id, "event_type", "club_event") is None

        publication = PublicEvent(
            id="pe-1", party_id=party.id, event_type="club_event", interest_tags=["techno", "outdoor"]
        )
        record_signal_from_action(db_path, guest.id, publication, DiscoverAction.GOING)
        fit, count = get_learned_affinity(db_path, guest.id, "event_type", "club_event")
        assert abs(fit - 1.0) < 0.001
        assert count == 1.0
        tag_fit, tag_count = get_learned_affinity(db_path, guest.id, "interest_tag", "techno")
        assert abs(tag_fit - 1.0) < 0.001
        assert tag_count == 1.0

        # Zweite Beobachtung (MAYBE) -> laufender gewichteter Mittelwert bewegt sich, crasht nicht.
        record_signal_from_action(db_path, guest.id, publication, DiscoverAction.MAYBE)
        fit_after_maybe, count_after_maybe = get_learned_affinity(db_path, guest.id, "event_type", "club_event")
        assert 0.7 < fit_after_maybe < 1.0
        assert count_after_maybe == 1.6

        # NOT_INTERESTED mit reason="wrong_vibe" -> starkes negatives Signal.
        vibe_publication = PublicEvent(id="pe-2", party_id=party.id, event_type="cultural_event", interest_tags=[])
        record_signal_from_action(
            db_path, guest.id, vibe_publication, DiscoverAction.NOT_INTERESTED,
            reason=DiscoverNotInterestedReason.WRONG_VIBE.value,
        )
        cultural_fit, _ = get_learned_affinity(db_path, guest.id, "event_type", "cultural_event")
        assert abs(cultural_fit - 0.1) < 0.001  # praktisch kein Decay bei Alter ~0

        # NOT_INTERESTED mit reason="too_far" -> KEIN Signal (Grund sagt nichts ueber Attribute aus).
        far_publication = PublicEvent(id="pe-3", party_id=party.id, event_type="house_party", interest_tags=[])
        signals = record_signal_from_action(
            db_path, guest.id, far_publication, DiscoverAction.NOT_INTERESTED,
            reason=DiscoverNotInterestedReason.TOO_FAR.value,
        )
        assert signals == []
        assert get_learned_affinity(db_path, guest.id, "event_type", "house_party") is None

        # Decay: kuenstlich gealtertes Signal naehert sich dem Neutralwert.
        from datetime import timedelta

        far_future = datetime.now(timezone.utc) + timedelta(days=AFFINITY_HALF_LIFE_DAYS)
        decayed_fit, decayed_count = get_learned_affinity(
            db_path, guest.id, "event_type", "cultural_event", now=far_future
        )
        assert abs(decayed_fit - ((_NEUTRAL_FIT + 0.1) / 2)) < 0.01  # nach einer Halbwertszeit: halbe Auslenkung
        assert decayed_count == 1.0  # observation_count decayed nicht

        # Bulk-Fetch liefert dieselben (decayed) Werte wie die Einzel-Variante
        # (minimale Abweichung durch leicht unterschiedliches "now" toleriert).
        current_tag_fit, _ = get_learned_affinity(db_path, guest.id, "interest_tag", "techno")
        bulk = get_learned_affinities_for_user(db_path, guest.id)
        assert abs(bulk[("event_type", "club_event")][0] - fit_after_maybe) < 0.001
        assert abs(bulk[("interest_tag", "techno")][0] - current_tag_fit) < 0.001
        assert ("event_type", "house_party") not in bulk

        # reset_learned_profile (Build-Schritt 8): loescht nur Learned
        # Affinity, laesst Blocked Organizers unangetastet.
        block_organizer(db_path, guest.id, host.id)  # erneut blocken, um Ueberleben zu pruefen
        reset_learned_profile(db_path, guest.id)
        assert get_learned_affinities_for_user(db_path, guest.id) == {}
        assert get_learned_affinity(db_path, guest.id, "event_type", "club_event") is None
        assert get_blocked_organizer_ids(db_path, guest.id) == {host.id}  # unveraendert

        print("accounts/discover_learning.py sanity check OK.")
