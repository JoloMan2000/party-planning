"""Tests für die Geo-/Kultur-Kontext-Erweiterung + persistentes Cross-Party-
Lernen (Geo-Kultur-Spec §9).

Deckt die dort formal benannten Testszenarien als pytest-Funktionen ab:
    TEST: GEOCODING FALLBACK
    TEST: ADMIN OVERRIDE GEWINNT
    TEST: INDIEN VS DEUTSCHLAND
    TEST: KEIN HARTER FILTER
    TEST: KALTSTART OHNE HISTORIE
    TEST: LERN-SIGNAL VERSCHIEBT RANKING
    TEST: GEOCODING-PROVIDER-FEHLER -> NIE EINE EXCEPTION

Test-Strategie (Geo-Kultur-Spec §2): ein ``_FakeGeocodingProvider`` für alle
Unit-Tests - KEINE echten Netzwerk-Calls. Der einzige Test, der die reale
``NominatimGeocodingProvider``-Klasse anfasst (GEOCODING-PROVIDER-FEHLER),
patcht ``requests.get`` via ``monkeypatch`` statt einen echten Request zu
senden, um exakt deren internen ``try/except``-Pfad zu prüfen.

Nutzt den ECHTEN Katalog (kein Mocking, siehe conftest.py / AUFGABE §43)
für alle Szenarien, die reale Items brauchen.
"""

from __future__ import annotations

import requests

from party_context.context_fit import calculate_context_fit
from party_context.domain import (
    GeocodingResult,
    LearningHistory,
    PartyContext,
    PartyRunSnapshot,
    SelectionEvent,
)
from party_context.engine import PartyContextEngine
from party_context.geocoding import NominatimGeocodingProvider, resolve_country_code
from party_engine.recommendation import compute_learned_preference_score, score_item_for_occasion
from party_engine.recommendation_domain import RecommendationContext
from party_engine.occasions import load_all_occasions


class _FakeGeocodingProvider:
    """Test-Double (Geo-Kultur-Spec §2): löst nur bekannte Fake-Adressen auf,
    niemals ein echter Netzwerk-Call."""

    def geocode(self, address: str) -> GeocodingResult | None:
        if "New York" in address:
            return GeocodingResult(country_code="US", country_name="United States", display_address=address)
        return None


def _engine():
    return PartyContextEngine()


# --- TEST: GEOCODING FALLBACK ------------------------------------------------


def test_geocoding_fallback_keine_adresse():
    derived = _engine().derive_context(
        PartyContext(party_address="", country_code=""),
        geocoding_provider=_FakeGeocodingProvider(),
    )
    assert derived.country_code == ""
    assert derived.country_source == "unknown"
    assert derived.culture_food_tags == {}
    assert derived.culture_beverage_tags == {}


# --- TEST: ADMIN OVERRIDE GEWINNT --------------------------------------------


def test_admin_override_gewinnt_gegen_geocoding():
    derived = _engine().derive_context(
        PartyContext(party_address="New York, USA", country_code="jp"),
        geocoding_provider=_FakeGeocodingProvider(),
    )
    assert derived.country_code == "JP"
    assert derived.country_source == "admin_override"
    assert derived.culture_genre_bias.get("jpop") == 0.8


# --- TEST: INDIEN VS DEUTSCHLAND ---------------------------------------------


def test_indien_vs_deutschland(catalog):
    masala_chai = catalog.get_item("masala_chai")
    assert masala_chai is not None

    india_ctx = _engine().derive_context(PartyContext(country_code="IN"))
    germany_ctx = _engine().derive_context(PartyContext(country_code="DE"))

    fit_india = calculate_context_fit(masala_chai, india_ctx)
    fit_germany = calculate_context_fit(masala_chai, germany_ctx)

    assert fit_india.culture_score > fit_germany.culture_score


# --- TEST: KEIN HARTER FILTER ------------------------------------------------


