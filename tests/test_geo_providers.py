"""Tests für ``geo/providers.py`` - nie echte Netzwerk-Calls (``requests``
wird immer per ``monkeypatch`` ersetzt). Deckt das "nie raisen"-Kontrakt
(Spec §97), den Suggest->Retrieve-Cache (Spec §70-71) und die
Provider-Auswahl-Factory ab."""

from __future__ import annotations

import pytest

import geo.providers as providers
from geo.domain import GeoPoint, GeoSearchContext
from geo.providers import (
    GooglePlacesSearchProvider,
    NominatimGeoSearchProvider,
    NullGeoSearchProvider,
    get_default_geo_search_provider,
)


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Settings:
    def __init__(self, google_places_api_key: str = ""):
        self.google_places_api_key = google_places_api_key


# --- NullGeoSearchProvider -------------------------------------------------


def test_null_provider_suggest_ist_immer_leer():
    provider = NullGeoSearchProvider()
    assert provider.suggest("Hamburg", GeoSearchContext()) == []


def test_null_provider_retrieve_ist_immer_none():
    provider = NullGeoSearchProvider()
    assert provider.retrieve("anything", GeoSearchContext()) is None


def test_null_provider_reverse_geocode_ist_immer_none():
    provider = NullGeoSearchProvider()
    assert provider.reverse_geocode(GeoPoint(latitude=1.0, longitude=1.0)) is None


# --- get_default_geo_search_provider ---------------------------------------


def test_factory_waehlt_nominatim_ohne_key():
    provider = get_default_geo_search_provider(_Settings())
    assert isinstance(provider, NominatimGeoSearchProvider)


def test_factory_waehlt_google_mit_key():
    provider = get_default_geo_search_provider(_Settings(google_places_api_key="secret"))
    assert isinstance(provider, GooglePlacesSearchProvider)


# --- NominatimGeoSearchProvider ---------------------------------------------


def test_nominatim_suggest_leerer_query_macht_keinen_call(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("requests.get darf bei leerem Query nicht aufgerufen werden")

    monkeypatch.setattr(providers.requests, "get", _boom)
    provider = NominatimGeoSearchProvider()
    assert provider.suggest("   ", GeoSearchContext()) == []


def test_nominatim_suggest_parst_ergebnisse_und_befuellt_cache(monkeypatch):
    payload = [
        {
            "place_id": 12345,
            "name": "Ballindamm",
            "type": "road",
            "class": "highway",
            "lat": "53.5511",
            "lon": "9.9937",
            "display_name": "Ballindamm, Hamburg, Deutschland",
            "address": {"road": "Ballindamm", "city": "Hamburg", "country": "Deutschland", "country_code": "de"},
        }
    ]
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse(payload))

    provider = NominatimGeoSearchProvider()
    suggestions = provider.suggest("Ballindamm", GeoSearchContext())

    assert len(suggestions) == 1
    assert suggestions[0].provider_place_id == "12345"
    assert suggestions[0].provider == "nominatim"

    # retrieve() ist ein Cache-Lookup, KEIN zweiter Netzwerk-Call.
    monkeypatch.setattr(
        providers.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("kein Netzwerk erwartet"))
    )
    place = provider.retrieve("12345", GeoSearchContext())
    assert place is not None
    assert place.address.city == "Hamburg"
    assert place.point == GeoPoint(latitude=53.5511, longitude=9.9937)


def test_nominatim_retrieve_ohne_cache_treffer_gibt_none():
    provider = NominatimGeoSearchProvider()
    assert provider.retrieve("unbekannt", GeoSearchContext()) is None


