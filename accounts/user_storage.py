"""SQLite-Persistenz für echte User-Accounts + Refresh-Token-Verwaltung
(Account-basierter Pivot, Phase 1).

Mirrort exakt das etablierte Muster aus ``party_engine/response_storage.py``/
``party_context/storage.py``: kurzlebige ``with sqlite3.connect(db_path) as
conn:``-Blöcke, ``CREATE TABLE IF NOT EXISTS``, ein ``init_*(db_path)`` pro
Modul, ausführbarer ``__main__``-Selbsttest.

FK-Constraints sind in der DDL nur zu Dokumentationszwecken angegeben -
``PRAGMA foreign_keys=ON`` wird (wie im Rest des Projekts) nicht gesetzt,
referentielle Integrität wird stattdessen auf Anwendungsebene geprüft.

``password_hash`` verlässt dieses Modul NIE über ``get_user_by_id``/
``get_user_by_email`` (öffentliche Lookups) - nur ``get_credentials_by_email``
(intern, ausschließlich vom Login-Code-Pfad genutzt) liest ihn.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from accounts.domain import User


class EmailAlreadyRegisteredError(Exception):
    pass


@dataclass
class RefreshTokenRecord:
    id: str  # jti
    user_id: str
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    replaced_by_id: str | None


@dataclass
class PasswordResetTokenRecord:
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime


def init_user_storage(db_path: str | Path) -> None:
    """Legt ``users``/``refresh_tokens`` an, falls nicht vorhanden. Idempotent,
    sicher bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                profile_image TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                replaced_by_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id)"
        )


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        profile_image=row["profile_image"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_user(db_path: str | Path, user_id: str, email: str, password_hash: str, display_name: str) -> User:
    normalized_email = email.strip().lower()
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, display_name, profile_image, created_at) "
                "VALUES (?, ?, ?, ?, '', ?)",
                (user_id, normalized_email, password_hash, display_name, now),
            )
    except sqlite3.IntegrityError as exc:
        raise EmailAlreadyRegisteredError(normalized_email) from exc
    return User(
        id=user_id, email=normalized_email, display_name=display_name, created_at=datetime.fromisoformat(now)
    )


def get_user_by_id(db_path: str | Path, user_id: str) -> User | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, email, display_name, profile_image, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_user(row) if row is not None else None


def get_user_by_email(db_path: str | Path, email: str) -> User | None:
    normalized_email = email.strip().lower()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, email, display_name, profile_image, created_at FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
    return _row_to_user(row) if row is not None else None


def get_credentials_by_email(db_path: str | Path, email: str) -> tuple[User, str] | None:
    """INTERN - ausschließlich für den Login-Code-Pfad
    (``backend/app/core/auth.py``). Liefert ``(User, password_hash)``."""
    normalized_email = email.strip().lower()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
    if row is None:
        return None
    return _row_to_user(row), row["password_hash"]


