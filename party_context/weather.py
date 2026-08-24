"""Wetter-Architektur (Spec §73-§75). Version 1 funktioniert vollständig ohne
konkreten ``WeatherProvider`` - dieses Modul bereitet lediglich die
Erweiterung um eine externe Wetterquelle vor (z.B. Open-Meteo/OpenWeather).

``WeatherProvider``/``WeatherContext`` selbst leben in ``party_context.domain``
(Datenstrukturen), dieses Modul enthält nur die (noch fehlende) konkrete
Integration bzw. einen No-Op-Fallback-Provider für Tests."""

from __future__ import annotations

from datetime import datetime

from party_context.domain import WeatherContext


class NullWeatherProvider:
    """Fallback-Provider, der niemals Live-Wetterdaten liefert (§44: die
    Engine muss auch ganz ohne Wetter-API vollständig funktionieren)."""

    def get_party_weather(
        self, location_type: str, start_datetime: datetime | None
    ) -> WeatherContext | None:
        return None


def resolve_weather_context(
    party_expected_temperature_c: float | None,
    party_weather_condition: str | None,
    party_rain_probability: float | None,
    provider: object | None = None,
    location_type: str = "other",
    start_datetime: datetime | None = None,
) -> WeatherContext | None:
    """Liefert den zu verwendenden ``WeatherContext``: bevorzugt einen
    externen ``WeatherProvider`` (falls übergeben und er Daten liefert),
    sonst die manuell im ``PartyContext`` erfassten Wetterfelder (§44/§45).
    Liefert ``None``, wenn weder Provider noch manuelle Wetterdaten vorliegen
    - Caller fällt dann auf den saisonalen Default zurück (§87)."""
    if provider is not None:
        live = provider.get_party_weather(location_type, start_datetime)
        if live is not None:
            return live

    if party_expected_temperature_c is None and party_weather_condition is None:
        return None

    return WeatherContext(
        temperature_c=party_expected_temperature_c,
        apparent_temperature_c=party_expected_temperature_c,
        condition=party_weather_condition,
        precipitation_probability=party_rain_probability,
        wind_speed=None,
        fetched_at=None,
    )


if __name__ == "__main__":
    assert resolve_weather_context(None, None, None) is None

    manual = resolve_weather_context(29.0, "sunny", 0.05)
    assert manual is not None
    assert manual.temperature_c == 29.0
    assert manual.condition == "sunny"

    null_provider = NullWeatherProvider()
    assert null_provider.get_party_weather("garden", None) is None
    manual_with_null_provider = resolve_weather_context(16.0, "rain", 0.7, provider=null_provider)
    assert manual_with_null_provider is not None
    assert manual_with_null_provider.temperature_c == 16.0
    print("party_context/weather.py sanity check OK.")
