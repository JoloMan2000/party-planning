"""Geocoding-Architektur (Geo-Kultur-Spec §2). Löst eine freie Adresse
(``PartyContext.party_address``, gespiegelt aus ``event_theme.party_location``)
zu einem ISO-3166-1-alpha-2-Ländercode auf, damit die Culture-Engine (§4)
länderspezifische Essens-/Getränke-/Musik-Tags anwenden kann.

``GeocodingProvider``/``GeocodingResult`` selbst leben in
``party_context.domain`` (Datenstrukturen), dieses Modul enthält die
konkrete Nominatim-Integration sowie die reine Auflösungsfunktion
``resolve_country_code()``, die niemals raist - jeder Fehler liefert
``("", "unknown")``, Caller fällt dann auf den neutralen Fallback zurück (§4)."""

from __future__ import annotations

import requests

from party_context import storage
from party_context.domain import GeocodingResult

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "PartyPlanningApp/1.0 (party-context-engine)"
_REQUEST_TIMEOUT_S = 5


class NullGeocodingProvider:
    """Fallback-Provider, der niemals Live-Geocoding liefert (analog
    ``NullWeatherProvider`` - die Engine muss auch ganz ohne Geocoding-API
    vollständig funktionieren)."""

    def geocode(self, address: str) -> GeocodingResult | None:
        return None


class NominatimGeocodingProvider:
    """Echte Geocoding-Anbindung über OpenStreetMap Nominatim (kostenlos,
    kein API-Key nötig). Nutzungsrichtlinie verlangt einen aussagekräftigen
    ``User-Agent`` und max. 1 Request/Sekunde - Caching (siehe
    ``party_context.storage.geocode_cache``) ist daher nicht optional,
    sondern Pflicht für jeden Aufrufer dieser Klasse.

    Muss NIE raisen (§2): jeder Fehler (Netzwerk/Timeout/kein Treffer/
    unerwartetes JSON) liefert ``None``."""

    def geocode(self, address: str) -> GeocodingResult | None:
        if not address or not address.strip():
            return None
        try:
            resp = requests.get(
                _NOMINATIM_URL,
                params={"q": address, "format": "json", "addressdetails": 1, "limit": 1},
                headers={"User-Agent": _USER_AGENT},
                timeout=_REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            results = resp.json()
            if not results:
                return None
            top = results[0]
            addr = top.get("address", {})
            country_code = (addr.get("country_code") or "").upper()
            if not country_code:
                return None
            return GeocodingResult(
                country_code=country_code,
                country_name=addr.get("country", ""),
                display_address=top.get("display_name", ""),
            )
        except Exception:
            return None


class CachingGeocodingProvider:
    """Cache-Wrapper um einen ``GeocodingProvider`` (Geo-Kultur-Spec §2):
    schlägt zuerst im ``geocode_cache`` (``party_context.storage``) nach und
    ruft den inneren Provider nur bei Cache-Miss auf. Pflicht für jede
    Live-Anbindung (Nominatim-Nutzungsrichtlinie: max. 1 Request/Sekunde,
    siehe ``NominatimGeocodingProvider``-Docstring). Cacht auch Fehlschläge
    (leerer Treffer) als ``""``, damit eine wiederholt unauflösbare Adresse
    nicht bei jedem App-Aufruf erneut angefragt wird."""

    def __init__(self, db_path: str, inner: object) -> None:
        self._db_path = db_path
        self._inner = inner

    def geocode(self, address: str) -> GeocodingResult | None:
        if not address or not address.strip():
            return None
        cached = storage.get_cached_country_code(self._db_path, address)
        if cached is not None:
            return GeocodingResult(country_code=cached) if cached else None
        result = self._inner.geocode(address)
        storage.save_geocode_cache(self._db_path, address, result.country_code if result else "")
        return result


def resolve_country_code(
    party_address: str,
    explicit_country_code: str = "",
    provider: object | None = None,
) -> tuple[str, str]:
    """Liefert ``(country_code, source)``. Admin-Override gewinnt immer
    (§3, analog zum ``season``-Override-Muster). Sonst wird - falls ein
    Provider übergeben wurde und eine Adresse vorliegt - per Geocoding
    aufgelöst. Liefert ``("", "unknown")``, wenn nichts vorliegt bzw. das
    Geocoding fehlschlägt - niemals ein Fehler/Exception."""
    if explicit_country_code:
        return explicit_country_code.upper(), "admin_override"

    if provider is not None and party_address and party_address.strip():
        result = provider.geocode(party_address)
        if result is not None and result.country_code:
            return result.country_code, "geocoded"

    return "", "unknown"


if __name__ == "__main__":
    class _FakeGeocodingProvider:
        def geocode(self, address: str) -> GeocodingResult | None:
            if "Berlin" in address:
                return GeocodingResult(country_code="DE", country_name="Germany", display_address=address)
            return None

    # Admin-Override gewinnt immer, auch wenn Provider/Adresse vorhanden sind.
    cc, source = resolve_country_code("Berlin, Germany", explicit_country_code="in", provider=_FakeGeocodingProvider())
    assert cc == "IN"
    assert source == "admin_override"

    # Geocoding-Fall.
    cc, source = resolve_country_code("Berlin, Germany", provider=_FakeGeocodingProvider())
    assert cc == "DE"
    assert source == "geocoded"

    # Kein Override, Provider liefert nichts -> unknown.
    cc, source = resolve_country_code("Unbekannter Ort", provider=_FakeGeocodingProvider())
    assert cc == ""
    assert source == "unknown"

    # Kein Provider, keine Adresse -> unknown.
    cc, source = resolve_country_code("", provider=None)
    assert cc == ""
    assert source == "unknown"

    null_provider = NullGeocodingProvider()
    assert null_provider.geocode("Berlin") is None
    cc, source = resolve_country_code("Berlin, Germany", provider=null_provider)
    assert cc == ""
    assert source == "unknown"

    # CachingGeocodingProvider: erster Aufruf trifft den inneren Provider,
    # zweiter Aufruf kommt aus dem Cache (inneren Provider durch Zähl-Fake ersetzt).
    import tempfile
    from pathlib import Path

    class _CountingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def geocode(self, address: str) -> GeocodingResult | None:
            self.calls += 1
            if "Lima" in address:
                return GeocodingResult(country_code="PE", country_name="Peru", display_address=address)
            return None

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_geocode_cache.db"
        storage.init_party_context_storage(db_path)
        counting = _CountingProvider()
        caching = CachingGeocodingProvider(db_path, counting)

        result1 = caching.geocode("Lima, Peru")
        assert result1 is not None and result1.country_code == "PE"
        assert counting.calls == 1

        result2 = caching.geocode("Lima, Peru")
        assert result2 is not None and result2.country_code == "PE"
        assert counting.calls == 1  # Cache-Hit, kein zweiter Netzwerk-Call

        # Fehlschlag wird ebenfalls gecacht (kein wiederholter Call).
        miss1 = caching.geocode("Nirgendwo")
        assert miss1 is None
        assert counting.calls == 2
        miss2 = caching.geocode("Nirgendwo")
        assert miss2 is None
        assert counting.calls == 2

        assert caching.geocode("") is None
        assert caching.geocode("   ") is None

    print("party_context/geocoding.py sanity check OK.")
