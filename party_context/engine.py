"""
PartyContextEngine (Spec §9): leitet aus einem ``PartyContext`` die zentrale,
von allen nachgelagerten Engines konsumierte Wahrheit ab (``DerivedPartyContext``).

Diese Engine bestimmt zentral Saison/Tageszeit/Temperaturklasse/Location-
Eigenschaften/Infrastruktur/Operational Constraints/Recommendation Tags/
Beverage-/Food-/Music-Modifier (§9) - keine nachgelagerte Engine darf diese
Logik redundant selbst implementieren (§10).
"""

from __future__ import annotations

from party_context import config
from party_context.capabilities import derive_capabilities
from party_context.daypart import derive_daypart, derive_daypart_weights
from party_context.domain import (
    BeverageContextModifiers,
    DerivedPartyContext,
    FoodContextModifiers,
    MusicContextModifiers,
    PartyContext,
    PartyContextOverride,
)
from party_context.locations import get_location_profile
from party_context.season import derive_season
from party_context.temperature import classify_temperature, fallback_temperature_class
from party_context.weather import resolve_weather_context


def _capped_field(base: float, deltas: list[float], field_name: str, caps: dict[str, tuple[float, float]], default_bounds: tuple[float, float]) -> float:
    cap_min, cap_max = caps.get(field_name, default_bounds)
    return config.apply_capped_modifier(base, deltas, cap_min, cap_max)


