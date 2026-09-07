"""API-Tests für den Forgot-Password-Flow (request-password-reset +
reset-password).

Mockt ``accounts.email_sender.send_password_reset_email`` komplett
(``monkeypatch.setattr(email_sender, ...)``) - kein echtes SMTP im Test,
mirroring die ``spotify_oauth_client``-Mocking-Konvention aus
``test_api_spotify_connect.py``. Der Reset-Link wird in einer mutable
Liste eingefangen, damit Tests den Token daraus extrahieren können (es
gibt kein echtes Postfach zu lesen)."""

from __future__ import annotations

from accounts import email_sender


def _mock_email_sender(monkeypatch) -> list[tuple[str, str]]:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        email_sender,
        "send_password_reset_email",
        lambda to_email, reset_link: captured.append((to_email, reset_link)),
    )
    return captured


def _extract_token(reset_link: str) -> str:
    # reset_link sieht aus wie "partyplanning://reset/{token_id}:{raw_token}"
    return reset_link.rsplit("/", 1)[-1]


def test_request_reset_mit_bekannter_email_gibt_200_und_ruft_email_sender(
    api_client, user_factory, monkeypatch
):
    captured = _mock_email_sender(monkeypatch)
    user_factory(email="known@example.com")

    resp = api_client.post("/api/v1/auth/request-password-reset", json={"email": "known@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body

    assert len(captured) == 1
    to_email, reset_link = captured[0]
    assert to_email == "known@example.com"
    assert reset_link.startswith("partyplanning://reset/")
    assert ":" in _extract_token(reset_link)


def test_request_reset_mit_unbekannter_email_gibt_identischen_200(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)

    resp = api_client.post("/api/v1/auth/request-password-reset", json={"email": "unknown@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "If that email is registered, a password reset link has been sent."

    known_resp = api_client.post("/api/v1/auth/request-password-reset", json={"email": "unknown@example.com"})
    assert known_resp.json() == body

    assert captured == []


def test_reset_mit_validem_token_funktioniert_end_to_end(api_client, user_factory, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    tokens = user_factory(email="reset-flow@example.com", password="Old-Passw0rd!23")
    old_refresh_token = tokens["refresh_token"]

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "reset-flow@example.com"})
    _to_email, reset_link = captured[0]
    reset_token = _extract_token(reset_link)

    resp = api_client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "New-Passw0rd!23"}
    )
    assert resp.status_code == 204

    # Alter Refresh-Token ist nach dem Reset widerrufen (force re-login überall)
    refresh_resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert refresh_resp.status_code == 401

    # Login mit neuem Passwort funktioniert
    login_resp = api_client.post(
        "/api/v1/auth/login", json={"email": "reset-flow@example.com", "password": "New-Passw0rd!23"}
    )
    assert login_resp.status_code == 200

    # Login mit altem Passwort funktioniert nicht mehr
    old_login_resp = api_client.post(
        "/api/v1/auth/login", json={"email": "reset-flow@example.com", "password": "Old-Passw0rd!23"}
    )
    assert old_login_resp.status_code == 401


def test_reset_mit_abgelaufenem_token_gibt_400(api_client, user_factory, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    user_factory(email="expired@example.com")

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "expired@example.com"})
    _to_email, reset_link = captured[0]
    reset_token = _extract_token(reset_link)
    token_id = reset_token.split(":", 1)[0]

    # Ablaufzeit direkt in der DB in die Vergangenheit setzen
    import sqlite3
    from datetime import datetime, timedelta, timezone

    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(api_client.db_path) as conn:
        conn.execute("UPDATE password_reset_tokens SET expires_at = ? WHERE id = ?", (expired_at, token_id))

    resp = api_client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "New-Passw0rd!23"}
    )
    assert resp.status_code == 400


def test_reset_mit_bereits_verwendetem_token_gibt_400_beim_zweiten_versuch(
    api_client, user_factory, monkeypatch
):
    captured = _mock_email_sender(monkeypatch)
    user_factory(email="reused@example.com")

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "reused@example.com"})
    _to_email, reset_link = captured[0]
    reset_token = _extract_token(reset_link)

    first = api_client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "New-Passw0rd!23"}
    )
    assert first.status_code == 204

    second = api_client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "Another-Passw0rd!23"}
    )
    assert second.status_code == 400


def test_reset_mit_falsch_geformtem_token_gibt_400(api_client):
    resp = api_client.post(
        "/api/v1/auth/reset-password", json={"token": "no-colon-here", "new_password": "New-Passw0rd!23"}
    )
    assert resp.status_code == 400


def test_reset_mit_gleichem_passwort_gibt_400_und_lässt_passwort_unveraendert(
    api_client, user_factory, monkeypatch
):
    captured = _mock_email_sender(monkeypatch)
    user_factory(email="samepass@example.com", password="Same-Passw0rd!23")

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "samepass@example.com"})
    _to_email, reset_link = captured[0]
    reset_token = _extract_token(reset_link)

    resp = api_client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "Same-Passw0rd!23"}
    )
    assert resp.status_code == 400

    login_resp = api_client.post(
        "/api/v1/auth/login", json={"email": "samepass@example.com", "password": "Same-Passw0rd!23"}
    )
    assert login_resp.status_code == 200


def test_reset_mit_schwachem_passwort_gibt_422(api_client, user_factory, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    user_factory(email="weakreset@example.com")

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "weakreset@example.com"})
    _to_email, reset_link = captured[0]
    reset_token = _extract_token(reset_link)

    resp = api_client.post("/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "weak"})
    assert resp.status_code == 422


def test_zweite_reset_anfrage_invalidiert_die_erste(api_client, user_factory, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    user_factory(email="doublerequest@example.com")

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "doublerequest@example.com"})
    _to_email, first_link = captured[0]
    first_token = _extract_token(first_link)

    api_client.post("/api/v1/auth/request-password-reset", json={"email": "doublerequest@example.com"})
    assert len(captured) == 2

    resp = api_client.post(
        "/api/v1/auth/reset-password", json={"token": first_token, "new_password": "New-Passw0rd!23"}
    )
    assert resp.status_code == 400
