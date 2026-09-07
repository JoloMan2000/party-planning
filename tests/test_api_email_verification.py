"""API-Tests für den Email-Verification-Flow (verify-email +
resend-verification-email).

Mirrort exakt die ``test_api_password_reset.py``-Konventionen: E-Mail-Versand
wird per ``monkeypatch.setattr(email_sender, ...)`` gemockt (überschreibt die
autouse-No-Op-Fixture aus ``conftest.py`` gezielt für diese Tests, die den
tatsächlichen Link/Empfänger prüfen wollen), der Link wird in einer mutable
Liste eingefangen und der Token daraus extrahiert."""

from __future__ import annotations

from accounts import email_sender


def _mock_email_sender(monkeypatch) -> list[tuple[str, str]]:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        email_sender,
        "send_verification_email",
        lambda to_email, verify_link: captured.append((to_email, verify_link)),
    )
    return captured


def _extract_token(verify_link: str) -> str:
    # verify_link sieht aus wie "partyplanning://verify/{token_id}:{raw_token}"
    return verify_link.rsplit("/", 1)[-1]


def test_signup_verschickt_verification_email(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)

    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "newuser@example.com", "password": "TestPassw0rd!23", "display_name": "New User"},
    )
    assert resp.status_code == 201
    assert resp.json()["user"]["email_verified"] is False

    assert len(captured) == 1
    to_email, verify_link = captured[0]
    assert to_email == "newuser@example.com"
    assert verify_link.startswith("partyplanning://verify/")
    assert ":" in _extract_token(verify_link)


def test_verify_email_mit_validem_token_setzt_email_verified(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "verifyme@example.com", "password": "TestPassw0rd!23", "display_name": "Verify Me"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    _to_email, verify_link = captured[0]
    token = _extract_token(verify_link)

    confirm_resp = api_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert confirm_resp.status_code == 204

    me_resp = api_client.get("/api/v1/me", headers=headers)
    assert me_resp.json()["email_verified"] is True


def test_verify_email_mit_falsch_geformtem_token_gibt_400(api_client):
    resp = api_client.post("/api/v1/auth/verify-email", json={"token": "no-colon-here"})
    assert resp.status_code == 400


def test_verify_email_mit_unbekanntem_token_gibt_400(api_client):
    resp = api_client.post("/api/v1/auth/verify-email", json={"token": "unknown-id:unknown-raw"})
    assert resp.status_code == 400


def test_verify_email_mit_abgelaufenem_token_gibt_400(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    api_client.post(
        "/api/v1/auth/signup",
        json={"email": "expiredverify@example.com", "password": "TestPassw0rd!23", "display_name": "Expired"},
    )
    _to_email, verify_link = captured[0]
    token = _extract_token(verify_link)
    token_id = token.split(":", 1)[0]

    import sqlite3
    from datetime import datetime, timedelta, timezone

    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(api_client.db_path) as conn:
        conn.execute("UPDATE email_verification_tokens SET expires_at = ? WHERE id = ?", (expired_at, token_id))

    resp = api_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 400


def test_verify_email_mit_bereits_verwendetem_token_gibt_400_beim_zweiten_versuch(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    api_client.post(
        "/api/v1/auth/signup",
        json={"email": "reusedverify@example.com", "password": "TestPassw0rd!23", "display_name": "Reused"},
    )
    _to_email, verify_link = captured[0]
    token = _extract_token(verify_link)

    first = api_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 204

    second = api_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400


def test_resend_verification_email_fuer_unverifizierten_user(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "resend@example.com", "password": "TestPassw0rd!23", "display_name": "Resend"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    _to_email, old_link = captured[0]
    old_token = _extract_token(old_link)

    resend_resp = api_client.post("/api/v1/auth/resend-verification-email", headers=headers)
    assert resend_resp.status_code == 204
    assert len(captured) == 2

    # Alter Token ist jetzt ungültig (invalidiert durch den Resend)
    old_confirm = api_client.post("/api/v1/auth/verify-email", json={"token": old_token})
    assert old_confirm.status_code == 400

    # Neuer Token funktioniert
    _to_email, new_link = captured[1]
    new_token = _extract_token(new_link)
    new_confirm = api_client.post("/api/v1/auth/verify-email", json={"token": new_token})
    assert new_confirm.status_code == 204


def test_resend_verification_email_fuer_bereits_verifizierten_user_gibt_400(api_client, monkeypatch):
    captured = _mock_email_sender(monkeypatch)
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "alreadyverified@example.com", "password": "TestPassw0rd!23", "display_name": "AV"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    _to_email, verify_link = captured[0]
    token = _extract_token(verify_link)
    api_client.post("/api/v1/auth/verify-email", json={"token": token})

    resend_resp = api_client.post("/api/v1/auth/resend-verification-email", headers=headers)
    assert resend_resp.status_code == 400


def test_resend_verification_email_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/auth/resend-verification-email")
    assert resp.status_code == 401
