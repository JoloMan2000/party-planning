"""API-Tests für die Organizer-Verification-Admin-Endpoints
(``/api/v1/admin/organizers/*``, ``backend/app/routers/admin_organizers.py``,
Social-Graph-Phase-4). Exakter struktureller Spiegel von
``tests/test_api_admin_users.py`` (dem LEGACY, jetzt funktional
abgelösten Verification-Flow)."""

from __future__ import annotations

import pytest

from backend.app.core.config import settings

ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/organizers", None),
    ("POST", "/api/v1/admin/organizers/some-organizer-id/verify", None),
    ("DELETE", "/api/v1/admin/organizers/some-organizer-id/verify", None),
]


def _create_organizer(api_client, headers, display_name="Acme Events"):
    resp = api_client.post("/api/v1/organizers", json={"display_name": display_name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_admin_route_ohne_auth_gibt_401(api_client, method, path, body):
    resp = api_client.request(method, path, json=body)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_admin_route_als_nicht_admin_gibt_403(api_client, auth_headers_factory, method, path, body):
    headers, _user, _ = auth_headers_factory(email="notanadmin-org@example.com")
    resp = api_client.request(method, path, json=body, headers=headers)
    assert resp.status_code == 403


def test_admin_kann_organizer_auflisten(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="listadmin-org@example.com")
    owner_headers, _owner, _ = auth_headers_factory(email="listedowner-org@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    monkeypatch.setattr(settings, "admin_emails", "listadmin-org@example.com")

    resp = api_client.get("/api/v1/admin/organizers", headers=admin_headers)
    assert resp.status_code == 200
    ids = {o["id"] for o in resp.json()}
    assert organizer["id"] in ids
    assert next(o for o in resp.json() if o["id"] == organizer["id"])["verification_status"] == "unverified"


def test_admin_kann_organizer_verifizieren_und_wieder_entfernen(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="verifyadmin-org@example.com")
    owner_headers, _owner, _ = auth_headers_factory(email="toverifyowner-org@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    monkeypatch.setattr(settings, "admin_emails", "verifyadmin-org@example.com")

    verify_resp = api_client.post(f"/api/v1/admin/organizers/{organizer['id']}/verify", headers=admin_headers)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verification_status"] == "verified"

    unverify_resp = api_client.delete(f"/api/v1/admin/organizers/{organizer['id']}/verify", headers=admin_headers)
    assert unverify_resp.status_code == 200
    assert unverify_resp.json()["verification_status"] == "unverified"


def test_admin_verify_unbekannter_organizer_gibt_404(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="notfoundadmin-org@example.com")
    monkeypatch.setattr(settings, "admin_emails", "notfoundadmin-org@example.com")

    resp = api_client.post("/api/v1/admin/organizers/unknown-organizer-id/verify", headers=admin_headers)
    assert resp.status_code == 404

    resp = api_client.delete("/api/v1/admin/organizers/unknown-organizer-id/verify", headers=admin_headers)
    assert resp.status_code == 404
