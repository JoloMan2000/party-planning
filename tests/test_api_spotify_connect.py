"""API-Tests für /me/music-provider/spotify (connect/callback/status/disconnect)
(Onboarding-Spec, Phase 7). Alle Spotify-HTTP-Aufrufe sind gemockt
(``monkeypatch.setattr(spotify_oauth_client, ...)``) - kein echtes Netzwerk,
kein Live-Spotify-Developer-App nötig (siehe Plan, "Explicit deferrals")."""

from __future__ import annotations

import accounts.spotify_oauth_client as spotify_oauth_client


def _mock_token_exchange(monkeypatch, spotify_user_id: str = "spotify-user-1"):
    monkeypatch.setattr(
        spotify_oauth_client,
        "exchange_code_for_token",
        lambda client_id, client_secret, redirect_uri, code, code_verifier: {
            "access_token": "access-tok",
            "refresh_token": "refresh-tok",
            "scope": "user-top-read",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(spotify_oauth_client, "get_spotify_user_id", lambda access_token: spotify_user_id)


def test_connect_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/me/music-provider/spotify/connect")
    assert resp.status_code == 401


def test_connect_mit_auth_liefert_authorize_url(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.get("/api/v1/me/music-provider/spotify/connect", headers=headers)
    assert resp.status_code == 200
    authorize_url = resp.json()["authorize_url"]
    assert "client_id=" in authorize_url
    assert "code_challenge=" in authorize_url
    assert "state=" in authorize_url
    assert "scope=user-top-read" in authorize_url


def test_status_default_nicht_verbunden(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.get("/api/v1/me/music-provider/spotify/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["spotify_user_id"] is None


def test_callback_unbekannter_state_gibt_400(api_client):
    resp = api_client.get(
        "/api/v1/me/music-provider/spotify/callback", params={"state": "unknown-state", "code": "some-code"}
    )
    assert resp.status_code == 400


def test_callback_mit_error_gibt_cancelled_seite_ohne_connection(api_client, auth_headers_factory, monkeypatch):
    headers, _user, _refresh_token = auth_headers_factory()
    connect_resp = api_client.get("/api/v1/me/music-provider/spotify/connect", headers=headers)
    authorize_url = connect_resp.json()["authorize_url"]
    state = _extract_query_param(authorize_url, "state")

    resp = api_client.get(
        "/api/v1/me/music-provider/spotify/callback", params={"state": state, "error": "access_denied"}
    )
    assert resp.status_code == 200
    assert "cancelled" in resp.text.lower()

    status_resp = api_client.get("/api/v1/me/music-provider/spotify/status", headers=headers)
    assert status_resp.json()["connected"] is False


def test_callback_valider_flow_verbindet_und_status_zeigt_connected(api_client, auth_headers_factory, monkeypatch):
    headers, _user, _refresh_token = auth_headers_factory()
    connect_resp = api_client.get("/api/v1/me/music-provider/spotify/connect", headers=headers)
    authorize_url = connect_resp.json()["authorize_url"]
    state = _extract_query_param(authorize_url, "state")

    _mock_token_exchange(monkeypatch)

    resp = api_client.get(
        "/api/v1/me/music-provider/spotify/callback", params={"state": state, "code": "auth-code"}
    )
    assert resp.status_code == 200
    assert "connected" in resp.text.lower()

    status_resp = api_client.get("/api/v1/me/music-provider/spotify/status", headers=headers)
    status_body = status_resp.json()
    assert status_body["connected"] is True
    assert status_body["spotify_user_id"] == "spotify-user-1"


def test_callback_wiederverwendeter_state_gibt_400(api_client, auth_headers_factory, monkeypatch):
    headers, _user, _refresh_token = auth_headers_factory()
    connect_resp = api_client.get("/api/v1/me/music-provider/spotify/connect", headers=headers)
    authorize_url = connect_resp.json()["authorize_url"]
    state = _extract_query_param(authorize_url, "state")

    _mock_token_exchange(monkeypatch)

    first = api_client.get("/api/v1/me/music-provider/spotify/callback", params={"state": state, "code": "auth-code"})
    assert first.status_code == 200

    replayed = api_client.get("/api/v1/me/music-provider/spotify/callback", params={"state": state, "code": "auth-code"})
    assert replayed.status_code == 400


def test_disconnect_setzt_status_zurueck(api_client, auth_headers_factory, monkeypatch):
    headers, _user, _refresh_token = auth_headers_factory()
    connect_resp = api_client.get("/api/v1/me/music-provider/spotify/connect", headers=headers)
    authorize_url = connect_resp.json()["authorize_url"]
    state = _extract_query_param(authorize_url, "state")

    _mock_token_exchange(monkeypatch)
    api_client.get("/api/v1/me/music-provider/spotify/callback", params={"state": state, "code": "auth-code"})

    disconnect_resp = api_client.delete("/api/v1/me/music-provider/spotify/disconnect", headers=headers)
    assert disconnect_resp.status_code == 204

    status_resp = api_client.get("/api/v1/me/music-provider/spotify/status", headers=headers)
    assert status_resp.json()["connected"] is False


def test_zwei_user_isolation(api_client, auth_headers_factory, monkeypatch):
    headers_a, _user_a, _ = auth_headers_factory(email="spotify-a@example.com")
    headers_b, _user_b, _ = auth_headers_factory(email="spotify-b@example.com")

    connect_resp = api_client.get("/api/v1/me/music-provider/spotify/connect", headers=headers_a)
    authorize_url = connect_resp.json()["authorize_url"]
    state = _extract_query_param(authorize_url, "state")

    _mock_token_exchange(monkeypatch, spotify_user_id="spotify-user-a")
    api_client.get("/api/v1/me/music-provider/spotify/callback", params={"state": state, "code": "auth-code"})

    status_a = api_client.get("/api/v1/me/music-provider/spotify/status", headers=headers_a)
    status_b = api_client.get("/api/v1/me/music-provider/spotify/status", headers=headers_b)
    assert status_a.json()["connected"] is True
    assert status_b.json()["connected"] is False


def _extract_query_param(url: str, key: str) -> str:
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    return query[key][0]
