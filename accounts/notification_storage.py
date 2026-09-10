"""SQLite-Persistenz für die In-App-Notification-Inbox (Phase 5). Mirrort
das Muster aus ``accounts/invitation_storage.py``/``accounts/party_storage.py``
- kurzlebige ``sqlite3.connect``-Blocks pro Funktion, keine ORM.

Bewusst poll-basiert statt echtem Push (FCM/APNs) - siehe TODO in
``backend/app/routers/notifications.py`` für den späteren Upgrade-Pfad.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
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


def list_notifications(db_path: str | Path, user_id: str, limit: int | None = None) -> list[Notification]:
    """Neueste zuerst. ``limit=None`` liefert alle (Rückwärtskompatibilität
    für den ``__main__``-Selbsttest); der Router übergibt immer einen
    beschränkten Wert, damit eine wachsende Inbox nicht die komplette
    Historie in einer Antwort zurückgibt."""
    sql = "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC"
    params: tuple = (user_id,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (user_id, limit)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_notification(r) for r in rows]


def has_recent_notification(
    db_path: str | Path, user_id: str, kind: str, party_id: str, within_minutes: int
) -> bool:
    """Social-Graph-Phase-8: True, wenn für ``(user_id, kind, party_id)``
    in den letzten ``within_minutes`` Minuten schon eine Notification
    erzeugt wurde - Frequency-Guard gegen Spam bei schnell
    aufeinanderfolgenden Edits desselben Events (Spec §65/§90). ``created_at``
    wird von ``create_notification`` als NAIVE lokale Zeit geschrieben,
    daher hier ebenfalls naive ``datetime.now()`` für den Cutoff (lexikaler
    ISO-8601-Vergleich)."""
    cutoff = (datetime.now() - timedelta(minutes=within_minutes)).isoformat()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM notifications WHERE user_id = ? AND kind = ? AND party_id = ? AND created_at > ? LIMIT 1",
            (user_id, kind, party_id, cutoff),
        ).fetchone()
    return row is not None


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

        # Social-Graph-Phase-8: has_recent_notification
        assert has_recent_notification(db_path, user.id, "invitation", "party-1", within_minutes=60) is True
        assert has_recent_notification(db_path, user.id, "invitation", "party-1", within_minutes=0) is False  # Cutoff jetzt
        assert has_recent_notification(db_path, user.id, "event_updated", "party-1", within_minutes=60) is False  # anderes kind
        assert has_recent_notification(db_path, user.id, "invitation", "party-2", within_minutes=60) is False  # andere party
        assert has_recent_notification(db_path, other.id, "invitation", "party-1", within_minutes=60) is False  # anderer user

        print("accounts/notification_storage.py sanity check OK.")
