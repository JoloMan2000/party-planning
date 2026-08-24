"""Tests für die Party Context Engine (party_context/*).

Deckt die in der Party-Context-Engine-Spec (§79-88) formal benannten
Testszenarien als pytest-Funktionen ab:
    §79 TEST: SOMMER VS WINTER
    §80 TEST: GARTEN VS WOHNUNG
    §81 TEST: KEIN GRILL
    §82 TEST: ESPRESSO MARTINI
    §83 TEST: HOT WEATHER WATER
    §84 TEST: MUSIC NEIGHBORS
    §85 TEST: LARGE GROUP
    §86 TEST: ACTUAL WEATHER OVERRIDES SEASON
    §87 TEST: FALLBACK OHNE WEATHER
    §88 TEST: EXPLAINABILITY

Nutzt den ECHTEN Katalog (kein Mocking, siehe conftest.py / AUFGABE §43)
für alle Szenarien, die reale Items brauchen (§80/§82).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from party_context import config
from party_context.context_fit import calculate_context_fit
from party_context.domain import PartyContext, PartyContextOverride
from party_context.engine import PartyContextEngine
from party_engine.domain import GuestResponse, PartyConfig
from party_engine.engine import compute_party_demand
from music_engine.engine import _apply_music_context_modifiers
from music_engine.domain import MusicPhase


@pytest.fixture()
def engine():
    return PartyContextEngine()


def _servings_for(result, item_id):
    for summary in result.item_demand:
        if summary.item_id == item_id:
            return summary.expected_servings
    return None


# --- §79: SOMMER VS WINTER ---------------------------------------------------


def test_sommer_vs_winter(engine):
    summer = engine.derive_context(
        PartyContext(
            start_datetime=datetime(2026, 7, 18, 15, 0),
            location_type="garden",
            indoor_outdoor="outdoor",
            expected_temperature_c=29.0,
        )
    )
    winter = engine.derive_context(
        PartyContext(
            start_datetime=datetime(2026, 1, 10, 18, 0),
            location_type="apartment",
            indoor_outdoor="indoor",
            expected_temperature_c=5.0,
        )
    )

    assert summer.season == "summer"
    assert winter.season == "winter"

    assert summer.food_modifiers.salad_preference > winter.food_modifiers.salad_preference
    assert summer.food_modifiers.grill_preference > winter.food_modifiers.grill_preference
    assert winter.food_modifiers.comfort_food_preference > summer.food_modifiers.comfort_food_preference
    assert winter.food_modifiers.hot_food_preference > summer.food_modifiers.hot_food_preference
    assert winter.beverage_modifiers.hot_drink_multiplier > summer.beverage_modifiers.hot_drink_multiplier


# --- §80: GARTEN VS WOHNUNG --------------------------------------------------


def test_garten_vs_wohnung(catalog, engine):
    bratwurst = catalog.get_item("bratwurst")
    pizza = catalog.get_item("pizza_margherita")
    assert bratwurst is not None
    assert pizza is not None

    garden_ctx = engine.derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", has_grill=True)
    )
    apartment_ctx = engine.derive_context(
        PartyContext(location_type="apartment", indoor_outdoor="indoor", has_kitchen=True)
    )

    bratwurst_garden = calculate_context_fit(bratwurst, garden_ctx).location_score
    bratwurst_apartment = calculate_context_fit(bratwurst, apartment_ctx).location_score
    pizza_garden = calculate_context_fit(pizza, garden_ctx).location_score
    pizza_apartment = calculate_context_fit(pizza, apartment_ctx).location_score

    assert bratwurst_garden > bratwurst_apartment
    assert pizza_apartment > pizza_garden


# --- §81: KEIN GRILL ----------------------------------------------------------


def test_kein_grill(catalog, engine):
    bratwurst = catalog.get_item("bratwurst")
    assert bratwurst is not None

    with_grill = engine.derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", has_grill=True)
    )
    without_grill = engine.derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", has_grill=False)
    )

    fit_with = calculate_context_fit(bratwurst, with_grill)
    fit_without = calculate_context_fit(bratwurst, without_grill)

    assert "no_grill" in without_grill.operational_constraints
    assert "no_grill" not in with_grill.operational_constraints
    # Hard-Constraint (§11): fehlende Infrastruktur deckelt den Gesamtscore.
    assert fit_without.total_score <= 0.15
    assert fit_without.total_score < fit_with.total_score
    assert any("grill" in penalty for penalty in fit_without.penalties)


# --- §82: ESPRESSO MARTINI -----------------------------------------------------


def test_espresso_martini(catalog, engine):
    assert "espresso_martini" in catalog.recipes
    assert "cocktail" in catalog.recipes["espresso_martini"].recommendation.tags

    responses = [
        GuestResponse(guest_name="A", start_time="18:00", drink_selections=["espresso_martini", "vodka"]),
    ]

    with_bar = engine.derive_context(
        PartyContext(location_type="apartment", indoor_outdoor="indoor", has_bar=True, has_coffee_machine=True)
    )
    without_bar = engine.derive_context(
        PartyContext(location_type="apartment", indoor_outdoor="indoor", has_bar=False, has_coffee_machine=True)
    )

    assert with_bar.beverage_modifiers.cocktail_complexity_penalty == 0.0
    assert without_bar.beverage_modifiers.cocktail_complexity_penalty > 0.0

    result_with_bar = compute_party_demand(catalog, responses, PartyConfig(), derived_context=with_bar)
    result_without_bar = compute_party_demand(catalog, responses, PartyConfig(), derived_context=without_bar)

    em_with_bar = _servings_for(result_with_bar, "espresso_martini")
    em_without_bar = _servings_for(result_without_bar, "espresso_martini")
    vodka_with_bar = _servings_for(result_with_bar, "vodka")
    vodka_without_bar = _servings_for(result_without_bar, "vodka")

    assert em_without_bar < em_with_bar
    assert vodka_without_bar > vodka_with_bar


# --- §83: HOT WEATHER WATER ----------------------------------------------------


def test_hot_weather_water(engine):
    cool_ctx = engine.derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", expected_temperature_c=20.0)
    )
    hot_ctx = engine.derive_context(
        PartyContext(location_type="garden", indoor_outdoor="outdoor", expected_temperature_c=33.0)
    )

    assert hot_ctx.temperature_class == "hot"
    assert hot_ctx.beverage_modifiers.water_multiplier > cool_ctx.beverage_modifiers.water_multiplier
    assert hot_ctx.beverage_modifiers.ice_multiplier > cool_ctx.beverage_modifiers.ice_multiplier

    party_config = PartyConfig()
    water_cool = party_config.water_l_per_guest * cool_ctx.beverage_modifiers.water_multiplier
    water_hot = party_config.water_l_per_guest * hot_ctx.beverage_modifiers.water_multiplier
    assert water_hot > water_cool


# --- §84: MUSIC NEIGHBORS -------------------------------------------------------


def test_music_neighbors(engine):
    apartment_ctx = engine.derive_context(
        PartyContext(location_type="apartment", indoor_outdoor="indoor", neighbors_sensitive=True)
    )
    club_ctx = engine.derive_context(
        PartyContext(location_type="club", indoor_outdoor="indoor", neighbors_sensitive=False)
    )

    assert apartment_ctx.music_modifiers.bass_penalty > club_ctx.music_modifiers.bass_penalty
    assert (
        apartment_ctx.music_modifiers.late_night_energy_penalty
        > club_ctx.music_modifiers.late_night_energy_penalty
    )

    phases = [
        MusicPhase(id="late", start_fraction=0.7, end_fraction=0.9, target_energy=0.8, target_danceability=0.8),
        MusicPhase(id="closing", start_fraction=0.9, end_fraction=1.0, target_energy=0.6, target_danceability=0.5),
    ]

    genre_weights, tag_weights, mood_weights, energy_target, danceability_target, new_phases_apt = (
        _apply_music_context_modifiers(
            {}, {"bass_heavy": 0.8}, {}, 0.5, 0.5, phases, apartment_ctx.music_modifiers
        )
    )
    _, _, _, _, _, new_phases_club = _apply_music_context_modifiers(
        {}, {"bass_heavy": 0.8}, {}, 0.5, 0.5, phases, club_ctx.music_modifiers
    )

    assert tag_weights["bass_heavy"] < 0.8
    late_phase_apt = next(p for p in new_phases_apt if p.id == "late")
    late_phase_club = next(p for p in new_phases_club if p.id == "late")
    assert late_phase_apt.target_energy < late_phase_club.target_energy


# --- §85: LARGE GROUP -----------------------------------------------------------


def test_large_group(engine):
    small_ctx = engine.derive_context(PartyContext(location_type="garden", indoor_outdoor="outdoor", guest_count=10))
    large_ctx = engine.derive_context(PartyContext(location_type="garden", indoor_outdoor="outdoor", guest_count=80))

    assert small_ctx.group_size_class in ("small_group", "medium_group")
    assert large_ctx.group_size_class in ("large_group", "very_large_group")

    for tag in config.LARGE_GROUP_OPERATIONAL_TAGS_BOOST:
        assert large_ctx.recommendation_tags.get(tag, 0.0) > small_ctx.recommendation_tags.get(tag, 0.0)
    for tag in config.LARGE_GROUP_OPERATIONAL_TAGS_PENALTY:
        assert large_ctx.recommendation_tags.get(tag, 0.0) < small_ctx.recommendation_tags.get(tag, 0.0)


# --- §86: ACTUAL WEATHER OVERRIDES SEASON ---------------------------------------


def test_actual_weather_overrides_season(engine):
    rainy_july_ctx = engine.derive_context(
        PartyContext(
            start_datetime=datetime(2026, 7, 18, 15, 0),
            expected_temperature_c=15.0,
            weather_condition="rain",
            rain_probability=0.8,
            location_type="garden",
            indoor_outdoor="outdoor",
        )
    )

    assert rainy_july_ctx.season == "summer"
    assert rainy_july_ctx.temperature_class == "mild"  # nicht "hot", trotz Juli
    assert rainy_july_ctx.weather_is_actual is True
    assert "outdoor_rain_risk" in rainy_july_ctx.operational_constraints


# --- §87: FALLBACK OHNE WEATHER --------------------------------------------------


def test_fallback_ohne_weather(engine):
    derived = engine.derive_context(PartyContext(location_type="apartment", indoor_outdoor="indoor", guest_count=10))

    assert derived.weather_is_actual is False
    assert derived.temperature_class in ("cold", "cool", "mild", "warm", "hot")
    assert derived.season in ("spring", "summer", "autumn", "winter")
    assert derived.explanations  # weiterhin nachvollziehbar, trotz Fallback


# --- §88: EXPLAINABILITY ---------------------------------------------------------


def test_explainability(engine):
    derived = engine.derive_context(
        PartyContext(
            start_datetime=datetime(2026, 7, 18, 15, 0),
            location_type="garden",
            indoor_outdoor="outdoor",
            has_grill=True,
            expected_temperature_c=29.0,
        )
    )

    assert derived.explanations
    joined = " ".join(derived.explanations)
    assert "Saison" in joined
    assert "Tageszeit" in joined
    assert "outdoor" in joined or "Location" in joined

    # Admin-Override muss ebenfalls eine nachvollziehbare Erklärung erzeugen (§72).
    overridden = engine.derive_context(
        PartyContext(location_type="apartment", indoor_outdoor="indoor"),
        overrides=[PartyContextOverride(key="temperature_class", value="warm", reason="Zelt mit Heizung")],
    )
    assert any("Admin-Override" in e and "Zelt mit Heizung" in e for e in overridden.explanations)
