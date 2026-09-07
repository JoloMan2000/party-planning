"""API-Tests für die Organizer-Verification-Admin-Endpoints
(``/api/v1/admin/users/*``, ``backend/app/routers/admin_users.py``).

MVP-Admin-Gate: hardcoded ``ADMIN_EMAILS`` (siehe
``backend/app/core/auth.py::require_admin``), gemockt via
``monkeypatch.setattr(settings, "admin_emails", ...)`` - mirroring des
``monkeypatch.setattr(settings, "db_path", ...)``-Musters in
``conftest.py::api_client``."""

from __future__ import annotations

import pytest

from backend.app.core.config import settings

ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/users", None),
    ("POST", "/api/v1/admin/users/some-user-id/verify", None),
    ("DELETE", "/api/v1/admin/users/some-user-id/verify", None),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_admin_route_ohne_auth_gibt_401(api_client, method, path, body):
    resp = api_client.request(method, path, json=body)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_admin_route_als_nicht_admin_gibt_403(api_client, auth_headers_factory, method, path, body):
    headers, _user, _ = auth_headers_factory(email="notanadmin@example.com")
    resp = api_client.request(method, path, json=body, headers=headers)
    assert resp.status_code == 403


def test_admin_kann_user_auflisten(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="listadmin@example.com")
    _headers, user, _ = auth_headers_factory(email="listeduser@example.com")
    monkeypatch.setattr(settings, "admin_emails", "listadmin@example.com")

    resp = api_client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "listeduser@example.com" in emails
    assert next(u for u in resp.json() if u["id"] == user["id"])["is_verified"] is False


def test_admin_kann_user_verifizieren_und_wieder_entfernen(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="verifyadmin@example.com")
    _headers, user, _ = auth_headers_factory(email="toverifyuser@example.com")
    monkeypatch.setattr(settings, "admin_emails", "verifyadmin@example.com")

    verify_resp = api_client.post(f"/api/v1/admin/users/{user['id']}/verify", headers=admin_headers)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True

    unverify_resp = api_client.delete(f"/api/v1/admin/users/{user['id']}/verify", headers=admin_headers)
    assert unverify_resp.status_code == 200
    assert unverify_resp.json()["is_verified"] is False


def test_admin_verify_unbekannter_user_gibt_404(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="notfoundadmin@example.com")
    monkeypatch.setattr(settings, "admin_emails", "notfoundadmin@example.com")

    resp = api_client.post("/api/v1/admin/users/unknown-user-id/verify", headers=admin_headers)
    assert resp.status_code == 404

    resp = api_client.delete("/api/v1/admin/users/unknown-user-id/verify", headers=admin_headers)
    assert resp.status_code == 404


def test_admin_emails_ist_case_insensitive(api_client, auth_headers_factory, monkeypatch):
    admin_headers, _admin, _ = auth_headers_factory(email="CaseAdmin@example.com")
    monkeypatch.setattr(settings, "admin_emails", "caseadmin@example.com")

    resp = api_client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200
