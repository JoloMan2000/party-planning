"""API-Tests für ``backend/app/routers/geo.py`` (``/api/v1/geo/suggest``,
``/retrieve``, ``/reverse``) - Auth-Pflicht (Spec §104), Mindestlänge (Spec
§11) und Provider-Fehler dürfen NIE zu einem 500 führen (Spec §97/§99)."""

from __future__ import annotations

import backend.app.core.deps as deps
from geo.domain import GeoSuggestion


class _RaisingProvider:
    def suggest(self, query, context):
        raise RuntimeError("provider down")

    def retrieve(self, provider_place_id, context):
        raise RuntimeError("provider down")

    def reverse_geocode(self, point):
        raise RuntimeError("provider down")


class _StubProvider:
    def suggest(self, query, context):
        return [
            GeoSuggestion(
                provider_place_id="1", primary_text="Ballindamm", secondary_text="Hamburg",
                place_type="street", provider="nominatim",
            )
        ]

    def retrieve(self, provider_place_id, context):
        return None

    def reverse_geocode(self, point):
        return None


def _override_provider(api_client, provider):
    from backend.app.main import app

    app.dependency_overrides[deps.get_geo_search_provider] = lambda: provider
    return app


def test_suggest_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/geo/suggest", params={"query": "Hamburg"})
    assert resp.status_code == 401


def test_suggest_zu_kurzer_query_gibt_leere_liste(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="geosuggestshort@example.com")
    resp = api_client.get("/api/v1/geo/suggest", params={"query": "a"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []


def test_suggest_erfolgreich(api_client, auth_headers_factory):
    app = _override_provider(api_client, _StubProvider())
    try:
        headers, _user, _ = auth_headers_factory(email="geosuggestok@example.com")
        resp = api_client.get("/api/v1/geo/suggest", params={"query": "Ballindamm"}, headers=headers)
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["provider_place_id"] == "1"
    finally:
        app.dependency_overrides.pop(deps.get_geo_search_provider, None)


def test_suggest_provider_fehler_gibt_leere_liste_kein_500(api_client, auth_headers_factory):
    app = _override_provider(api_client, _RaisingProvider())
    try:
        headers, _user, _ = auth_headers_factory(email="geosuggestdown@example.com")
        resp = api_client.get("/api/v1/geo/suggest", params={"query": "Hamburg"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []
    finally:
        app.dependency_overrides.pop(deps.get_geo_search_provider, None)


def test_retrieve_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/geo/retrieve", json={"provider_place_id": "1"})
    assert resp.status_code == 401


def test_retrieve_provider_fehler_gibt_none_kein_500(api_client, auth_headers_factory):
    app = _override_provider(api_client, _RaisingProvider())
    try:
        headers, _user, _ = auth_headers_factory(email="georetrievedown@example.com")
        resp = api_client.post("/api/v1/geo/retrieve", json={"provider_place_id": "1"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json() is None
    finally:
        app.dependency_overrides.pop(deps.get_geo_search_provider, None)


def test_retrieve_leere_provider_place_id_gibt_422(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="georetrieveempty@example.com")
    resp = api_client.post("/api/v1/geo/retrieve", json={"provider_place_id": "  "}, headers=headers)
    assert resp.status_code == 422


def test_reverse_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/geo/reverse", json={"latitude": 53.5, "longitude": 9.9})
    assert resp.status_code == 401


def test_reverse_provider_fehler_gibt_none_kein_500(api_client, auth_headers_factory):
    app = _override_provider(api_client, _RaisingProvider())
    try:
        headers, _user, _ = auth_headers_factory(email="georeversedown@example.com")
        resp = api_client.post(
            "/api/v1/geo/reverse", json={"latitude": 53.5, "longitude": 9.9}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json() is None
    finally:
        app.dependency_overrides.pop(deps.get_geo_search_provider, None)
