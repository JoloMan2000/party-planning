"""API-Tests für Admin-JWT-Auth (Phase-1-Plan Schritt 7).

Deckt ab: falsches Passwort -> 401, korrektes Passwort -> 200 + JWT, sowie
dass jede ``admin_*``-Route ohne Token mit 401 abgelehnt wird (All-or-Nothing-
Gate, mirroring der heutigen ``is_admin``-Prüfung).
"""

from __future__ import annotations

import pytest

from backend.app.core.config import settings

ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/responses"),
    ("GET", "/api/v1/admin/responses/csv"),
    ("GET", "/api/v1/admin/party-settings"),
    ("GET", "/api/v1/admin/party-settings/event-types"),
    ("POST", "/api/v1/admin/party-settings"),
    ("GET", "/api/v1/admin/party-context"),
    ("POST", "/api/v1/admin/party-context"),
    ("GET", "/api/v1/admin/party-context/derived"),
    ("GET", "/api/v1/admin/party-context/overrides"),
    ("POST", "/api/v1/admin/party-context/overrides"),
    ("DELETE", "/api/v1/admin/party-context/overrides/some_key"),
    ("GET", "/api/v1/admin/catalog-curation"),
    ("POST", "/api/v1/admin/catalog-curation"),
    ("GET", "/api/v1/admin/recommendations"),
    ("GET", "/api/v1/admin/music/settings"),
    ("POST", "/api/v1/admin/music/settings"),
    ("GET", "/api/v1/admin/music/track-overrides"),
    ("POST", "/api/v1/admin/music/track-overrides"),
    ("GET", "/api/v1/admin/music/artist-overrides"),
    ("POST", "/api/v1/admin/music/artist-overrides"),
    ("POST", "/api/v1/admin/music/generate-playlist"),
    ("POST", "/api/v1/admin/shopping-list"),
]


def test_login_mit_falschem_passwort_gibt_401(api_client):
    resp = api_client.post("/api/v1/auth/admin/login", json={"password": "wrong"})
    assert resp.status_code == 401


def test_login_mit_korrektem_passwort_gibt_jwt(api_client):
    resp = api_client.post("/api/v1/auth/admin/login", json={"password": settings.admin_password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_route_ohne_token_gibt_401(api_client, method, path):
    resp = api_client.request(method, path)
    assert resp.status_code == 401


def test_admin_route_mit_gueltigem_token_ist_erlaubt(api_client, admin_headers):
    resp = api_client.get("/api/v1/admin/party-settings", headers=admin_headers)
    assert resp.status_code == 200