class PartyContextEngine:
    """Single entry point: ``PartyContext`` -> ``DerivedPartyContext`` (§9)."""

    def derive_context(
        self,
        party_context: PartyContext,
        overrides: list[PartyContextOverride] | None = None,
        weather_provider: object | None = None,
        hemisphere: str = "northern",
    ) -> DerivedPartyContext:
        explanations: list[str] = []

        # --- Saison (§5) ---------------------------------------------------
        season = derive_season(party_context.start_datetime, hemisphere=hemisphere, override=party_context.season)
        if season is None:
            season = "summer"
            explanations.append("Keine Datums-/Saisonangabe vorhanden - neutraler Sommer-Fallback verwendet.")
        elif party_context.season:
            explanations.append(f"Saison wurde vom Admin auf '{season}' gesetzt.")
        else:
            explanations.append(f"Saison '{season}' wurde aus dem Party-Datum abgeleitet.")

        # --- Tageszeit (§6/§7) ----------------------------------------------
        daypart_primary = derive_daypart(party_context.start_datetime)
        daypart_weights = derive_daypart_weights(party_context.start_datetime, party_context.duration_hours)
        if party_context.start_datetime is not None:
            explanations.append(f"Tageszeit '{daypart_primary}' wurde aus der Startzeit ({party_context.duration_hours} h Dauer) abgeleitet.")

        # --- Wetter / Temperaturklasse (§44/§45/§46) -------------------------
        weather_ctx = resolve_weather_context(
            party_context.expected_temperature_c,
            party_context.weather_condition,
            party_context.rain_probability,
            provider=weather_provider,
            location_type=party_context.location_type,
            start_datetime=party_context.start_datetime,
        )
        if weather_ctx is not None and weather_ctx.temperature_c is not None:
            temperature_class = classify_temperature(weather_ctx.temperature_c)
            weather_is_actual = True
            explanations.append(
                f"Tatsächliche Wetterdaten ({weather_ctx.temperature_c:.0f}°C"
                f"{', ' + weather_ctx.condition if weather_ctx.condition else ''}) wurden verwendet und"
                f" priorisiert gegenüber der reinen Saison-Annahme."
            )
            rain_probability = weather_ctx.precipitation_probability
        else:
            temperature_class = fallback_temperature_class(season)
            weather_is_actual = False
            explanations.append(f"Keine Wetterdaten vorhanden - Temperaturklasse '{temperature_class}' wurde aus der Saison '{season}' abgeleitet.")
            rain_probability = party_context.rain_probability

        temperature_c = weather_ctx.temperature_c if weather_ctx is not None else party_context.expected_temperature_c
        weather_condition = weather_ctx.condition if weather_ctx is not None else party_context.weather_condition

        # --- Indoor/Outdoor + Location ---------------------------------------
        indoor_outdoor = party_context.indoor_outdoor
        location_profile = get_location_profile(party_context.location_type)
        explanations.append(f"Die Party findet überwiegend {indoor_outdoor} in der Location '{party_context.location_type}' statt.")

        # --- Gästezahl-Klasse (§39) -------------------------------------------
        group_size_class = config.classify_group_size(party_context.guest_count)

        # --- Capabilities (§17/§18) -------------------------------------------
        available_capabilities = derive_capabilities(party_context)

        # --- Location-/Kontext-Tags (§15/§16) ----------------------------------
        location_tags: set[str] = {
            indoor_outdoor,
            party_context.location_type,
            season,
            f"{temperature_class}_weather",
            group_size_class,
            daypart_primary,
        }
        location_tags |= set(location_profile.preferred_tags.keys())
        location_tags |= set(party_context.context_tags)

        # --- Operational Constraints (§11 Hard Constraint / §28) ---------------
        operational_constraints: set[str] = set()
        if not party_context.has_grill:
            operational_constraints.add("no_grill")
        else:
            explanations.append("Ein Grill ist vorhanden, daher erhalten Grillgerichte keinen Infrastruktur-Penalty.")
        if not party_context.has_bar:
            operational_constraints.add("no_bar_setup")
            explanations.append("Da keine Bar-Ausstattung angegeben wurde, werden komplexe Cocktails leicht heruntergestuft.")
        if not party_context.has_kitchen:
            operational_constraints.add("no_kitchen")
        if not party_context.has_fridge:
            operational_constraints.add("no_fridge")
        if not party_context.has_coffee_machine:
            operational_constraints.add("no_espresso_source")
        if party_context.neighbors_sensitive:
            operational_constraints.add("neighbors_sensitive")
        if party_context.music_volume_limit:
            operational_constraints.add("volume_limited")
        outdoor_ish = indoor_outdoor in ("outdoor", "mixed")
        if outdoor_ish and rain_probability is not None and rain_probability >= config.RAIN_PROBABILITY_HIGH_THRESHOLD:
            operational_constraints.add("outdoor_rain_risk")
            explanations.append(config.RAIN_WARNING_TEXT)
        if outdoor_ish and not party_context.has_fridge and temperature_class in ("warm", "hot"):
            operational_constraints.add("food_spoilage_risk")

        # --- Recommendation Tags (§15/§16/§40) -----------------------------------
        recommendation_tags: dict[str, float] = {}
        recommendation_tags[season] = 1.0
        recommendation_tags[f"{temperature_class}_weather"] = 1.0
        recommendation_tags[daypart_primary] = 1.0
        recommendation_tags[indoor_outdoor] = 1.0
        for tag, weight in location_profile.preferred_tags.items():
            recommendation_tags[tag] = max(recommendation_tags.get(tag, 0.0), weight)
        for tag, weight in location_profile.discouraged_tags.items():
            recommendation_tags[tag] = min(recommendation_tags.get(tag, 0.0), -weight)
        if group_size_class in ("large_group", "very_large_group"):
            for tag, delta in config.LARGE_GROUP_OPERATIONAL_TAGS_BOOST.items():
                recommendation_tags[tag] = recommendation_tags.get(tag, 0.0) + delta
            for tag, delta in config.LARGE_GROUP_OPERATIONAL_TAGS_PENALTY.items():
                recommendation_tags[tag] = recommendation_tags.get(tag, 0.0) + delta
            explanations.append(f"Gästezahl-Klasse '{group_size_class}' bevorzugt batchable/buffet-freundliche Empfehlungen.")

        # --- Beverage Context Modifiers (§19-§23/§64) -----------------------------
        bev_deltas: dict[str, list[float]] = {}
        for source in (config.SEASON_BEVERAGE_DELTAS.get(season, {}), config.TEMPERATURE_BEVERAGE_DELTAS.get(temperature_class, {})):
            for field_name, delta in source.items():
                bev_deltas.setdefault(field_name, []).append(delta)
        if outdoor_ish:
            for field_name, delta in config.OUTDOOR_BEVERAGE_DELTAS.items():
                bev_deltas.setdefault(field_name, []).append(delta)

        cocktail_penalty_deltas: list[float] = []
        if not party_context.has_bar:
            cocktail_penalty_deltas.append(config.NO_BAR_COCKTAIL_COMPLEXITY_PENALTY)
        if group_size_class in ("large_group", "very_large_group"):
            cocktail_penalty_deltas.append(config.LARGE_GROUP_COCKTAIL_COMPLEXITY_PENALTY)
        bev_deltas.setdefault("cocktail_complexity_penalty", []).extend(cocktail_penalty_deltas)

        beverage_modifiers = BeverageContextModifiers(
            water_multiplier=_capped_field(1.0, bev_deltas.get("water_multiplier", []), "water_multiplier", config.BEVERAGE_MULTIPLIER_CAPS, config.BEVERAGE_MODIFIER_FIELD_BOUNDS),
            non_alcoholic_multiplier=_capped_field(1.0, bev_deltas.get("non_alcoholic_multiplier", []), "non_alcoholic_multiplier", config.BEVERAGE_MULTIPLIER_CAPS, config.BEVERAGE_MODIFIER_FIELD_BOUNDS),
            ice_multiplier=_capped_field(1.0, bev_deltas.get("ice_multiplier", []), "ice_multiplier", config.BEVERAGE_MULTIPLIER_CAPS, config.BEVERAGE_MODIFIER_FIELD_BOUNDS),
            hot_drink_multiplier=_capped_field(1.0, bev_deltas.get("hot_drink_multiplier", []), "hot_drink_multiplier", config.BEVERAGE_MULTIPLIER_CAPS, config.BEVERAGE_MODIFIER_FIELD_BOUNDS),
            cold_refreshing_drink_multiplier=_capped_field(1.0, bev_deltas.get("cold_refreshing_drink_multiplier", []), "cold_refreshing_drink_multiplier", config.BEVERAGE_MULTIPLIER_CAPS, config.BEVERAGE_MODIFIER_FIELD_BOUNDS),
            cocktail_complexity_penalty=_capped_field(0.0, bev_deltas.get("cocktail_complexity_penalty", []), "cocktail_complexity_penalty", config.BEVERAGE_MULTIPLIER_CAPS, (0.0, 0.5)),
        )
        if beverage_modifiers.water_multiplier > 1.05:
            explanations.append(f"Aufgrund der Temperaturklasse '{temperature_class}' wurde der Wasser- und Eisbedarf erhöht (×{beverage_modifiers.water_multiplier:.2f}).")

        # --- Food Context Modifiers (§24-§28) -------------------------------------
        food_deltas: dict[str, list[float]] = {}
        for source in (config.SEASON_FOOD_DELTAS.get(season, {}), config.TEMPERATURE_FOOD_DELTAS.get(temperature_class, {})):
            for field_name, delta in source.items():
                food_deltas.setdefault(field_name, []).append(delta)

        spoilage_penalty = 0.0
        if "food_spoilage_risk" in operational_constraints:
            spoilage_penalty = config.FOOD_SPOILAGE_PENALTY_HIGH
            explanations.append(config.FOOD_SPOILAGE_WARNING_TEXT)
        elif not party_context.has_fridge:
            spoilage_penalty = config.FOOD_SPOILAGE_PENALTY_LOW

        bounds = config.FOOD_MODIFIER_FIELD_BOUNDS
        food_modifiers = FoodContextModifiers(
            fresh_food_preference=_capped_field(1.0, food_deltas.get("fresh_food_preference", []), "fresh_food_preference", {}, bounds),
            hot_food_preference=_capped_field(1.0, food_deltas.get("hot_food_preference", []), "hot_food_preference", {}, bounds),
            comfort_food_preference=_capped_field(1.0, food_deltas.get("comfort_food_preference", []), "comfort_food_preference", {}, bounds),
            salad_preference=_capped_field(1.0, food_deltas.get("salad_preference", []), "salad_preference", {}, bounds),
            grill_preference=_capped_field(1.0, food_deltas.get("grill_preference", []), "grill_preference", {}, bounds),
            fingerfood_preference=_capped_field(1.0, food_deltas.get("fingerfood_preference", []), "fingerfood_preference", {}, bounds),
            dessert_preference=_capped_field(1.0, food_deltas.get("dessert_preference", []), "dessert_preference", {}, bounds),
            spoilage_operational_penalty=spoilage_penalty,
        )

        # --- Music Context Modifiers (§30-§37) ------------------------------------
        music_deltas: dict[str, list[float]] = {}
        for field_name, delta in config.LOCATION_MUSIC_MODIFIER_DELTAS.get(party_context.location_type, {}).items():
            music_deltas.setdefault(field_name, []).append(delta)
        if party_context.neighbors_sensitive:
            for field_name, delta in config.NEIGHBORS_SENSITIVE_MUSIC_DELTAS.items():
                music_deltas.setdefault(field_name, []).append(delta)
            explanations.append("Empfindliche Nachbarn: Bass-lastige und späte High-Energy-Musik werden zurückgestuft.")
        if party_context.music_volume_limit:
            for field_name, delta in config.VOLUME_LIMIT_MUSIC_DELTAS.items():
                music_deltas.setdefault(field_name, []).append(delta)

        music_bounds = config.MUSIC_MODIFIER_FIELD_BOUNDS
        music_modifiers = MusicContextModifiers(
            energy_modifier=_capped_field(0.0, music_deltas.get("energy_modifier", []), "energy_modifier", {}, music_bounds),
            danceability_modifier=_capped_field(0.0, music_deltas.get("danceability_modifier", []), "danceability_modifier", {}, music_bounds),
            conversation_modifier=_capped_field(0.0, music_deltas.get("conversation_modifier", []), "conversation_modifier", {}, music_bounds),
            bass_penalty=_capped_field(0.0, music_deltas.get("bass_penalty", []), "bass_penalty", {}, (0.0, 1.0)),
            late_night_energy_penalty=_capped_field(0.0, music_deltas.get("late_night_energy_penalty", []), "late_night_energy_penalty", {}, (0.0, 1.0)),
            outdoor_modifier=_capped_field(0.0, music_deltas.get("outdoor_modifier", []), "outdoor_modifier", {}, music_bounds),
        )

        derived = DerivedPartyContext(
            season=season,
            daypart_primary=daypart_primary,
            daypart_weights=daypart_weights,
            temperature_class=temperature_class,
            weather_is_actual=weather_is_actual,
            temperature_c=temperature_c,
            weather_condition=weather_condition,
            indoor_outdoor=indoor_outdoor,
            location_type=party_context.location_type,
            group_size_class=group_size_class,
            location_tags=location_tags,
            available_capabilities=available_capabilities,
            operational_constraints=operational_constraints,
            recommendation_tags=recommendation_tags,
            beverage_modifiers=beverage_modifiers,
            food_modifiers=food_modifiers,
            music_modifiers=music_modifiers,
            explanations=explanations,
            context_model_version=config.PARTY_CONTEXT_MODEL_VERSION,
        )

        if overrides:
            derived = _apply_overrides(derived, overrides)

        return derived


