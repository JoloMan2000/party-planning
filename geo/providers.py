"""Such-Provider-Abstraktion der Geo Platform (Spec §7-9, §67-70).

Mirrort exakt das Muster aus ``party_context/geocoding.py``
(``NominatimGeocodingProvider``): ``requests``-Bibliothek, dedizierter
User-Agent, 5s-Timeout, NIE raisen - jeder Fehler liefert ein leeres/``None``-
Ergebnis, niemals eine Exception (Spec §97, Fallback-Sicherheitsnetz).

Business-Logik hängt nie direkt an einem Provider, sondern immer an der
``GeoSearchProvider``-Protocol - ``get_default_geo_search_provider()`` wählt
zur Laufzeit, mirroring das ``spotify_client_id``-Optional-Feature-Muster in
``backend/app/core/config.py``: ohne Konfiguration läuft alles mit dem
kostenlosen Nominatim-Adapter, sobald ``google_places_api_key`` gesetzt ist,
übernimmt automatisch Google Places."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Protocol

import requests

from geo.domain import GeoAddress, GeoPlace, GeoPoint, GeoSearchContext, GeoSuggestion, LocationPrecision

_logger = logging.getLogger(__name__)

_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "PartyPlanningApp/1.0 (geo-platform)"
_REQUEST_TIMEOUT_S = 5

_GOOGLE_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
_GOOGLE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

_CACHE_TTL_S = 5 * 60
_CACHE_MAX_SIZE = 512


class GeoSearchProvider(Protocol):
    """Gemeinsame Schnittstelle aller Such-Provider (Spec §7)."""

    def suggest(self, query: str, context: GeoSearchContext) -> list[GeoSuggestion]: ...

    def retrieve(self, provider_place_id: str, context: GeoSearchContext) -> GeoPlace | None: ...

    def reverse_geocode(self, point: GeoPoint) -> GeoPlace | None: ...


class NullGeoSearchProvider:
    """Absoluter Sicherheitsnetz-Fallback (Spec §97) - liefert immer leer/
    ``None``, wirft nie. Wird nie aktiv als Default gewählt (Nominatim braucht
    keinen Key), existiert aber als expliziter, testbarer Nullwert."""

    def suggest(self, query: str, context: GeoSearchContext) -> list[GeoSuggestion]:
        return []

    def retrieve(self, provider_place_id: str, context: GeoSearchContext) -> GeoPlace | None:
        return None

    def reverse_geocode(self, point: GeoPoint) -> GeoPlace | None:
        return None


class _TTLCache:
    """Winzige In-Process-Cache-Implementierung (5 Min TTL, kapazitätsbegrenzt,
    keine neue Abhängigkeit) - hält volle ``GeoPlace``-Objekte ab dem
    Suggest-Aufruf vor, damit ``retrieve()`` ein Cache-Lookup ist statt eines
    zweiten, Rate-Limit-kostenden Netzwerk-Calls (Spec §70-71: Provider-
    Payloads werden nicht über diesen kurzlebigen Cache hinaus persistiert,
    nur die final bestätigte ``PartyLocation`` landet in der DB)."""

    def __init__(self, ttl_s: float = _CACHE_TTL_S, max_size: int = _CACHE_MAX_SIZE) -> None:
        self._ttl_s = ttl_s
        self._max_size = max_size
        self._store: dict[str, tuple[float, GeoPlace]] = {}

    def get(self, key: str) -> GeoPlace | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: GeoPlace) -> None:
        if len(self._store) >= self._max_size:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]
        self._store[key] = (time.monotonic() + self._ttl_s, value)


def _parse_nominatim_address(raw: dict) -> GeoAddress:
    addr = raw.get("address", {}) or {}
    return GeoAddress(
        street=addr.get("road"),
        house_number=addr.get("house_number"),
        postal_code=addr.get("postcode"),
        city=addr.get("city") or addr.get("town") or addr.get("village"),
        district=addr.get("suburb") or addr.get("city_district"),
        region=addr.get("state"),
        country_code=(addr.get("country_code") or "").upper() or None,
        country_name=addr.get("country"),
        formatted_address=raw.get("display_name", ""),
    )


def _nominatim_precision(place_class: str, place_type: str) -> LocationPrecision:
    if place_type in {"house", "building"}:
        return LocationPrecision.EXACT
    if place_class == "highway":
        return LocationPrecision.STREET
    if place_type in {"suburb", "neighbourhood", "quarter"}:
        return LocationPrecision.NEIGHBORHOOD
    if place_type in {"city", "town", "village", "administrative"}:
        return LocationPrecision.CITY
    return LocationPrecision.APPROXIMATE


class NominatimGeoSearchProvider:
    """Kostenlose OpenStreetMap-Nominatim-Anbindung, Zero-Config-Default
    (Spec §67, mirroring ``party_context/geocoding.py``). Muss NIE raisen -
    jeder Fehler (Netzwerk/Timeout/kein Treffer/unerwartetes JSON) liefert
    ein leeres Ergebnis. Fehler-Logs enthalten NIE die rohe Such-Anfrage
    oder Adresse (Spec §65-66), nur den Provider-Namen."""

    def __init__(self) -> None:
        self._cache = _TTLCache()

    def suggest(self, query: str, context: GeoSearchContext) -> list[GeoSuggestion]:
        if not query or not query.strip():
            return []
        params: dict[str, object] = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": 8,
        }
        if context.bias_country_code:
            params["countrycodes"] = context.bias_country_code
        if context.language:
            params["accept-language"] = context.language
        try:
            resp = requests.get(
                _NOMINATIM_SEARCH_URL,
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=_REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            results = resp.json()
        except Exception:
            _logger.warning("suggest failed provider=nominatim")
            return []

        suggestions: list[GeoSuggestion] = []
        for raw in results:
            place_id = str(raw.get("place_id") or "")
            if not place_id:
                continue
            address = _parse_nominatim_address(raw)
            point = None
            try:
                if raw.get("lat") is not None and raw.get("lon") is not None:
                    point = GeoPoint(latitude=float(raw["lat"]), longitude=float(raw["lon"]))
            except (TypeError, ValueError):
                point = None
            place_type = raw.get("type", "")
            place = GeoPlace(
                id=place_id,
                name=raw.get("name") or address.formatted_address,
                place_type=place_type,
                address=address,
                point=point,
                provider="nominatim",
                provider_place_id=place_id,
                precision=_nominatim_precision(raw.get("class", ""), place_type),
            )
            self._cache.set(place_id, place)

            primary = raw.get("name") or (address.street or address.city or address.formatted_address)
            suggestions.append(
                GeoSuggestion(
                    provider_place_id=place_id,
                    primary_text=primary or address.formatted_address,
                    secondary_text=address.formatted_address,
                    place_type=place_type,
                    provider="nominatim",
                )
            )
        return suggestions

    def retrieve(self, provider_place_id: str, context: GeoSearchContext) -> GeoPlace | None:
        return self._cache.get(provider_place_id)

    def reverse_geocode(self, point: GeoPoint) -> GeoPlace | None:
        try:
            resp = requests.get(
                _NOMINATIM_REVERSE_URL,
                params={"lat": point.latitude, "lon": point.longitude, "format": "json", "addressdetails": 1},
                headers={"User-Agent": _USER_AGENT},
                timeout=_REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            raw = resp.json()
        except Exception:
            _logger.warning("reverse_geocode failed provider=nominatim")
            return None

        if not raw or raw.get("error"):
            return None
        place_id = str(raw.get("place_id") or "")
        address = _parse_nominatim_address(raw)
        place_type = raw.get("type", "")
        return GeoPlace(
            id=place_id or str(uuid.uuid4()),
            name=raw.get("name") or address.formatted_address,
            place_type=place_type,
            address=address,
            point=point,
            provider="nominatim",
            provider_place_id=place_id,
            precision=_nominatim_precision(raw.get("class", ""), place_type),
        )


class GooglePlacesSearchProvider:
    """Google-Places-Anbindung ("professionelle Apps"-Antwort auf die
    User-Rückfrage) - aktiviert sich automatisch, sobald
    ``settings.google_places_api_key`` gesetzt ist (siehe
    ``get_default_geo_search_provider``). Reicht ``search_session_id`` als
    Googles offiziellen ``sessiontoken`` durch (echte Kosten-Ersparnis-
    Semantik, Spec §13/§139). Muss NIE raisen, analog Nominatim."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def suggest(self, query: str, context: GeoSearchContext) -> list[GeoSuggestion]:
        if not query or not query.strip():
            return []
        params: dict[str, object] = {"input": query, "key": self._api_key}
        if context.search_session_id:
            params["sessiontoken"] = context.search_session_id
        if context.bias_country_code:
            params["components"] = f"country:{context.bias_country_code.lower()}"
        if context.language:
            params["language"] = context.language
        if context.bias_point:
            params["location"] = f"{context.bias_point.latitude},{context.bias_point.longitude}"
            params["radius"] = 50000
        try:
            resp = requests.get(_GOOGLE_AUTOCOMPLETE_URL, params=params, timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            body = resp.json()
        except Exception:
            _logger.warning("suggest failed provider=google_places")
            return []

        predictions = body.get("predictions", []) or []
        suggestions = []
        for pred in predictions:
            structured = pred.get("structured_formatting", {}) or {}
            suggestions.append(
                GeoSuggestion(
                    provider_place_id=pred.get("place_id", ""),
                    primary_text=structured.get("main_text", pred.get("description", "")),
                    secondary_text=structured.get("secondary_text", ""),
                    place_type=(pred.get("types") or [""])[0],
                    provider="google_places",
                )
            )
        return suggestions

    def retrieve(self, provider_place_id: str, context: GeoSearchContext) -> GeoPlace | None:
        params: dict[str, object] = {
            "place_id": provider_place_id,
            "key": self._api_key,
            "fields": "name,formatted_address,geometry,address_component,type",
        }
        if context.search_session_id:
            params["sessiontoken"] = context.search_session_id
        try:
            resp = requests.get(_GOOGLE_DETAILS_URL, params=params, timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            body = resp.json()
        except Exception:
            _logger.warning("retrieve failed provider=google_places")
            return None

        result = body.get("result")
        if not result:
            return None
        return self._parse_google_place(result, provider_place_id)

    def reverse_geocode(self, point: GeoPoint) -> GeoPlace | None:
        params = {"latlng": f"{point.latitude},{point.longitude}", "key": self._api_key}
        try:
            resp = requests.get(_GOOGLE_GEOCODE_URL, params=params, timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            body = resp.json()
        except Exception:
            _logger.warning("reverse_geocode failed provider=google_places")
            return None

        results = body.get("results", []) or []
        if not results:
            return None
        top = results[0]
        return self._parse_google_place(top, top.get("place_id", ""), fallback_point=point)

    def _parse_google_place(self, result: dict, place_id: str, fallback_point: GeoPoint | None = None) -> GeoPlace:
        components = {c["types"][0]: c["long_name"] for c in result.get("address_components", []) if c.get("types")}
        country_code = None
        for c in result.get("address_components", []):
            if "country" in c.get("types", []):
                country_code = c.get("short_name")
                break
        address = GeoAddress(
            street=components.get("route"),
            house_number=components.get("street_number"),
            postal_code=components.get("postal_code"),
            city=components.get("locality") or components.get("postal_town"),
            district=components.get("sublocality"),
            region=components.get("administrative_area_level_1"),
            country_code=country_code,
            country_name=components.get("country"),
            formatted_address=result.get("formatted_address", ""),
        )
        geometry = result.get("geometry", {}) or {}
        location = geometry.get("location", {}) or {}
        point = fallback_point
        if location.get("lat") is not None and location.get("lng") is not None:
            point = GeoPoint(latitude=float(location["lat"]), longitude=float(location["lng"]))
        types = result.get("types", []) or []
        precision = LocationPrecision.EXACT if "street_address" in types or "premise" in types else (
            LocationPrecision.CITY if "locality" in types else LocationPrecision.APPROXIMATE
        )
        return GeoPlace(
            id=place_id,
            name=result.get("name", "") or address.formatted_address,
            place_type=(types or [""])[0],
            address=address,
            point=point,
            provider="google_places",
            provider_place_id=place_id,
            precision=precision,
        )


def get_default_geo_search_provider(settings: object) -> GeoSearchProvider:
    """Factory (mirroring das ``spotify_client_id``-Optional-Feature-Muster):
    Google Places, sobald ``settings.google_places_api_key`` gesetzt ist,
    sonst der kostenlose, immer lauffähige Nominatim-Adapter - Zero-Config-
    Dev/Test bleibt garantiert funktionsfähig."""
    api_key = getattr(settings, "google_places_api_key", "") or ""
    if api_key:
        return GooglePlacesSearchProvider(api_key=api_key)
    return NominatimGeoSearchProvider()
