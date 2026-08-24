"""
SQLite-Persistenz für persistentes Cross-Party-Lernen (Geo-Kultur-Spec §7).
=============================================================================

Zwei neue, bewusst schlanke Tabellen (``party_runs`` / ``selection_events``),
gleiche SQLite-Datei wie ``event_theme.py``/``party_context/storage.py``,
gleiches Migrations-Muster (``CREATE TABLE IF NOT EXISTS``).

Scope (Geo-Kultur-Spec §7): Single-Tenant-Lernen über die AUFEINANDER-
FOLGENDEN Partys dieses einen Admins/Deployments hinweg - ``party_runs`` sind
eingefrorene Snapshots abgeschlossener Partys, NIE nachträglich veränderbar.
``selection_events`` sind bewusst anonymisiert (kein guest_name), getrennt von
der operativen ``responses``-Tabelle, die für den Einkauf echte Namen braucht.

Der Party-Lifecycle-Trigger (wann ein ``party_run`` geschrieben wird) lebt
NICHT hier, sondern in ``event_theme.py`` (siehe dortige
``maybe_freeze_and_reset_party()``, Geo-Kultur-Spec §7) - dieses Modul stellt
nur die reinen Persistenz-Bausteine bereit."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from party_context.domain import LearningHistory, PartyRunSnapshot, SelectionEvent


def init_learning_storage(db_path: str | Path) -> None:
    """Legt ``party_runs``/``selection_events`` an, falls nicht vorhanden.
    Idempotent, sicher bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL DEFAULT '',
                occasion_id TEXT NOT NULL DEFAULT '',
                country_code TEXT NOT NULL DEFAULT '',
                season TEXT NOT NULL DEFAULT '',
                temperature_class TEXT NOT NULL DEFAULT '',
                location_type TEXT NOT NULL DEFAULT '',
                group_size_class TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS selection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                party_run_id INTEGER NOT NULL REFERENCES party_runs(id),
                item_id TEXT NOT NULL DEFAULT '',
                item_type TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT 'selected'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_selection_events_party_run_id ON selection_events(party_run_id)"
        )


def save_party_run(db_path: str | Path, snapshot: PartyRunSnapshot) -> int:
    """Speichert einen neuen, eingefrorenen ``PartyRunSnapshot`` (immer INSERT,
    nie UPDATE - Snapshots sind unveränderlich §7). Liefert die vergebene
    ``id`` zurück (wird für ``save_selection_events`` benötigt)."""
    started_at = snapshot.started_at.isoformat() if snapshot.started_at else datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO party_runs
                (started_at, occasion_id, country_code, season, temperature_class, location_type, group_size_class)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                snapshot.occasion_id,
                snapshot.country_code,
                snapshot.season,
                snapshot.temperature_class,
                snapshot.location_type,
                snapshot.group_size_class,
            ),
        )
        return int(cursor.lastrowid)


def save_selection_events(db_path: str | Path, party_run_id: int, events: list[SelectionEvent]) -> None:
    """Speichert die anonymisierten Gast-Auswahlen eines ``party_run_id``.
    No-op bei leerer Liste."""
    if not events:
        return
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO selection_events (party_run_id, item_id, item_type, event_type) VALUES (?, ?, ?, ?)",
            [(party_run_id, e.item_id, e.item_type, e.event_type) for e in events],
        )


def get_learning_history(db_path: str | Path) -> LearningHistory:
    """Liefert die vollständige historische Sicht (alle ``party_runs`` +
    ``selection_events``) für ``compute_learned_preference_score()``. Niemals
    ``None`` - liefert eine leere ``LearningHistory`` (Kaltstart, §7 Pflicht-
    verhalten), falls noch keine Party abgeschlossen wurde."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = conn.execute("SELECT * FROM party_runs").fetchall()
        event_rows = conn.execute("SELECT * FROM selection_events").fetchall()

    runs = []
    for row in run_rows:
        started_at = None
        if row["started_at"]:
            try:
                started_at = datetime.fromisoformat(row["started_at"])
            except ValueError:
                started_at = None
        runs.append(
            PartyRunSnapshot(
                id=row["id"],
                started_at=started_at,
                occasion_id=row["occasion_id"] or "",
                country_code=row["country_code"] or "",
                season=row["season"] or "",
                temperature_class=row["temperature_class"] or "",
                location_type=row["location_type"] or "",
                group_size_class=row["group_size_class"] or "",
            )
        )
    events = [
        SelectionEvent(
            id=row["id"],
            party_run_id=row["party_run_id"],
            item_id=row["item_id"] or "",
            item_type=row["item_type"] or "",
            event_type=row["event_type"] or "selected",
        )
        for row in event_rows
    ]
    return LearningHistory(runs=runs, events=events)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_learning.db"
        init_learning_storage(db_path)
        init_learning_storage(db_path)  # idempotent, darf nicht crashen

        empty_history = get_learning_history(db_path)
        assert empty_history.runs == []
        assert empty_history.events == []

        run1 = PartyRunSnapshot(
            started_at=datetime(2026, 6, 1, 18, 0),
            occasion_id="birthday",
            country_code="IN",
            season="summer",
            temperature_class="warm",
            location_type="garden",
            group_size_class="medium_group",
        )
        run1_id = save_party_run(db_path, run1)
        assert run1_id == 1

        run2 = PartyRunSnapshot(
            started_at=datetime(2026, 7, 1, 18, 0),
            occasion_id="birthday",
            country_code="IN",
            season="summer",
            temperature_class="hot",
            location_type="garden",
            group_size_class="large_group",
        )
        run2_id = save_party_run(db_path, run2)
        assert run2_id == 2

        save_selection_events(
            db_path,
            run1_id,
            [
                SelectionEvent(item_id="chicken_biryani", item_type="recipe"),
                SelectionEvent(item_id="mango_lassi", item_type="direct_consumable"),
            ],
        )
        save_selection_events(db_path, run2_id, [SelectionEvent(item_id="chicken_biryani", item_type="recipe")])
        save_selection_events(db_path, run2_id, [])  # no-op, darf nicht crashen

        history = get_learning_history(db_path)
        assert len(history.runs) == 2
        assert len(history.events) == 3
        assert history.runs[0].country_code == "IN"
        assert history.runs[1].temperature_class == "hot"
        biryani_events = [e for e in history.events if e.item_id == "chicken_biryani"]
        assert len(biryani_events) == 2
        assert {e.party_run_id for e in biryani_events} == {run1_id, run2_id}

        print("party_context/learning_storage.py sanity check OK.")
