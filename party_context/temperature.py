"""Temperaturklassen-Ableitung (Spec §46). Zentral, damit keine Engine eigene
Temperatur-Schwellen definiert."""

from __future__ import annotations

from party_context.config import (
    SEASON_FALLBACK_TEMPERATURE_CLASS,
    TEMPERATURE_CLASS_HOT,
    TEMPERATURE_CLASS_THRESHOLDS,
)


def classify_temperature(temperature_c: float | None) -> str | None:
    """cold < 8 <= cool < 15 <= mild < 21 <= warm < 28 <= hot (§46,
    konfigurierbar in config.TEMPERATURE_CLASS_THRESHOLDS)."""
    if temperature_c is None:
        return None
    for threshold, label in TEMPERATURE_CLASS_THRESHOLDS:
        if temperature_c < threshold:
            return label
    return TEMPERATURE_CLASS_HOT


def fallback_temperature_class(season: str | None) -> str:
    """Ohne Wetterdaten (§87): plausible Temperaturklasse aus der Saison."""
    if season is None:
        return "mild"
    return SEASON_FALLBACK_TEMPERATURE_CLASS.get(season, "mild")


if __name__ == "__main__":
    assert classify_temperature(4.0) == "cold"
    assert classify_temperature(7.9) == "cold"
    assert classify_temperature(8.0) == "cool"
    assert classify_temperature(14.9) == "cool"
    assert classify_temperature(15.0) == "mild"
    assert classify_temperature(20.9) == "mild"
    assert classify_temperature(21.0) == "warm"
    assert classify_temperature(27.9) == "warm"
    assert classify_temperature(28.0) == "hot"
    assert classify_temperature(35.0) == "hot"
    assert classify_temperature(None) is None
    assert fallback_temperature_class("winter") == "cold"
    assert fallback_temperature_class("summer") == "warm"
    assert fallback_temperature_class(None) == "mild"
    print("party_context/temperature.py sanity check OK.")
