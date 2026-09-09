"""SQLite-Persistenz für ``Friendship`` (Social-Graph-Phase-1).

Mirrort das etablierte Muster aus ``accounts/discover_learning.py``:
kurzlebige ``with sqlite3.connect(db_path) as conn:``-Blöcke, ein
``init_*_storage(db_path)``, ``_row_to_X``-Helper, ausführbarer
``__main__``-Selbsttest.

Erste symmetrische Beziehung in dieser Codebase - siehe ``social/domain.py``
für die Invariante ``user_a_id < user_b_id`` und ihre Begründung. Diese
Datei ist der EINZIGE Ort, an dem das kanonische Paar gebildet wird
(``_canonical_pair``); alle Lese-/Schreibfunktionen wenden es intern an,
Aufrufer übergeben die beiden User-IDs in beliebiger Reihenfolge."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from social.domain import Friendship


def init_friendship_storage(db_path: str | Path) -> None:
    """Legt ``friendships`` an, falls nicht vorhanden. Idempotent, sicher
    bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friendships (
                id TEXT PRIMARY KEY,
                user_a_id TEXT NOT NULL,
                user_b_id TEXT NOT NULL,
                source_friend_request_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_a_id, user_b_id),
                FOREIGN KEY (user_a_id) REFERENCES users(id),
                FOREIGN KEY (user_b_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friendships_user_a ON friendships(user_a_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friendships_user_b ON friendships(user_b_id)")


def _canonical_pair(user_id_1: str, user_id_2: str) -> tuple[str, str]:
    """Alle User-IDs sind fixed-length ``uuid.uuid4().hex`` - einfacher
    lexikographischer Stringvergleich reicht für eine stabile totale
    Ordnung."""
    return tuple(sorted((user_id_1, user_id_2)))  # type: ignore[return-value]


def _row_to_friendship(row: sqlite3.Row) -> Friendship:
    return Friendship(
        id=row["id"],
        user_a_id=row["user_a_id"],
        user_b_id=row["user_b_id"],
        source_friend_request_id=row["source_friend_request_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_friendship(
    db_path: str | Path,
    friendship_id: str,
    user_id_1: str,
    user_id_2: str,
    source_friend_request_id: str | None = None,
) -> Friendship:
    """Idempotent (mirrort ``discover_learning.block_organizer``'s
    SELECT-then-return-existing-Form): ein erneuter Aufruf für dasselbe Paar
    gibt einfach die bestehende Zeile zurück, statt zu duplizieren oder zu
    crashen."""
    user_a_id, user_b_id = _canonical_pair(user_id_1, user_id_2)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM friendships WHERE user_a_id = ? AND user_b_id = ?", (user_a_id, user_b_id)
        ).fetchone()
        if existing is not None:
            return _row_to_friendship(existing)

        now = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO friendships (id, user_a_id, user_b_id, source_friend_request_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (friendship_id, user_a_id, user_b_id, source_friend_request_id, now),
        )
        row = conn.execute("SELECT * FROM friendships WHERE id = ?", (friendship_id,)).fetchone()
    return _row_to_friendship(row)


def are_friends(db_path: str | Path, user_id_1: str, user_id_2: str) -> bool:
    user_a_id, user_b_id = _canonical_pair(user_id_1, user_id_2)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM friendships WHERE user_a_id = ? AND user_b_id = ?", (user_a_id, user_b_id)
        ).fetchone()
    return row is not None


def list_friends_for_user(db_path: str | Path, user_id: str) -> list[Friendship]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM friendships WHERE user_a_id = ? OR user_b_id = ? ORDER BY created_at DESC",
            (user_id, user_id),
        ).fetchall()
    return [_row_to_friendship(r) for r in rows]


def remove_friendship(db_path: str | Path, user_id_1: str, user_id_2: str) -> None:
    """Löscht die Freundschaft. No-Op, falls keine Zeile existiert (mirrort
    ``discover_learning.unblock_organizer``)."""
    user_a_id, user_b_id = _canonical_pair(user_id_1, user_id_2)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM friendships WHERE user_a_id = ? AND user_b_id = ?", (user_a_id, user_b_id))


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_friendships.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        init_friendship_storage(db_path)
        init_friendship_storage(db_path)  # idempotent

        anna = user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")
        max_ = user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")
        ben = user_storage.create_user(db_path, uuid.uuid4().hex, "ben@example.com", "hash", "Ben")

        assert are_friends(db_path, anna.id, max_.id) is False
        assert list_friends_for_user(db_path, anna.id) == []

        friendship = create_friendship(db_path, uuid.uuid4().hex, anna.id, max_.id)
        assert are_friends(db_path, anna.id, max_.id) is True
        # Symmetrisch: Reihenfolge der Argumente egal.
        assert are_friends(db_path, max_.id, anna.id) is True

        # Kanonische Ordnung: user_a_id < user_b_id, unabhängig von der Aufruf-Reihenfolge.
        assert friendship.user_a_id < friendship.user_b_id

        # Idempotent: erneuter Aufruf (auch mit vertauschten Argumenten) gibt dieselbe Zeile.
        again = create_friendship(db_path, uuid.uuid4().hex, max_.id, anna.id)
        assert again.id == friendship.id

        assert len(list_friends_for_user(db_path, anna.id)) == 1
        assert len(list_friends_for_user(db_path, max_.id)) == 1
        assert list_friends_for_user(db_path, ben.id) == []

        remove_friendship(db_path, anna.id, max_.id)
        assert are_friends(db_path, anna.id, max_.id) is False
        assert list_friends_for_user(db_path, anna.id) == []

        # Unfreund ohne bestehende Freundschaft -> No-Op, kein Crash.
        remove_friendship(db_path, anna.id, max_.id)

        print("social/friendships.py sanity check OK.")
