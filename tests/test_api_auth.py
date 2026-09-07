"""API-Tests für Signup/Login/Refresh-Rotation/Logout (Account-basierter
Pivot, Phase 1, AUFGABE-Spec §85-95 - Backend-relevante Szenarien)."""

from __future__ import annotations

import pytest


def test_signup_gibt_201_und_token_paar(api_client):
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "newuser@example.com", "password": "Sup3rSecret!23", "display_name": "New User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "newuser@example.com"
    assert "password_hash" not in body["user"]
    assert "password" not in body["user"]


@pytest.mark.parametrize(
    "password",
    [
        "Short1!",  # < 12 Zeichen
        "lowercase123!",  # kein Großbuchstabe
        "UPPERCASE123!",  # kein Kleinbuchstabe
        "NoDigitsHere!!",  # keine Ziffer
        "NoSpecialChar123",  # kein Sonderzeichen
    ],
)
def test_signup_mit_schwachem_passwort_gibt_422(api_client, password):
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "weakpass@example.com", "password": password, "display_name": "Weak"},
    )
    assert resp.status_code == 422


def test_signup_mit_starkem_passwort_gibt_201(api_client):
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "strongpass@example.com", "password": "Str0ng!Passw0rd", "display_name": "Strong"},
    )
    assert resp.status_code == 201


def test_signup_mit_bereits_registrierter_email_gibt_409(api_client, user_factory):
    user_factory(email="dupe@example.com")
    resp = api_client.post(
        "/api/v1/auth/signup", json={"email": "dupe@example.com", "password": "Whatever!123", "display_name": "Dupe"}
    )
    assert resp.status_code == 409


def test_login_mit_falschem_passwort_gibt_401(api_client, user_factory):
    user_factory(email="loginfail@example.com", password="Correct-Passw0rd")
    resp = api_client.post("/api/v1/auth/login", json={"email": "loginfail@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_mit_unbekannter_email_gibt_401(api_client):
    resp = api_client.post("/api/v1/auth/login", json={"email": "unknown@example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_login_mit_korrekten_zugangsdaten_gibt_token_paar(api_client, user_factory):
    user_factory(email="loginok@example.com", password="Correct-Passw0rd")
    resp = api_client.post("/api/v1/auth/login", json={"email": "loginok@example.com", "password": "Correct-Passw0rd"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_refresh_rotiert_token_und_alter_wird_ungueltig(api_client, user_factory):
    tokens = user_factory(email="rotate@example.com")
    old_refresh_token = tokens["refresh_token"]

    resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != old_refresh_token

    # Wiederverwendung des alten (bereits rotierten) Refresh-Tokens -> 401 (Reuse-Detection)
    resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert resp.status_code == 401

    # Reuse-Detection widerruft ALLE Tokens des Users - auch der frisch rotierte ist jetzt tot
    resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert resp.status_code == 401


def test_refresh_mit_unbekanntem_token_gibt_401(api_client):
    resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


def test_logout_widerruft_refresh_token(api_client, user_factory):
    tokens = user_factory(email="logout@example.com")
    resp = api_client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 204

    resp = api_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


def test_login_wird_nach_max_fehlversuchen_gesperrt(api_client, user_factory):
    from backend.app.core.config import settings

    user_factory(email="bruteforce@example.com", password="Correct-Passw0rd")
    for _ in range(settings.login_tier1_max_attempts):
        resp = api_client.post(
            "/api/v1/auth/login", json={"email": "bruteforce@example.com", "password": "wrong"}
        )
        assert resp.status_code == 401

    # Selbst mit dem KORREKTEN Passwort bleibt der Account jetzt gesperrt.
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "bruteforce@example.com", "password": "Correct-Passw0rd"}
    )
    assert resp.status_code == 429


def test_login_sperre_gilt_identisch_fuer_unbekannte_email(api_client):
    """Verhindert E-Mail-Enumeration über das Lockout-Verhalten: eine nie
    registrierte Adresse wird nach den gleichen fehlgeschlagenen Versuchen
    genauso gesperrt wie eine echte."""
    from backend.app.core.config import settings

    for _ in range(settings.login_tier1_max_attempts):
        resp = api_client.post(
            "/api/v1/auth/login", json={"email": "never-registered@example.com", "password": "whatever123"}
        )
        assert resp.status_code == 401

    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "never-registered@example.com", "password": "whatever123"}
    )
    assert resp.status_code == 429


def test_login_erfolg_setzt_fehlversuch_zaehler_zurueck(api_client, user_factory):
    from backend.app.core.config import settings

    user_factory(email="resetcounter@example.com", password="Correct-Passw0rd")
    for _ in range(settings.login_tier1_max_attempts - 1):
        api_client.post("/api/v1/auth/login", json={"email": "resetcounter@example.com", "password": "wrong"})

    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "resetcounter@example.com", "password": "Correct-Passw0rd"}
    )
    assert resp.status_code == 200

    # Zähler wurde zurückgesetzt - ein einzelner erneuter Fehlversuch danach
    # löst noch keine Sperre aus.
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "resetcounter@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_login_ruft_verify_password_auch_fuer_unbekannte_email_auf(api_client, monkeypatch):
    """Security-Hardening-Pass: verhindert Timing-basierte E-Mail-Enumeration.
    Ohne Dummy-Hash würde `verify_password` (Argon2, absichtlich langsam) nur
    für tatsächlich registrierte E-Mails aufgerufen - ein Angreifer könnte über
    die Response-Zeit unterscheiden, ob ein Account existiert, selbst wenn der
    401-Body identisch aussieht. Dieser Test stellt sicher, dass der Aufruf
    IMMER passiert, mit dem vordefinierten Dummy-Hash als Vergleichswert."""
    import backend.app.routers.auth as auth_router

    calls = []
    original_verify_password = auth_router.verify_password

    def spy(password, password_hash):
        calls.append(password_hash)
        return original_verify_password(password, password_hash)

    monkeypatch.setattr(auth_router, "verify_password", spy)

    resp = api_client.post(
        "/api/v1/auth/login", json={"email": "never-called-verify@example.com", "password": "whatever123"}
    )
    assert resp.status_code == 401
    assert calls == [auth_router._DUMMY_PASSWORD_HASH]
