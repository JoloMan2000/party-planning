"""API-Tests für /api/v1/catalogs/* (Onboarding-Spec, Phase 6) - öffentlich,
kein Auth nötig, stabile IDs."""

from __future__ import annotations

import pytest

_ENDPOINTS = [
    "/api/v1/catalogs/event-interests",
    "/api/v1/catalogs/music-genres",
    "/api/v1/catalogs/event-sizes",
    "/api/v1/catalogs/event-settings",
    "/api/v1/catalogs/interest-tags",
]


@pytest.mark.parametrize("endpoint", _ENDPOINTS)
def test_catalog_endpoint_ohne_auth_erreichbar(api_client, endpoint):
    resp = api_client.get(endpoint)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) > 0
    for item in body:
        assert "id" in item
        assert "label_de" in item
        assert "label_en" in item


def test_music_genre_catalog_ids_sind_stabil(api_client):
    resp = api_client.get("/api/v1/catalogs/music-genres")
    ids = {item["id"] for item in resp.json()}
    assert "tech_house" in ids
    assert "jazz" in ids


def test_event_interest_catalog_ids_sind_stabil(api_client):
    resp = api_client.get("/api/v1/catalogs/event-interests")
    ids = {item["id"] for item in resp.json()}
    assert "concert" in ids
    assert "festival" in ids