def test_nominatim_suggest_bei_netzwerkfehler_gibt_leere_liste(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(providers.requests, "get", _boom)
    provider = NominatimGeoSearchProvider()
    assert provider.suggest("Hamburg", GeoSearchContext()) == []


def test_nominatim_reverse_geocode_bei_fehler_gibt_none(monkeypatch):
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    provider = NominatimGeoSearchProvider()
    assert provider.reverse_geocode(GeoPoint(latitude=1.0, longitude=1.0)) is None


def test_nominatim_reverse_geocode_erfolgreich(monkeypatch):
    payload = {
        "place_id": 999,
        "name": "Elbphilharmonie",
        "type": "building",
        "class": "amenity",
        "display_name": "Elbphilharmonie, Hamburg, Deutschland",
        "address": {"city": "Hamburg", "country": "Deutschland", "country_code": "de"},
    }
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse(payload))
    provider = NominatimGeoSearchProvider()
    place = provider.reverse_geocode(GeoPoint(latitude=53.5, longitude=9.9))
    assert place is not None
    assert place.address.city == "Hamburg"


def test_nominatim_reverse_geocode_error_key_gibt_none(monkeypatch):
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse({"error": "Unable to geocode"}))
    provider = NominatimGeoSearchProvider()
    assert provider.reverse_geocode(GeoPoint(latitude=0.0, longitude=0.0)) is None


# --- GooglePlacesSearchProvider ---------------------------------------------


def test_google_suggest_parst_predictions(monkeypatch):
    payload = {
        "predictions": [
            {
                "place_id": "abc123",
                "description": "Ballindamm, Hamburg, Germany",
                "structured_formatting": {"main_text": "Ballindamm", "secondary_text": "Hamburg, Germany"},
                "types": ["route"],
            }
        ]
    }
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse(payload))
    provider = GooglePlacesSearchProvider(api_key="key")
    suggestions = provider.suggest("Ballindamm", GeoSearchContext(search_session_id="sess-1"))
    assert len(suggestions) == 1
    assert suggestions[0].provider == "google_places"
    assert suggestions[0].primary_text == "Ballindamm"


def test_google_suggest_bei_fehler_gibt_leere_liste(monkeypatch):
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    provider = GooglePlacesSearchProvider(api_key="key")
    assert provider.suggest("Hamburg", GeoSearchContext()) == []


def test_google_retrieve_parst_details(monkeypatch):
    payload = {
        "result": {
            "name": "Elbphilharmonie",
            "formatted_address": "Platz der Deutschen Einheit 1, 20457 Hamburg, Germany",
            "geometry": {"location": {"lat": 53.5411, "lng": 9.9844}},
            "address_components": [
                {"long_name": "Hamburg", "short_name": "HH", "types": ["locality"]},
                {"long_name": "Germany", "short_name": "DE", "types": ["country"]},
            ],
            "types": ["premise"],
        }
    }
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse(payload))
    provider = GooglePlacesSearchProvider(api_key="key")
    place = provider.retrieve("place-id", GeoSearchContext())
    assert place is not None
    assert place.address.city == "Hamburg"
    assert place.address.country_code == "DE"
    assert place.point == GeoPoint(latitude=53.5411, longitude=9.9844)


def test_google_retrieve_ohne_result_gibt_none(monkeypatch):
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse({}))
    provider = GooglePlacesSearchProvider(api_key="key")
    assert provider.retrieve("place-id", GeoSearchContext()) is None


def test_google_reverse_geocode_erfolgreich(monkeypatch):
    payload = {
        "results": [
            {
                "place_id": "rev-1",
                "formatted_address": "Hamburg, Germany",
                "geometry": {"location": {"lat": 53.55, "lng": 9.99}},
                "address_components": [{"long_name": "Hamburg", "short_name": "HH", "types": ["locality"]}],
                "types": ["locality"],
            }
        ]
    }
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse(payload))
    provider = GooglePlacesSearchProvider(api_key="key")
    place = provider.reverse_geocode(GeoPoint(latitude=53.55, longitude=9.99))
    assert place is not None
    assert place.address.city == "Hamburg"


def test_google_reverse_geocode_ohne_results_gibt_none(monkeypatch):
    monkeypatch.setattr(providers.requests, "get", lambda *a, **k: _FakeResponse({"results": []}))
    provider = GooglePlacesSearchProvider(api_key="key")
    assert provider.reverse_geocode(GeoPoint(latitude=0.0, longitude=0.0)) is None
