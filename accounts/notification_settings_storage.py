"""SQLite-Persistenz für die Pro-User-Notification-Kategorie-Schalter
(Social-Graph-Phase-8, Spec §109/§156).

Mirrort das Muster aus ``accounts/discovery_storage.py`` (skalare
Preference-Zeile, ``user_id`` als PK, ``INSERT ... ON CONFLICT DO UPDATE``
als Full-Replace-Upsert - der Client hält immer alle Werte, kein
Client-seitiges Diffing). Fehlt die Zeile, liefert
``get_notification_settings`` die Dataclass-Defaults (alle Kategorien AN) -
gleiches graceful-missing-Verhalten wie
``discovery_storage.get_discovery_preferences`` im Router."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from accounts.domain import NotificationSettings


def init_notification_settings_storage(db_path: str | Path) -> None:
    """Legt ``notification_settings`` an, falls nicht vorhanden. Idempotent,
    sicher bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id TEXT PRIMARY KEY,
                friend_requests INTEGER NOT NULL DEFAULT 1,
                party_invitations INTEGER NOT NULL DEFAULT 1,
                organizer_updates INTEGER NOT NULL DEFAULT 1,
                followed_event_updates INTEGER NOT NULL DEFAULT 1,
                nearby_discover INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )


def _row_to_settings(row: sqlite3.Row) -> NotificationSettings:
    return NotificationSettings(
        user_id=row["user_id"],
        friend_requests=bool(row["friend_requests"]),
        party_invitations=bool(row["party_invitations"]),
        organizer_updates=bool(row["organizer_updates"]),
        followed_event_updates=bool(row["followed_event_updates"]),
        nearby_discover=bool(row["nearby_discover"]),
    )


def get_notification_settings(db_path: str | Path, user_id: str) -> NotificationSettings:
    """Fällt auf die ``NotificationSettings``-Dataclass-Defaults (alle
    Kategorien AN) zurück, falls für den User noch keine Zeile existiert."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM notification_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    return _row_to_settings(row) if row is not None else NotificationSettings(user_id=user_id)


def upsert_notification_settings(
    db_path: str | Path,
    user_id: str,
    *,
    friend_requests: bool,
    party_invitations: bool,
    organizer_updates: bool,
    followed_event_updates: bool,
    nearby_discover: bool,
) -> NotificationSettings:
    """Full-Replace-Upsert - alle fünf Werte werden immer geschrieben (der
    Client sendet stets den vollständigen gewünschten Endzustand, wie bei
    ``discovery_storage.upsert_discovery_preferences``)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO notification_settings
                (user_id, friend_requests, party_invitations, organizer_updates,
                 followed_event_updates, nearby_discover)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                friend_requests = excluded.friend_requests,
                party_invitations = excluded.party_invitations,
                organizer_updates = excluded.organizer_updates,
                followed_event_updates = excluded.followed_event_updates,
                nearby_discover = excluded.nearby_discover
            """,
            (
                user_id,
                1 if friend_requests else 0,
                1 if party_invitations else 0,
                1 if organizer_updates else 0,
                1 if followed_event_updates else 0,
                1 if nearby_discover else 0,
            ),
        )
    return get_notification_settings(db_path, user_id)


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_notification_settings.db"
        user_storage.init_user_storage(db_path)
        init_notification_settings_storage(db_path)
        init_notification_settings_storage(db_path)  # idempotent

        user = user_storage.create_user(db_path, uuid.uuid4().hex, "user@example.com", "hash", "User")

        # Keine Zeile -> alle Defaults AN.
        defaults = get_notification_settings(db_path, user.id)
        assert defaults.friend_requests is True
        assert defaults.organizer_updates is True
        assert defaults.followed_event_updates is True
        assert defaults.nearby_discover is True

        saved = upsert_notification_settings(
            db_path, user.id,
            friend_requests=True, party_invitations=True, organizer_updates=False,
            followed_event_updates=False, nearby_discover=True,
        )
        assert saved.organizer_updates is False
        assert saved.followed_event_updates is False
        assert saved.friend_requests is True

        # Persistiert.
        reread = get_notification_settings(db_path, user.id)
        assert reread.organizer_updates is False
        assert reread.nearby_discover is True

        # Full-Replace: erneuter Upsert mit anderen Werten überschreibt vollständig.
        saved2 = upsert_notification_settings(
            db_path, user.id,
            friend_requests=False, party_invitations=False, organizer_updates=True,
            followed_event_updates=True, nearby_discover=False,
        )
        assert saved2.friend_requests is False
        assert saved2.organizer_updates is True
        assert saved2.nearby_discover is False

        # Anderer User -> unberührt, Defaults.
        other = user_storage.create_user(db_path, uuid.uuid4().hex, "other@example.com", "hash", "Other")
        assert get_notification_settings(db_path, other.id).organizer_updates is True

        print("accounts/notification_settings_storage.py sanity check OK.")