def _apply_overrides(derived: DerivedPartyContext, overrides: list[PartyContextOverride]) -> DerivedPartyContext:
    """Admin-Overrides sind stärker als abgeleitete Defaults (§71/§72). Nur
    direkt auf ``DerivedPartyContext`` vorhandene Top-Level-Felder werden
    unterstützt (z.B. ``season``, ``indoor_outdoor``, ``temperature_class``)."""
    for override in overrides:
        if hasattr(derived, override.key):
            setattr(derived, override.key, override.value)
            reason = f" ({override.reason})" if override.reason else ""
            derived.explanations.append(f"Admin-Override: '{override.key}' = {override.value}{reason}")
        elif override.key == "operational_constraints_remove" and isinstance(override.value, (set, list)):
            derived.operational_constraints -= set(override.value)
            reason = f" ({override.reason})" if override.reason else ""
            derived.explanations.append(f"Admin-Override: Constraint(s) {sorted(override.value)} entfernt{reason}")
        elif override.key == "operational_constraints_add" and isinstance(override.value, (set, list)):
            derived.operational_constraints |= set(override.value)
            reason = f" ({override.reason})" if override.reason else ""
            derived.explanations.append(f"Admin-Override: Constraint(s) {sorted(override.value)} hinzugefügt{reason}")
    return derived


