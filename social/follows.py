"""SQLite-Persistenz für ``OrganizerFollow`` und ``EventFollow``
(Social-Graph-Phase-5, AUFGABE-Spec §45-79).

Beide Follow-Typen liegen bewusst in EINEM Modul (analog dazu, dass
``social/blocks.py`` die gesamte Block-Logik hält) - es ist dieselbe
gerichtete ``UNIQUE(user_id, ziel_id)``-Form wie ``user_blocks`` /
``blocked_organizers``, nur mit gegenteiliger Absicht (positives
Interesse-Signal statt Ausschluss).

Abhängigkeits-Richtung: dieses Modul importiert NICHTS aus ``organizers`` /
``accounts`` (reine Storage-Schicht auf den eigenen zwei Tabellen). Die
Cross-Checks "ist dieser Organizer verifiziert?" / "ist diese Party
veröffentlicht?" passieren im Router (``backend/app/routers/follows.py``) -
exakt wie ``social/blocks.py`` seine Cross-Checks nicht selbst macht.

``list_organizer_follows`` / ``list_event_follows`` geben eine nach
``created_at DESC`` sortierte ``list`` zurück - bewusste Abweichung vom
Geschwister-Modul ``social/blocks.py`` (``list_blocked_user_ids -> set``):
ein Follow-Feed ist chronologisch, das mirrort deshalb
``social/friendships.py::list_friends_for_user`` statt ``blocks.py``.

Der vom Spec vorgeschlagene ``status``-Wert ("active") wird NICHT als Spalte
modelliert - "gefolgt" = "Zeile existiert", Unfollow = ``DELETE`` (wie
``user_blocks`` / ``friendships`` / ``public_events``). Eine spätere weiche
"suspended follow"-Stufe kann die Spalte nachrüsten."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from social.domain import EventFollow, OrganizerFollow


def init_follow_storage(db_path: str | Path) -> None:
    """Legt ``organizer_follows`` und ``event_follows`` an, falls nicht
    vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar. Beide
    Tabellen sind brandneu (Phase 5) - kein ``ALTER TABLE``-Migrations-Dict
    nötig."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS organizer_follows (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                organizer_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, organizer_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (organizer_id) REFERENCES organizers(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_organizer_follows_user ON organizer_follows(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_organizer_follows_organizer ON organizer_follows(organizer_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_follows (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                party_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, party_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (party_id) REFERENCES parties(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_follows_user ON event_follows(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_follows_party ON event_follows(party_id)")


