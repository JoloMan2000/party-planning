"""SQLite-Persistenz für den per-User Spotify-OAuth/PKCE-Connection-Layer
(Onboarding-Spec, Phase 7 des Account-basierten Pivots).

Mirrort das etablierte Muster aus ``accounts/user_storage.py``/
``accounts/profile_storage.py``: kurzlebige ``with sqlite3.connect(db_path)
as conn:``-Blöcke, ``CREATE TABLE IF NOT EXISTS``, ein ``init_*(db_path)``
pro Modul, ausführbarer ``__main__``-Selbsttest.

Access-/Refresh-Token werden verschlüsselt (nicht nur gehasht wie
Refresh-Tokens in ``user_storage.py``) gespeichert, weil sie - anders als
unsere eigenen Refresh-Tokens - später tatsächlich wieder im Klartext
gebraucht werden, um Spotify-API-Aufrufe zu machen. Der Schlüssel wird als
``bytes``-Parameter übergeben (nie aus ``backend.app.core.config`` importiert
- ``accounts/*`` importiert nie aus ``backend.app.*``, siehe Plan)."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

import accounts.spotify_oauth_client as spotify_oauth_client
from accounts.domain import SpotifyConnection

_OAUTH_STATE_TTL = timedelta(minutes=10)


def init_spotify_storage(db_path: str | Path) -> None:
    """Legt ``spotify_oauth_states``/``spotify_connections`` an, falls nicht
    vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spotify_oauth_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spotify_connections (
                user_id TEXT PRIMARY KEY,
                spotify_user_id TEXT NOT NULL,
                access_token_encrypted TEXT NOT NULL,
                refresh_token_encrypted TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                connected_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )


def _encrypt(encryption_key: bytes, value: str) -> str:
    return Fernet(encryption_key).encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(encryption_key: bytes, value: str) -> str:
    return Fernet(encryption_key).decrypt(value.encode("ascii")).decode("utf-8")


def create_oauth_state(db_path: str | Path, user_id: str) -> tuple[str, str]:
    """Erzeugt PKCE-Verifier/Challenge + CSRF-``state``, persistiert
    ``(state, user_id, code_verifier)`` kurzlebig (10 Min). Liefert
    ``(state, code_challenge)`` für den Router, um die Authorize-URL zu bauen."""
    code_verifier, code_challenge = spotify_oauth_client.generate_pkce_pair()
    state = secrets.token_urlsafe(24)
    now = datetime.now()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO spotify_oauth_states (state, user_id, code_verifier, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (state, user_id, code_verifier, now.isoformat(), (now + _OAUTH_STATE_TTL).isoformat()),
        )
    return state, code_challenge


def consume_oauth_state(db_path: str | Path, state: str) -> tuple[str, str] | None:
    """Liest + löscht die ``state``-Zeile (Einmalgebrauch, unabhängig vom
    Ergebnis). Liefert ``(user_id, code_verifier)`` nur, wenn nicht
    abgelaufen - sonst ``None``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM spotify_oauth_states WHERE state = ?", (state,)).fetchone()
        conn.execute("DELETE FROM spotify_oauth_states WHERE state = ?", (state,))
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        return None
    return row["user_id"], row["code_verifier"]


def _row_to_connection(row: sqlite3.Row) -> SpotifyConnection:
    return SpotifyConnection(
        user_id=row["user_id"],
        spotify_user_id=row["spotify_user_id"],
        scope=row["scope"],
        connected_at=datetime.fromisoformat(row["connected_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def save_connection(
    db_path: str | Path,
    encryption_key: bytes,
    user_id: str,
    spotify_user_id: str,
    access_token: str,
    refresh_token: str,
    scope: str,
    expires_in: int,
) -> SpotifyConnection:
    now = datetime.now()
    expires_at = now + timedelta(seconds=expires_in)
    with sqlite3.connect(db_path) as conn:
        existing = conn.execute(
            "SELECT connected_at FROM spotify_connections WHERE user_id = ?", (user_id,)
        ).fetchone()
        connected_at = existing[0] if existing is not None else now.isoformat()
        conn.execute(
            """
            INSERT INTO spotify_connections
                (user_id, spotify_user_id, access_token_encrypted, refresh_token_encrypted, scope,
                 expires_at, connected_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                spotify_user_id = excluded.spotify_user_id,
                access_token_encrypted = excluded.access_token_encrypted,
                refresh_token_encrypted = excluded.refresh_token_encrypted,
                scope = excluded.scope,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                spotify_user_id,
                _encrypt(encryption_key, access_token),
                _encrypt(encryption_key, refresh_token),
                scope,
                expires_at.isoformat(),
                connected_at,
                now.isoformat(),
            ),
        )
    result = get_connection(db_path, user_id)
    assert result is not None
    return result


