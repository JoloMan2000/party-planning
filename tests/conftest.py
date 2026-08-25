"""Gemeinsame pytest-Fixtures für die party_engine Testsuite.

Lädt den ECHTEN Katalog aus ``catalog/*.json`` (kein Mocking, siehe
AUFGABE §43) genau einmal pro Testsession.
"""

from __future__ import annotations

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
def admin_token(api_client):
    """Gültiges Admin-JWT via echten Login-Endpunkt (mirroring des
    Passwort-Login-Flows, kein direktes Token-Forging)."""
    from backend.app.core.config import settings

    resp = api_client.post("/api/v1/auth/admin/login", json={"password": settings.admin_password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
