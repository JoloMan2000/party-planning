"""Pytest-Unit-Tests für ``accounts/spotify_storage.py`` (Onboarding-Spec,
Phase 7). Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst
um eine pytest-Variante (isolierte ``tmp_path``-DB) inkl. Edge-Cases
(abgelaufener oauth-state, Refresh-Pfad in ``ensure_valid_access_token``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet

import accounts.spotify_oauth_client as spotify_oauth_client
import accounts.spotify_storage as spotify_storage


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "spotify_test.db"
    spotify_storage.init_spotify_storage(path)
    return path


@pytest.fixture()
def encryption_key():
    return Fernet.generate_key()


def test_create_und_consume_oauth_state_happy_path(db_path):
    state, challenge = spotify_storage.create_oauth_state(db_path, "user-1")
    assert len(challenge) > 0

    consumed = spotify_storage.consume_oauth_state(db_path, state)
    assert consumed is not None
    user_id, code_verifier = consumed
    assert user_id == "user-1"
    assert len(code_verifier) > 0


def test_consume_oauth_state_unbekannt_gibt_none(db_path):
    assert spotify_storage.consume_oauth_state(db_path, "unknown-state") is None


def test_consume_oauth_state_ist_einmalgebrauch(db_path):
    state, _challenge = spotify_storage.create_oauth_state(db_path, "user-1")
    assert spotify_storage.consume_oauth_state(db_path, state) is not None
    assert spotify_storage.consume_oauth_state(db_path, state) is None


def test_consume_oauth_state_abgelaufen_gibt_none(db_path):
    past = datetime.now() - timedelta(minutes=1)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO spotify_oauth_states (state, user_id, code_verifier, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("expired-state", "user-1", "verifier", past.isoformat(), past.isoformat()),
        )
    assert spotify_storage.consume_oauth_state(db_path, "expired-state") is None


def test_save_und_get_connection_roundtrip_ohne_rohtoken(db_path, encryption_key):
    assert spotify_storage.get_connection(db_path, "user-1") is None

    saved = spotify_storage.save_connection(
        db_path, encryption_key, "user-1", "spotify-user-1", "access-tok", "refresh-tok", "user-top-read", 3600
    )
    assert saved.spotify_user_id == "spotify-user-1"
    assert saved.scope == "user-top-read"
    assert not hasattr(saved, "access_token")
    assert not hasattr(saved, "refresh_token")

    fetched = spotify_storage.get_connection(db_path, "user-1")
    assert fetched is not None
    assert fetched.spotify_user_id == "spotify-user-1"


def test_save_connection_upsert_ersetzt_ohne_duplikat(db_path, encryption_key):
    first = spotify_storage.save_connection(
        db_path, encryption_key, "user-1", "spotify-user-1", "access-tok", "refresh-tok", "user-top-read", 3600
    )
    second = spotify_storage.save_connection(
        db_path, encryption_key, "user-1", "spotify-user-1", "access-tok-2", "refresh-tok-2", "user-top-read", 3600
    )
    assert second.connected_at == first.connected_at


def test_delete_connection_entfernt_verbindung(db_path, encryption_key):
    spotify_storage.save_connection(
        db_path, encryption_key, "user-1", "spotify-user-1", "access-tok", "refresh-tok", "user-top-read", 3600
    )
    spotify_storage.delete_connection(db_path, "user-1")
    assert spotify_storage.get_connection(db_path, "user-1") is None


def test_ensure_valid_access_token_nicht_verbunden_gibt_none(db_path, encryption_key):
    assert spotify_storage.ensure_valid_access_token(db_path, encryption_key, "cid", "csecret", "user-1") is None


def test_ensure_valid_access_token_nicht_abgelaufen_kein_refresh_call(db_path, encryption_key, monkeypatch):
    spotify_storage.save_connection(
        db_path, encryption_key, "user-1", "spotify-user-1", "access-tok", "refresh-tok", "user-top-read", 3600
    )

    def _fail(*args, **kwargs):
        raise AssertionError("refresh_access_token darf hier nicht aufgerufen werden")

    monkeypatch.setattr(spotify_oauth_client, "refresh_access_token", _fail)

    token = spotify_storage.ensure_valid_access_token(db_path, encryption_key, "cid", "csecret", "user-1")
    assert token == "access-tok"


def test_ensure_valid_access_token_abgelaufen_refresht_und_persistiert(db_path, encryption_key, monkeypatch):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO spotify_connections
                (user_id, spotify_user_id, access_token_encrypted, refresh_token_encrypted, scope,
                 expires_at, connected_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "user-1",
                "spotify-user-1",
                spotify_storage._encrypt(encryption_key, "old-access"),
                spotify_storage._encrypt(encryption_key, "old-refresh"),
                "user-top-read",
                (datetime.now() - timedelta(seconds=1)).isoformat(),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )

    calls = []

    def _fake_refresh(client_id, client_secret, refresh_token):
        calls.append((client_id, client_secret, refresh_token))
        return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}

    monkeypatch.setattr(spotify_oauth_client, "refresh_access_token", _fake_refresh)

    token = spotify_storage.ensure_valid_access_token(db_path, encryption_key, "cid", "csecret", "user-1")
    assert token == "new-access"
    assert calls == [("cid", "csecret", "old-refresh")]

    fetched = spotify_storage.get_connection(db_path, "user-1")
    assert fetched is not None
    assert spotify_storage._decrypt(encryption_key, _access_token_encrypted(db_path, "user-1")) == "new-access"


def _access_token_encrypted(db_path, user_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT access_token_encrypted FROM spotify_connections WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row[0]
