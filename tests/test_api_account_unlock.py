"""API-Tests für den 3-stufigen Login-Lockout (Tier 1/2/3) + den
E-Mail-Unlock-Flow für Tier 3 (dauerhafte Blockierung).

Mirrort die ``test_api_password_reset.py``-Mocking-Konvention für den
E-Mail-Versand. Tier-Übergänge werden erzwungen, indem ``locked_until``
direkt per SQL in die Vergangenheit gesetzt wird (wie im bisherigen
``test_login_sperre_laeuft_nach_ablauf_ab``), da die Testsuite nicht
tatsächlich 15 Minuten/1 Tag warten kann."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from accounts import email_sender


def _mock_unlock_email_sender(monkeypatch) -> list[tuple[str, str]]:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        email_sender,
        "send_account_unlock_email",
        lambda to_email, unlock_link: captured.append((to_email, unlock_link)),
    )
    return captured


def _extract_token(unlock_link: str) -> str:
    return unlock_link.rsplit("/", 1)[-1]


def _expire_lock(api_client, email: str) -> None:
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(api_client.db_path) as conn:
        conn.execute("UPDATE login_attempts SET locked_until = ? WHERE email = ?", (expired_at, email))


def _fail_logins(api_client, email: str, password: str, count: int) -> None:
    for _ in range(count):
        api_client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_tier1_sperre_nach_5_fehlversuchen(api_client, user_factory):
    user_factory(email="tier1@example.com", password="Correct-Passw0rd!23")

    # Die 5. Fehlanmeldung selbst setzt die Sperre, gibt aber noch 401 zurück
    # (der Lockout-Precheck läuft VOR dem Credential-Check derselben Anfrage,
    # siehe login()) - erst der NÄCHSTE Versuch sieht die aktive Sperre.
    _fail_logins(api_client, "tier1@example.com", "wrong-pw", 5)
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "tier1@example.com", "password": "wrong-pw"}
    )
    assert resp.status_code == 429

    # Auch das korrekte Passwort ist während der Sperre blockiert.
    still_locked = api_client.post(
        "/api/v1/auth/login", json={"email": "tier1@example.com", "password": "Correct-Passw0rd!23"}
    )
    assert still_locked.status_code == 429


def test_tier2_sperre_nach_ablauf_von_tier1_und_3_weiteren_fehlversuchen(api_client, user_factory):
    user_factory(email="tier2@example.com", password="Correct-Passw0rd!23")
    _fail_logins(api_client, "tier2@example.com", "wrong-pw", 5)
    _expire_lock(api_client, "tier2@example.com")

    _fail_logins(api_client, "tier2@example.com", "wrong-pw", 3)
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "tier2@example.com", "password": "wrong-pw"}
    )
    assert resp.status_code == 429


def test_tier3_permanente_blockierung_nach_ablauf_von_tier2_und_5_weiteren_fehlversuchen(
    api_client, user_factory
):
    user_factory(email="tier3@example.com", password="Correct-Passw0rd!23")
    _fail_logins(api_client, "tier3@example.com", "wrong-pw", 5)
    _expire_lock(api_client, "tier3@example.com")
    _fail_logins(api_client, "tier3@example.com", "wrong-pw", 3)
    _expire_lock(api_client, "tier3@example.com")

    _fail_logins(api_client, "tier3@example.com", "wrong-pw", 5)
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "tier3@example.com", "password": "wrong-pw"}
    )
    assert resp.status_code == 423

    # Erneutes "Ablaufen lassen" hat keinen Effekt - Tier 3 hat keinen
    # Auto-Ablauf, nur der Email-Unlock-Flow hilft.
    _expire_lock(api_client, "tier3@example.com")
    still_blocked = api_client.post(
        "/api/v1/auth/login", json={"email": "tier3@example.com", "password": "Correct-Passw0rd!23"}
    )
    assert still_blocked.status_code == 423


def test_unbekannte_email_durchlaeuft_identische_tier_eskalation(api_client):
    email = "never-registered@example.com"
    _fail_logins(api_client, email, "wrong-pw", 5)
    resp1 = api_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw"})
    assert resp1.status_code == 429

    _expire_lock(api_client, email)
    _fail_logins(api_client, email, "wrong-pw", 3)
    resp2 = api_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw"})
    assert resp2.status_code == 429

    _expire_lock(api_client, email)
    _fail_logins(api_client, email, "wrong-pw", 5)
    resp3 = api_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw"})
    assert resp3.status_code == 423


def test_request_account_unlock_fuer_blockierten_echten_account(api_client, user_factory, monkeypatch):
    captured = _mock_unlock_email_sender(monkeypatch)
    user_factory(email="blocked@example.com", password="Correct-Passw0rd!23")
    _fail_logins(api_client, "blocked@example.com", "wrong-pw", 5)
    _expire_lock(api_client, "blocked@example.com")
    _fail_logins(api_client, "blocked@example.com", "wrong-pw", 3)
    _expire_lock(api_client, "blocked@example.com")
    _fail_logins(api_client, "blocked@example.com", "wrong-pw", 5)

    resp = api_client.post("/api/v1/auth/request-account-unlock", json={"email": "blocked@example.com"})
    assert resp.status_code == 200
    assert len(captured) == 1
    to_email, unlock_link = captured[0]
    assert to_email == "blocked@example.com"
    assert unlock_link.startswith("partyplanning://unlock/")


def test_request_account_unlock_fuer_unbekannte_email_gibt_identischen_200_ohne_email(
    api_client, monkeypatch
):
    captured = _mock_unlock_email_sender(monkeypatch)

    resp = api_client.post(
        "/api/v1/auth/request-account-unlock", json={"email": "unknown-unlock@example.com"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "If that account exists, an unlock link has been sent to its email address."

    known_body = api_client.post(
        "/api/v1/auth/request-account-unlock", json={"email": "another-unknown@example.com"}
    ).json()
    assert known_body == body
    assert captured == []


def test_request_account_unlock_fuer_nicht_blockierten_account_verschickt_trotzdem_email(
    api_client, user_factory, monkeypatch
):
    captured = _mock_unlock_email_sender(monkeypatch)
    user_factory(email="notblocked@example.com")

    resp = api_client.post("/api/v1/auth/request-account-unlock", json={"email": "notblocked@example.com"})
    assert resp.status_code == 200
    assert len(captured) == 1


def test_unlock_account_end_to_end(api_client, user_factory, monkeypatch):
    unlock_captured = _mock_unlock_email_sender(monkeypatch)
    tokens = user_factory(email="unlockflow@example.com", password="Correct-Passw0rd!23")
    old_refresh_token = tokens["refresh_token"]

    _fail_logins(api_client, "unlockflow@example.com", "wrong-pw", 5)
    _expire_lock(api_client, "unlockflow@example.com")
    _fail_logins(api_client, "unlockflow@example.com", "wrong-pw", 3)
    _expire_lock(api_client, "unlockflow@example.com")
    _fail_logins(api_client, "unlockflow@example.com", "wrong-pw", 5)

    blocked_resp = api_client.post(
        "/api/v1/auth/login", json={"email": "unlockflow@example.com", "password": "Correct-Passw0rd!23"}
    )
    assert blocked_resp.status_code == 423

    api_client.post("/api/v1/auth/request-account-unlock", json={"email": "unlockflow@example.com"})
    _to_email, unlock_link = unlock_captured[0]
    unlock_token = _extract_token(unlock_link)

    confirm_resp = api_client.post("/api/v1/auth/unlock-account", json={"token": unlock_token})
    assert confirm_resp.status_code == 204

    login_resp = api_client.post(
        "/api/v1/auth/login", json={"email": "unlockflow@example.com", "password": "Correct-Passw0rd!23"}
    )
    assert login_resp.status_code == 200

    # Unlock revoked KEINE Refresh-Tokens (anders als Password-Reset) - der
    # Token von vor der Blockierung funktioniert immer noch.
    refresh_resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert refresh_resp.status_code == 200


def test_unlock_account_mit_falsch_geformtem_token_gibt_400(api_client):
    resp = api_client.post("/api/v1/auth/unlock-account", json={"token": "no-colon-here"})
    assert resp.status_code == 400


def test_unlock_account_mit_unbekanntem_token_gibt_400(api_client):
    resp = api_client.post("/api/v1/auth/unlock-account", json={"token": "unknown-id:unknown-raw"})
    assert resp.status_code == 400


def test_unlock_account_mit_abgelaufenem_token_gibt_400(api_client, user_factory, monkeypatch):
    captured = _mock_unlock_email_sender(monkeypatch)
    user_factory(email="expiredunlock@example.com")
    api_client.post("/api/v1/auth/request-account-unlock", json={"email": "expiredunlock@example.com"})
    _to_email, unlock_link = captured[0]
    token = _extract_token(unlock_link)
    token_id = token.split(":", 1)[0]

    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(api_client.db_path) as conn:
        conn.execute("UPDATE account_unlock_tokens SET expires_at = ? WHERE id = ?", (expired_at, token_id))

    resp = api_client.post("/api/v1/auth/unlock-account", json={"token": token})
    assert resp.status_code == 400


def test_unlock_account_mit_bereits_verwendetem_token_gibt_400_beim_zweiten_versuch(
    api_client, user_factory, monkeypatch
):
    captured = _mock_unlock_email_sender(monkeypatch)
    user_factory(email="reusedunlock@example.com")
    api_client.post("/api/v1/auth/request-account-unlock", json={"email": "reusedunlock@example.com"})
    _to_email, unlock_link = captured[0]
    token = _extract_token(unlock_link)

    first = api_client.post("/api/v1/auth/unlock-account", json={"token": token})
    assert first.status_code == 204
    second = api_client.post("/api/v1/auth/unlock-account", json={"token": token})
    assert second.status_code == 400


def test_zweite_unlock_anfrage_invalidiert_die_erste(api_client, user_factory, monkeypatch):
    captured = _mock_unlock_email_sender(monkeypatch)
    user_factory(email="doubleunlock@example.com")

    api_client.post("/api/v1/auth/request-account-unlock", json={"email": "doubleunlock@example.com"})
    _to_email, first_link = captured[0]
    first_token = _extract_token(first_link)

    api_client.post("/api/v1/auth/request-account-unlock", json={"email": "doubleunlock@example.com"})
    assert len(captured) == 2

    resp = api_client.post("/api/v1/auth/unlock-account", json={"token": first_token})
    assert resp.status_code == 400