def update_profile_image(db_path: str | Path, user_id: str, relative_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE users SET profile_image = ? WHERE id = ?", (relative_path, user_id))


def save_refresh_token(
    db_path: str | Path, jti: str, user_id: str, token_hash: str, issued_at: datetime, expires_at: datetime
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (id, user_id, token_hash, issued_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (jti, user_id, token_hash, issued_at.isoformat(), expires_at.isoformat()),
        )


def get_refresh_token(db_path: str | Path, jti: str) -> RefreshTokenRecord | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM refresh_tokens WHERE id = ?", (jti,)).fetchone()
    if row is None:
        return None
    return RefreshTokenRecord(
        id=row["id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        issued_at=datetime.fromisoformat(row["issued_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        replaced_by_id=row["replaced_by_id"],
    )


def revoke_refresh_token(db_path: str | Path, jti: str, replaced_by_id: str | None = None) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ?, replaced_by_id = ? WHERE id = ?",
            (datetime.now().isoformat(), replaced_by_id, jti),
        )


def revoke_all_refresh_tokens_for_user(db_path: str | Path, user_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (datetime.now().isoformat(), user_id),
        )


def get_password_hash_by_user_id(db_path: str | Path, user_id: str) -> str | None:
    """INTERN - ausschließlich für den Auth-Code-Pfad (Password-Reset:
    "neues Passwort != aktuelles Passwort"-Prüfung)."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return row[0] if row is not None else None


def update_password_hash(db_path: str | Path, user_id: str, new_password_hash: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))


def create_password_reset_token(
    db_path: str | Path, token_id: str, user_id: str, token_hash: str, expires_at: datetime
) -> None:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token_id, user_id, token_hash, expires_at.isoformat(), now),
        )


def get_password_reset_token(db_path: str | Path, token_id: str) -> PasswordResetTokenRecord | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM password_reset_tokens WHERE id = ?", (token_id,)).fetchone()
    if row is None:
        return None
    return PasswordResetTokenRecord(
        id=row["id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        used_at=datetime.fromisoformat(row["used_at"]) if row["used_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def mark_password_reset_token_used(db_path: str | Path, token_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
            (datetime.now().isoformat(), token_id),
        )


def invalidate_password_reset_tokens_for_user(db_path: str | Path, user_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
            (datetime.now().isoformat(), user_id),
        )


if __name__ == "__main__":
    import tempfile
    import uuid

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_user_storage.db"
        init_user_storage(db_path)
        init_user_storage(db_path)  # idempotent, darf nicht crashen

        user = create_user(db_path, uuid.uuid4().hex, "Alice@Example.com", "hashed-pw", "Alice")
        assert user.email == "alice@example.com"  # normalisiert
        assert not hasattr(user, "password_hash")

        by_id = get_user_by_id(db_path, user.id)
        assert by_id is not None
        assert by_id.email == "alice@example.com"

        by_email = get_user_by_email(db_path, "ALICE@example.com")  # case-insensitive
        assert by_email is not None
        assert by_email.id == user.id

        creds = get_credentials_by_email(db_path, "alice@example.com")
        assert creds is not None
        assert creds[1] == "hashed-pw"

        try:
            create_user(db_path, uuid.uuid4().hex, "alice@example.com", "other-hash", "Alice2")
            raise AssertionError("sollte EmailAlreadyRegisteredError werfen")
        except EmailAlreadyRegisteredError:
            pass

        assert get_user_by_id(db_path, "unknown") is None
        assert get_credentials_by_email(db_path, "unknown@example.com") is None

        jti = uuid.uuid4().hex
        now = datetime.now()
        save_refresh_token(db_path, jti, user.id, "tokenhash", now, now)
        record = get_refresh_token(db_path, jti)
        assert record is not None
        assert record.revoked_at is None

        revoke_refresh_token(db_path, jti, replaced_by_id="next-jti")
        revoked = get_refresh_token(db_path, jti)
        assert revoked.revoked_at is not None
        assert revoked.replaced_by_id == "next-jti"

        jti2 = uuid.uuid4().hex
        save_refresh_token(db_path, jti2, user.id, "tokenhash2", now, now)
        revoke_all_refresh_tokens_for_user(db_path, user.id)
        assert get_refresh_token(db_path, jti2).revoked_at is not None

        update_profile_image(db_path, user.id, "profile_images/user.jpg")
        assert get_user_by_id(db_path, user.id).profile_image == "profile_images/user.jpg"

        assert get_password_hash_by_user_id(db_path, user.id) == "hashed-pw"
        update_password_hash(db_path, user.id, "new-hashed-pw")
        assert get_password_hash_by_user_id(db_path, user.id) == "new-hashed-pw"
        assert get_password_hash_by_user_id(db_path, "unknown") is None

        reset_token_id = uuid.uuid4().hex
        create_password_reset_token(db_path, reset_token_id, user.id, "reset-hash", now)
        reset_record = get_password_reset_token(db_path, reset_token_id)
        assert reset_record is not None
        assert reset_record.used_at is None
        mark_password_reset_token_used(db_path, reset_token_id)
        assert get_password_reset_token(db_path, reset_token_id).used_at is not None

        reset_token_id2 = uuid.uuid4().hex
        create_password_reset_token(db_path, reset_token_id2, user.id, "reset-hash-2", now)
        invalidate_password_reset_tokens_for_user(db_path, user.id)
        assert get_password_reset_token(db_path, reset_token_id2).used_at is not None
        assert get_password_reset_token(db_path, "unknown") is None

        print("accounts/user_storage.py sanity check OK.")
