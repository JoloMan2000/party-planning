"""SQLite-Persistenz für die In-App-Notification-Inbox (Phase 5). Mirrort
das Muster aus ``accounts/invitation_storage.py``/``accounts/party_storage.py``
- kurzlebige ``sqlite3.connect``-Blocks pro Funktion, keine ORM.

Bewusst poll-basiert statt echtem Push (FCM/APNs) - siehe TODO in
``backend/app/routers/notifications.py`` für den späteren Upgrade-Pfad.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from accounts.domain import Notification


def init_notifications(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                party_id TEXT,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)")


def _row_to_notification(row: sqlite3.Row) -> Notification:
    return Notification(
        id=row["id"],
        user_id=row["user_id"],
        party_id=row["party_id"],
        kind=row["kind"],
        message=row["message"],
        created_at=datetime.fromisoformat(row["created_at"]),
        read=bool(row["read"]),
    )


def create_notification(
    db_path: str | Path,
    notification_id: str,
    user_id: str,
    party_id: str | None,
    kind: str,
    message: str,
) -> Notification:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO notifications (id, user_id, party_id, kind, message, created_at, read)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (notification_id, user_id, party_id, kind, message, now),
        )
    return Notification(
        id=notification_id, user_id=user_id, party_id=party_id, kind=kind, message=message,
        created_at=datetime.fromisoformat(now), read=False,
    )


def list_notifications(db_path: str | Path, user_id: str) -> list[Notification]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [_row_to_notification(r) for r in rows]


def mark_read(db_path: str | Path, notification_id: str, user_id: str) -> Notification | None:
    """Setzt ``read = 1``, aber nur wenn die Notification [user_id] gehört
    (kein Cross-User-Zugriff auf fremde Notifications). ``None`` wenn nicht
    gefunden oder nicht dem User gehörend."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM notifications WHERE id = ? AND user_id = ?", (notification_id, user_id)
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
    notification = _row_to_notification(row)
    notification.read = True
    return notification


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_notification_storage.db"
        user_storage.init_user_storage(db_path)
        init_notifications(db_path)
        init_notifications(db_path)  # idempotent

        user = user_storage.create_user(db_path, uuid.uuid4().hex, "user@example.com", "hash", "User")
        other = user_storage.create_user(db_path, uuid.uuid4().hex, "other@example.com", "hash", "Other")

        n1 = create_notification(db_path, uuid.uuid4().hex, user.id, "party-1", "invitation", "You're invited!")
        assert n1.read is False

        listed = list_notifications(db_path, user.id)
        assert len(listed) == 1
        assert listed[0].id == n1.id

        # Cross-user: other user can't mark it read
        assert mark_read(db_path, n1.id, other.id) is None
        still_unread = list_notifications(db_path, user.id)
        assert still_unread[0].read is False

        marked = mark_read(db_path, n1.id, user.id)
        assert marked is not None
        assert marked.read is True
        now_read = list_notifications(db_path, user.id)
        assert now_read[0].read is True

        assert list_notifications(db_path, other.id) == []

        print("accounts/notification_storage.py sanity check OK.")