def test_kein_harter_filter_bier_bleibt_waehlbar(catalog):
    beer = catalog.get_item("beer_pils")
    assert beer is not None

    india_ctx = _engine().derive_context(PartyContext(country_code="IN"))
    germany_ctx = _engine().derive_context(PartyContext(country_code="DE"))

    fit_india = calculate_context_fit(beer, india_ctx)
    fit_germany = calculate_context_fit(beer, germany_ctx)

    # Niedriger gerankt in Indien als in Deutschland ...
    assert fit_india.culture_score < fit_germany.culture_score
    # ... aber niemals ausgeschlossen: bleibt ein valides, positives Ergebnis.
    assert fit_india.total_score > 0.0
    assert beer.id in {it.id for it in catalog.all_selectable_items()}


# --- TEST: KALTSTART OHNE HISTORIE -------------------------------------------


def test_kaltstart_ohne_historie_liefert_neutral(catalog):
    empty_history = LearningHistory()
    context_dims = {"season": "summer", "location_type": "garden", "country_code": "IN"}
    assert compute_learned_preference_score("masala_chai", context_dims, empty_history) == 0.5


def test_kaltstart_ranking_identisch_mit_und_ohne_learning_history(catalog):
    occasions = load_all_occasions()
    profile = occasions["birthday"]
    party_context = RecommendationContext(season="summer", hour_of_day=19, guest_count=20)
    derived = _engine().derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", country_code="IN")
    )

    items = catalog.all_selectable_items()[:20]
    scores_without = {
        it.id: score_item_for_occasion(it, profile, party_context, derived_context=derived).total_score
        for it in items
    }
    scores_with_empty = {
        it.id: score_item_for_occasion(
            it, profile, party_context, derived_context=derived, learning_history=LearningHistory()
        ).total_score
        for it in items
    }
    assert scores_without == scores_with_empty


# --- TEST: LERN-SIGNAL VERSCHIEBT RANKING ------------------------------------


def test_lern_signal_verschiebt_ranking(catalog):
    occasions = load_all_occasions()
    profile = occasions["birthday"]
    party_context = RecommendationContext(season="summer", hour_of_day=19, guest_count=20)
    derived = _engine().derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", country_code="IN")
    )

    item = catalog.get_item("masala_chai")
    assert item is not None

    # 10 ähnliche vergangene Partys (gleiches season/location_type/country_code),
    # masala_chai wurde in 8 davon tatsächlich gewählt.
    runs = [
        PartyRunSnapshot(id=i, season="summer", location_type="garden", country_code="IN")
        for i in range(1, 11)
    ]
    events = [SelectionEvent(party_run_id=i, item_id="masala_chai") for i in range(1, 9)]
    history = LearningHistory(runs=runs, events=events)

    score_without = score_item_for_occasion(item, profile, party_context, derived_context=derived)
    score_with = score_item_for_occasion(
        item, profile, party_context, derived_context=derived, learning_history=history
    )

    assert score_with.learned_score > 0.5
    assert score_with.total_score > score_without.total_score


# --- TEST: GEOCODING-PROVIDER-FEHLER -> NIE EINE EXCEPTION -------------------


def test_geocoding_provider_fehler_niemals_exception(monkeypatch):
    def _raise_timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("simulierter Netzwerk-Timeout")

    monkeypatch.setattr(requests, "get", _raise_timeout)

    provider = NominatimGeocodingProvider()
    # Der Provider selbst darf nicht raisen (Vertrag §2).
    result = provider.geocode("Irgendeine Adresse 1")
    assert result is None

    cc, source = resolve_country_code("Irgendeine Adresse 1", provider=provider)
    assert cc == ""
    assert source == "unknown"

    # Die gesamte Engine bleibt voll funktionsfähig, auch bei fehlerhaftem Provider.
    derived = _engine().derive_context(
        PartyContext(party_address="Irgendeine Adresse 1"),
        geocoding_provider=provider,
    )
    assert derived.country_code == ""
    assert derived.country_source == "unknown"
