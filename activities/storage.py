"""SQLite-Persistenz für ``Activity``/``ActivityVote`` (Equipment Engine
Phase 4, "Real Activities Domain + Guest Voting"). Mirrort
``organizers/storage.py``'s Muster exakt: per-Funktion eigene Connection,
``CREATE TABLE IF NOT EXISTS``, ``TEXT PRIMARY KEY``, ein Index pro Hot-
Lookup-Spalte, plain ``FOREIGN KEY`` ohne ``ON DELETE`` (FK-Enforcement ist
app-weit AUS, ``PRAGMA foreign_keys`` wird nie gesetzt - Kaskaden-Löschungen
passieren explizit in Anwendungscode, siehe ``delete_activity`` unten).

Zeitstempel als naives ``datetime.now().isoformat()`` (kein ``timezone.utc``)
- mirrort ``organizers/storage.py`` und ist der häufigere Stil in dieser
Codebase. Die Dataclass-Feld-Defaults in ``activities/domain.py`` bleiben
trotzdem UTC-aware - dieselbe kosmetische Inkonsistenz wie zwischen
``organizers/domain.py`` und ``organizers/storage.py``."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from activities.domain import Activity, ActivityVote


def init_activities_storage(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                party_id TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                station_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (party_id) REFERENCES parties(id),
                FOREIGN KEY (created_by_user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_party ON activities(party_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_votes (
                id TEXT PRIMARY KEY,
                activity_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(activity_id, user_id),
                FOREIGN KEY (activity_id) REFERENCES activities(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_votes_activity ON activity_votes(activity_id)")
        # Hot Path für list_voted_activity_ids_for_user (einmal pro
        # anfragendem Gast bei jedem GET .../activities).
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_votes_user ON activity_votes(user_id)")


def _row_to_activity(row: sqlite3.Row) -> Activity:
    return Activity(
        id=row["id"],
        party_id=row["party_id"],
        created_by_user_id=row["created_by_user_id"],
        name=row["name"],
        station_id=row["station_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_vote(row: sqlite3.Row) -> ActivityVote:
    return ActivityVote(
        id=row["id"],
        activity_id=row["activity_id"],
        user_id=row["user_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_activity(
    db_path: str | Path,
    activity_id: str,
    party_id: str,
    created_by_user_id: str,
    name: str,
    *,
    station_id: str | None = None,
) -> Activity:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO activities (id, party_id, created_by_user_id, name, station_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (activity_id, party_id, created_by_user_id, name, station_id, now),
        )
    return Activity(
        id=activity_id, party_id=party_id, created_by_user_id=created_by_user_id, name=name,
        station_id=station_id, created_at=datetime.fromisoformat(now),
    )


def get_activity(db_path: str | Path, activity_id: str) -> Activity | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    return _row_to_activity(row) if row is not None else None


def list_activities_for_party(db_path: str | Path, party_id: str) -> list[Activity]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM activities WHERE party_id = ? ORDER BY created_at", (party_id,)
        ).fetchall()
    return [_row_to_activity(r) for r in rows]


def delete_activity(db_path: str | Path, activity_id: str) -> None:
    """Idempotent (No-Op, falls unbekannt). Löscht zuerst die abhängigen
    ``activity_votes``-Zeilen, DANN die ``activities``-Zeile selbst - FK-
    Enforcement ist app-weit AUS (siehe Moduldocstring), Kinder-vor-Eltern
    ist reine Anwendungscode-Disziplin."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM activity_votes WHERE activity_id = ?", (activity_id,))
        conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))


def cast_vote(db_path: str | Path, vote_id: str, activity_id: str, user_id: str) -> ActivityVote:
    """Idempotent (SELECT-then-return-existing, mirrort
    ``social/follows.py::follow_organizer`` exakt). Ein erneuter Vote
    desselben Users für dieselbe Activity gibt die bestehende Zeile
    unverändert zurück - kein Duplikat, keine neue ``created_at``."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM activity_votes WHERE activity_id = ? AND user_id = ?", (activity_id, user_id)
        ).fetchone()
        if existing is not None:
            return _row_to_vote(existing)
        conn.execute(
            "INSERT INTO activity_votes (id, activity_id, user_id, created_at) VALUES (?, ?, ?, ?)",
            (vote_id, activity_id, user_id, now),
        )
        row = conn.execute("SELECT * FROM activity_votes WHERE id = ?", (vote_id,)).fetchone()
    return _row_to_vote(row)


def retract_vote(db_path: str | Path, activity_id: str, user_id: str) -> None:
    """No-Op, falls kein Vote existiert (mirrort
    ``social/follows.py::unfollow_organizer``)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM activity_votes WHERE activity_id = ? AND user_id = ?", (activity_id, user_id))


def has_voted(db_path: str | Path, activity_id: str, user_id: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM activity_votes WHERE activity_id = ? AND user_id = ?", (activity_id, user_id)
        ).fetchone()
    return row is not None


def count_votes_for_activity(db_path: str | Path, activity_id: str) -> int:
    with sqlite3.connect(db_path) as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM activity_votes WHERE activity_id = ?", (activity_id,)
        ).fetchone()
    return count


def count_votes_by_activity_for_party(db_path: str | Path, party_id: str) -> dict[str, int]:
    """Eine JOIN-Query für die gesamte Party statt N
    ``count_votes_for_activity``-Aufrufe - vermeidet N+1 sowohl in
    ``GET .../activities`` als auch im Equipment-Demand-Compute-Merge (siehe
    ``backend/app/routers/admin_equipment.py``). Activities OHNE Votes fehlen
    im Ergebnis-Dict (kein ``0``-Eintrag) - Aufrufer nutzen
    ``.get(activity_id, 0)``."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT av.activity_id, COUNT(*) FROM activity_votes av
            JOIN activities a ON a.id = av.activity_id
            WHERE a.party_id = ?
            GROUP BY av.activity_id
            """,
            (party_id,),
        ).fetchall()
    return {activity_id: count for activity_id, count in rows}


def list_voted_activity_ids_for_user(db_path: str | Path, party_id: str, user_id: str) -> set[str]:
    """Eine JOIN-Query für ``voted_by_me`` über ALLE Activities einer Party
    statt N ``has_voted``-Aufrufe - derselbe N+1-Vermeidungsgrund wie
    ``count_votes_by_activity_for_party``. Genutzt von
    ``GET .../activities``."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT av.activity_id FROM activity_votes av
            JOIN activities a ON a.id = av.activity_id
            WHERE a.party_id = ? AND av.user_id = ?
            """,
            (party_id, user_id),
        ).fetchall()
    return {row[0] for row in rows}