if __name__ == "__main__":
    from datetime import datetime

    engine = PartyContextEngine()

    # §67: Sommer-Gartengeburtstag
    summer_ctx = PartyContext(
        occasion_id="birthday",
        start_datetime=datetime(2026, 7, 18, 15, 0),
        duration_hours=8.0,
        guest_count=35,
        location_type="garden",
        indoor_outdoor="outdoor",
        has_grill=True,
        has_kitchen=True,
        has_fridge=True,
        has_bar=False,
        has_coffee_machine=True,
        expected_temperature_c=29.0,
        weather_condition="sunny",
    )
    derived_summer = engine.derive_context(summer_ctx)
    assert derived_summer.season == "summer"
    assert derived_summer.temperature_class == "hot"
    assert derived_summer.weather_is_actual is True
    assert derived_summer.group_size_class == "large_group"
    assert "no_grill" not in derived_summer.operational_constraints
    assert "no_bar_setup" in derived_summer.operational_constraints
    assert derived_summer.beverage_modifiers.water_multiplier > 1.0
    assert derived_summer.beverage_modifiers.ice_multiplier > 1.0
    assert derived_summer.beverage_modifiers.cocktail_complexity_penalty > 0.0
    assert derived_summer.food_modifiers.salad_preference > 1.0
    assert derived_summer.food_modifiers.grill_preference > 1.0
    assert derived_summer.explanations

    # §68: Winter-Scheunengeburtstag
    winter_ctx = PartyContext(
        occasion_id="birthday",
        start_datetime=datetime(2026, 1, 10, 18, 0),
        duration_hours=6.0,
        guest_count=20,
        location_type="barn",
        indoor_outdoor="indoor",
        has_kitchen=False,
        has_fridge=False,
        expected_temperature_c=4.0,
    )
    derived_winter = engine.derive_context(winter_ctx)
    assert derived_winter.season == "winter"
    assert derived_winter.temperature_class == "cold"
    assert derived_winter.beverage_modifiers.hot_drink_multiplier > 1.0
    assert derived_winter.food_modifiers.comfort_food_preference > 1.0
    assert derived_winter.food_modifiers.hot_food_preference > 1.0

    # §87: Fallback ohne Wetterdaten liefert weiterhin vollständigen Kontext
    no_weather_ctx = PartyContext(location_type="apartment", indoor_outdoor="indoor", guest_count=10)
    derived_no_weather = engine.derive_context(no_weather_ctx)
    assert derived_no_weather.weather_is_actual is False
    assert derived_no_weather.temperature_class in ("cold", "cool", "mild", "warm", "hot")

    # §86: tatsächliches Wetter überstimmt Saison
    rainy_july_ctx = PartyContext(
        start_datetime=datetime(2026, 7, 18, 15, 0), expected_temperature_c=15.0, weather_condition="rain", rain_probability=0.8,
        location_type="garden", indoor_outdoor="outdoor",
    )
    derived_rainy = engine.derive_context(rainy_july_ctx)
    assert derived_rainy.season == "summer"
    assert derived_rainy.temperature_class == "mild"  # nicht "hot", trotz Juli
    assert "outdoor_rain_risk" in derived_rainy.operational_constraints

    # §71/§72: Admin-Override
    overrides = [PartyContextOverride(key="temperature_class", value="warm", reason="Zelt mit Heizung")]
    derived_override = engine.derive_context(winter_ctx, overrides=overrides)
    assert derived_override.temperature_class == "warm"
    assert any("Admin-Override" in e for e in derived_override.explanations)

    print(f"summer beverage_modifiers -> {derived_summer.beverage_modifiers}")
    print(f"winter food_modifiers -> {derived_winter.food_modifiers}")
    print("party_context/engine.py sanity check OK.")
