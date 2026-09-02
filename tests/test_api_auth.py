"""API-Tests für Signup/Login/Refresh-Rotation/Logout (Account-basierter
Pivot, Phase 1, AUFGABE-Spec §85-95 - Backend-relevante Szenarien)."""

from __future__ import annotations


def test_signup_gibt_201_und_token_paar(api_client):
    resp = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "newuser@example.com", "password": "supersecret1", "display_name": "New User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "newuser@example.com"
    assert "password_hash" not in body["user"]
    assert "password" not in body["user"]


def test_signup_mit_bereits_registrierter_email_gibt_409(api_client, user_factory):
    user_factory(email="dupe@example.com")
    resp = api_client.post(
        "/api/v1/auth/signup", json={"email": "dupe@example.com", "password": "whatever123", "display_name": "Dupe"}
    )
    assert resp.status_code == 409


def test_login_mit_falschem_passwort_gibt_401(api_client, user_factory):
    user_factory(email="loginfail@example.com", password="correct-password")
    resp = api_client.post("/api/v1/auth/login", json={"email": "loginfail@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_mit_unbekannter_email_gibt_401(api_client):
    resp = api_client.post("/api/v1/auth/login", json={"email": "unknown@example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_login_mit_korrekten_zugangsdaten_gibt_token_paar(api_client, user_factory):
    user_factory(email="loginok@example.com", password="correct-password")
    resp = api_client.post("/api/v1/auth/login", json={"email": "loginok@example.com", "password": "correct-password"})
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
