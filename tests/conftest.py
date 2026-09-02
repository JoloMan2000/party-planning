"""Gemeinsame pytest-Fixtures für die party_engine Testsuite.

Lädt den ECHTEN Katalog aus ``catalog/*.json`` (kein Mocking, siehe
AUFGABE §43) genau einmal pro Testsession.
"""

from __future__ import annotations

import uuid

import pytest

from party_engine.catalog import load_catalog
from party_engine.domain import PartyConfig


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture()
def config():
    return PartyConfig()


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """FastAPI ``TestClient`` mit ``settings.db_path`` auf eine isolierte
    ``tmp_path``-SQLite-DB umgebogen (Phase-1-Plan Schritt 7) - berührt nie
    die echte Dev-``responses.db``. ``settings.db_path`` wird gepatcht (statt
    nur die ``get_db_path``-Dependency zu überschreiben), da das Startup-Event
    in ``backend/app/main.py`` direkt ``settings.db_path`` liest, nicht die
    Dependency."""
    from backend.app.core.config import settings
    from backend.app.main import app
    from starlette.testclient import TestClient

    db_path = tmp_path / "responses.db"
    monkeypatch.setattr(settings, "db_path", db_path)

    with TestClient(app) as client:
        client.db_path = db_path
        yield client


@pytest.fixture()
def admin_headers():
    """Die 7 Legacy-``admin_*``-Router sind seit dem Account-basierten Pivot
    (Phase 1, Entscheidung #2 "clean break") absichtlich unauthentifiziert -
    ``get_current_admin``/``settings.admin_password`` existieren nicht mehr.
    Diese Fixture liefert daher bewusst leere Headers, bis eine spätere Phase
    Admin-Zugriff auf dem neuen Rollenmodell neu aufbaut."""
    return {}


@pytest.fixture()
def user_factory(api_client):
    """Legt einen echten User via ``POST /auth/signup`` an (kein direktes
    DB-Seeding/Token-Forging) und liefert die volle Token-Response
    (``access_token``, ``refresh_token``, ``user``)."""

    def _make_user(email: str | None = None, display_name: str = "Test User", password: str = "testpassword123") -> dict:
        email = email or f"user-{uuid.uuid4().hex}@example.com"
        resp = api_client.post(
            "/api/v1/auth/signup", json={"email": email, "password": password, "display_name": display_name}
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_user


@pytest.fixture()
def auth_headers_factory(user_factory):
    """Liefert ``(headers, user, refresh_token)`` für einen frisch angelegten
    User - der übliche Fall in API-Tests, die nur die Auth-Headers brauchen."""

    def _make_headers(
        email: str | None = None, display_name: str = "Test User", password: str = "testpassword123"
    ) -> tuple[dict, dict, str]:
        token_response = user_factory(email=email, display_name=display_name, password=password)
        headers = {"Authorization": f"Bearer {token_response['access_token']}"}
        return headers, token_response["user"], token_response["refresh_token"]

    return _make_headers