def _row_to_organizer_follow(row: sqlite3.Row) -> OrganizerFollow:
    return OrganizerFollow(
        id=row["id"],
        user_id=row["user_id"],
        organizer_id=row["organizer_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_event_follow(row: sqlite3.Row) -> EventFollow:
    return EventFollow(
        id=row["id"],
        user_id=row["user_id"],
        party_id=row["party_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


# --- Organizer follows ---------------------------------------------------


def follow_organizer(db_path: str | Path, follow_id: str, user_id: str, organizer_id: str) -> OrganizerFollow:
    """Idempotent (SELECT-then-return-existing, mirrort
    ``blocks.block_user``). Ein erneuter Aufruf gibt die bestehende Zeile
    unverändert zurück, kein Duplikat, keine neue ``created_at``."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM organizer_follows WHERE user_id = ? AND organizer_id = ?", (user_id, organizer_id)
        ).fetchone()
        if existing is not None:
            return _row_to_organizer_follow(existing)
        conn.execute(
            "INSERT INTO organizer_follows (id, user_id, organizer_id, created_at) VALUES (?, ?, ?, ?)",
            (follow_id, user_id, organizer_id, now),
        )
        row = conn.execute("SELECT * FROM organizer_follows WHERE id = ?", (follow_id,)).fetchone()
    return _row_to_organizer_follow(row)


def unfollow_organizer(db_path: str | Path, user_id: str, organizer_id: str) -> None:
    """No-Op, falls kein Follow existiert (mirrort ``blocks.unblock_user``)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM organizer_follows WHERE user_id = ? AND organizer_id = ?", (user_id, organizer_id)
        )


def is_following_organizer(db_path: str | Path, user_id: str, organizer_id: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM organizer_follows WHERE user_id = ? AND organizer_id = ?", (user_id, organizer_id)
        ).fetchone()
    return row is not None


def list_organizer_follows(db_path: str | Path, user_id: str) -> list[OrganizerFollow]:
    """Neueste zuerst - Follow-Feed ist chronologisch (mirrort
    ``friendships.list_friends_for_user``, NICHT das ``set`` aus
    ``blocks.list_blocked_user_ids``)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM organizer_follows WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [_row_to_organizer_follow(r) for r in rows]


def count_organizer_followers(db_path: str | Path, organizer_id: str) -> int:
    """Serverseitige Aggregation (Spec §59: "Keine clientseitige Zählung")."""
    with sqlite3.connect(db_path) as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM organizer_follows WHERE organizer_id = ?", (organizer_id,)
        ).fetchone()
    return count


def list_organizer_follower_ids(db_path: str | Path, organizer_id: str) -> list[str]:
    """Social-Graph-Phase-8: die User-IDs, die diesem Organizer folgen -
    Gegenrichtung zu ``list_organizer_follows`` (per Follower), gebraucht
    für den Notification-Fan-out bei einem neu veröffentlichten Event.
    Nutzt ``idx_organizer_follows_organizer``."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id FROM organizer_follows WHERE organizer_id = ? ORDER BY created_at", (organizer_id,)
        ).fetchall()
    return [row[0] for row in rows]


# --- Event follows -----------------------------------------------------


def follow_event(db_path: str | Path, follow_id: str, user_id: str, party_id: str) -> EventFollow:
    """Idempotent, strukturgleich zu ``follow_organizer``."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM event_follows WHERE user_id = ? AND party_id = ?", (user_id, party_id)
        ).fetchone()
        if existing is not None:
            return _row_to_event_follow(existing)
        conn.execute(
            "INSERT INTO event_follows (id, user_id, party_id, created_at) VALUES (?, ?, ?, ?)",
            (follow_id, user_id, party_id, now),
        )
        row = conn.execute("SELECT * FROM event_follows WHERE id = ?", (follow_id,)).fetchone()
    return _row_to_event_follow(row)


def unfollow_event(db_path: str | Path, user_id: str, party_id: str) -> None:
    """No-Op, falls kein Follow existiert."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM event_follows WHERE user_id = ? AND party_id = ?", (user_id, party_id))


def is_following_event(db_path: str | Path, user_id: str, party_id: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM event_follows WHERE user_id = ? AND party_id = ?", (user_id, party_id)
        ).fetchone()
    return row is not None


def list_event_follows(db_path: str | Path, user_id: str) -> list[EventFollow]:
    """Neueste zuerst. Kann Follows auf inzwischen unveröffentlichte Partys
    enthalten - der Router blendet diese über einen ``public_events``-JOIN
    aus, ohne die Zeile zu löschen (siehe ``EventFollow``-Docstring)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM event_follows WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [_row_to_event_follow(r) for r in rows]


def count_event_followers(db_path: str | Path, party_id: str) -> int:
    with sqlite3.connect(db_path) as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM event_follows WHERE party_id = ?", (party_id,)
        ).fetchone()
    return count


def list_event_follower_ids(db_path: str | Path, party_id: str) -> list[str]:
    """Social-Graph-Phase-8: die User-IDs, die diesem Event folgen -
    Gegenrichtung zu ``list_event_follows``, gebraucht für den
    Notification-Fan-out bei Datums-/Ort-Änderung oder Absage. Nutzt
    ``idx_event_follows_party``."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id FROM event_follows WHERE party_id = ? ORDER BY created_at", (party_id,)
        ).fetchall()
    return [row[0] for row in rows]


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage
    import organizers.storage as organizers_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_follows.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        organizers_storage.init_organizer_storage(db_path)
        init_follow_storage(db_path)
        init_follow_storage(db_path)  # idempotent

        anna = user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")
        max_ = user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")
        owner = user_storage.create_user(db_path, uuid.uuid4().hex, "owner@example.com", "hash", "Owner")

        organizer_a = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Boiler Room")
        organizer_b = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Berghain")
        party = party_storage.create_party(db_path, uuid.uuid4().hex, owner.id, "Summer Sound")

        # --- Organizer follows ---
        assert is_following_organizer(db_path, anna.id, organizer_a.id) is False
        assert list_organizer_follows(db_path, anna.id) == []
        assert count_organizer_followers(db_path, organizer_a.id) == 0

        follow = follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
        assert follow.user_id == anna.id
        assert follow.organizer_id == organizer_a.id
        assert is_following_organizer(db_path, anna.id, organizer_a.id) is True

        # Idempotent: 2. Aufruf -> identische Zeile, kein Duplikat.
        follow_again = follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
        assert follow_again.id == follow.id
        assert count_organizer_followers(db_path, organizer_a.id) == 1

        follow_organizer(db_path, uuid.uuid4().hex, max_.id, organizer_a.id)
        assert count_organizer_followers(db_path, organizer_a.id) == 2

        # Social-Graph-Phase-8: Gegenrichtung - Follower-IDs eines Organizers.
        assert set(list_organizer_follower_ids(db_path, organizer_a.id)) == {anna.id, max_.id}
        assert list_organizer_follower_ids(db_path, organizer_b.id) == []

        # Neueste zuerst.
        follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_b.id)
        annas_follows = list_organizer_follows(db_path, anna.id)
        assert [f.organizer_id for f in annas_follows] == [organizer_b.id, organizer_a.id]

        unfollow_organizer(db_path, anna.id, organizer_a.id)
        assert is_following_organizer(db_path, anna.id, organizer_a.id) is False
        assert count_organizer_followers(db_path, organizer_a.id) == 1
        unfollow_organizer(db_path, anna.id, organizer_a.id)  # No-Op

        # --- Event follows ---
        assert is_following_event(db_path, anna.id, party.id) is False
        assert list_event_follows(db_path, anna.id) == []
        assert count_event_followers(db_path, party.id) == 0

        event_follow = follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
        assert event_follow.party_id == party.id
        assert is_following_event(db_path, anna.id, party.id) is True

        event_follow_again = follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
        assert event_follow_again.id == event_follow.id
        assert count_event_followers(db_path, party.id) == 1

        # Social-Graph-Phase-8: Gegenrichtung - Follower-IDs eines Events.
        follow_event(db_path, uuid.uuid4().hex, max_.id, party.id)
        assert set(list_event_follower_ids(db_path, party.id)) == {anna.id, max_.id}
        assert list_event_follower_ids(db_path, "unknown-party") == []
        unfollow_event(db_path, max_.id, party.id)

        unfollow_event(db_path, anna.id, party.id)
        assert is_following_event(db_path, anna.id, party.id) is False
        unfollow_event(db_path, anna.id, party.id)  # No-Op

        # Unbekannte IDs -> keine Fehler.
        assert list_organizer_follows(db_path, "unknown") == []
        assert count_organizer_followers(db_path, "unknown") == 0
        assert is_following_event(db_path, "unknown", "unknown") is False

        print("social/follows.py sanity check OK.")