def get_connection(db_path: str | Path, user_id: str) -> SpotifyConnection | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM spotify_connections WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_connection(row) if row is not None else None


def delete_connection(db_path: str | Path, user_id: str) -> None:
    """Trennt die Verbindung (löscht unsere gespeicherte Kopie). Spotify
    bietet keine öffentliche App-seitige Token-Revocation-API - wer den
    Zugriff auch bei Spotify selbst widerrufen will, muss das zusätzlich in
    den eigenen Spotify-Account-Einstellungen tun."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM spotify_connections WHERE user_id = ?", (user_id,))


def ensure_valid_access_token(
    db_path: str | Path, encryption_key: bytes, client_id: str, client_secret: str, user_id: str
) -> str | None:
    """Liefert ein gültiges Access-Token, erneuert es bei Bedarf über den
    gespeicherten Refresh-Token. ``None``, wenn (noch) nicht verbunden.
    Wird von keinem Endpoint dieser Phase aufgerufen - vorbereitet für die
    künftige Import-Funktion (Phase 8/9)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM spotify_connections WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None

    if datetime.fromisoformat(row["expires_at"]) > datetime.now():
        return _decrypt(encryption_key, row["access_token_encrypted"])

    refresh_token = _decrypt(encryption_key, row["refresh_token_encrypted"])
    token_data = spotify_oauth_client.refresh_access_token(client_id, client_secret, refresh_token)
    now = datetime.now()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE spotify_connections SET access_token_encrypted = ?, refresh_token_encrypted = ?, "
            "expires_at = ?, updated_at = ? WHERE user_id = ?",
            (
                _encrypt(encryption_key, token_data["access_token"]),
                _encrypt(encryption_key, token_data["refresh_token"]),
                (now + timedelta(seconds=token_data["expires_in"])).isoformat(),
                now.isoformat(),
                user_id,
            ),
        )
    return token_data["access_token"]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_spotify_storage.db"
        init_spotify_storage(db_path)
        init_spotify_storage(db_path)  # idempotent, darf nicht crashen

        key = Fernet.generate_key()
        user_id = "user-1"

        state, challenge = create_oauth_state(db_path, user_id)
        assert len(challenge) > 0
        consumed = consume_oauth_state(db_path, state)
        assert consumed is not None
        assert consumed[0] == user_id

        # Einmalgebrauch - zweiter Consume derselben state liefert None.
        assert consume_oauth_state(db_path, state) is None
        assert consume_oauth_state(db_path, "unknown-state") is None

        assert get_connection(db_path, user_id) is None
        saved = save_connection(
            db_path, key, user_id, "spotify-user-1", "access-tok", "refresh-tok", "user-top-read", 3600
        )
        assert saved.spotify_user_id == "spotify-user-1"
        assert not hasattr(saved, "access_token")

        fetched = get_connection(db_path, user_id)
        assert fetched is not None
        assert fetched.scope == "user-top-read"

        # Upsert darf keinen zweiten Datensatz anlegen, connected_at bleibt stabil.
        saved2 = save_connection(
            db_path, key, user_id, "spotify-user-1", "access-tok-2", "refresh-tok-2", "user-top-read", 3600
        )
        assert saved2.connected_at == saved.connected_at

        token = ensure_valid_access_token(db_path, key, "client-id", "client-secret", user_id)
        assert token == "access-tok-2"  # noch nicht abgelaufen, kein Refresh-Call nötig

        delete_connection(db_path, user_id)
        assert get_connection(db_path, user_id) is None
        assert ensure_valid_access_token(db_path, key, "client-id", "client-secret", user_id) is None

        print("accounts/spotify_storage.py sanity check OK.")
