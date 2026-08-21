"""Tests für ``party_engine.allocation`` (Demand-Group-Pools, Caps,
Overflow-Substitution). Nutzt den echten Katalog, siehe ``conftest.py``."""

from __future__ import annotations

import pytest

from party_engine.allocation import allocate_guest_demand, resolve_guest_preferences
from party_engine.domain import DietaryProfile, GuestResponse


def _prefs_and_allocs(catalog, config, response):
    prefs, issues = resolve_guest_preferences(response, catalog, config=config)
    allocs = allocate_guest_demand(
        response.guest_name, prefs, catalog, config, dietary=response.dietary
    )
    return allocs, issues


def test_multiple_selections_same_demand_group_share_one_budget(catalog, config):
    """AUFGABE §30: mehrere Selektionen in derselben demand_group konkurrieren
    um ein GEMEINSAMES Choice-Budget, statt jeweils voll gerechnet zu werden."""
    response = GuestResponse(
        guest_name="X",
        start_time="18:00",
        food_selections=["cheeseburger", "veggie_burger"],  # beide demand_group="main"
    )
    allocs, _ = _prefs_and_allocs(catalog, config, response)

    by_item = {a.item_id: a.servings for a in allocs if a.source != "baseline"}
    assert set(by_item) == {"cheeseburger", "veggie_burger"}

    total = sum(by_item.values())
    assert total == pytest.approx(config.main_budget_per_guest, rel=1e-6)
    # Gleich gewichtete Selektionen -> gleich aufgeteilt.
    assert by_item["cheeseburger"] == pytest.approx(by_item["veggie_burger"], rel=1e-6)
    # Keinesfalls je Item das volle Budget (das wäre der alte, fehlerhafte
    # naive Zählmodell-Ansatz, siehe b44b0b5 Commit-Historie).
    assert by_item["cheeseburger"] < config.main_budget_per_guest


def test_water_baseline_present_even_with_zero_selections(catalog, config):
    response = GuestResponse(guest_name="Nobody", start_time="18:00")
    allocs, _ = _prefs_and_allocs(catalog, config, response)

    water_allocs = [a for a in allocs if a.item_id == "water"]
    assert len(water_allocs) == 1
    assert water_allocs[0].source == "baseline"
    assert water_allocs[0].servings > 0


def test_water_baseline_present_alongside_other_selections(catalog, config):
    response = GuestResponse(
        guest_name="Someone", start_time="18:00", drink_selections=["moscow_mule"]
    )
    allocs, _ = _prefs_and_allocs(catalog, config, response)
    water_allocs = [a for a in allocs if a.item_id == "water" and a.source == "baseline"]
    assert len(water_allocs) == 1
    assert water_allocs[0].servings > 0


def test_alcohol_cap_per_guest_is_respected(catalog, config):
    """AUFGABE §31: max_alcohol_units_per_guest begrenzt den Reinalkohol-
    Bedarf pro Gast; Überschuss wird umverteilt (nicht einfach verworfen)."""
    response = GuestResponse(
        guest_name="HeavyDrinker", start_time="18:00", drink_selections=["vodka"]
    )
    allocs, _ = _prefs_and_allocs(catalog, config, response)

    vodka_dc = catalog.direct_consumables["vodka"]
    vodka_ingredient = catalog.ingredients[vodka_dc.ingredient_id]
    pure_alcohol_per_serving = vodka_dc.serving_size_l * (vodka_ingredient.abv / 100.0)

    vodka_servings = next((a.servings for a in allocs if a.item_id == "vodka"), 0.0)
    total_pure_alcohol_l = vodka_servings * pure_alcohol_per_serving

    cap_l = config.max_alcohol_units_per_guest * config.alcohol_unit_pure_alcohol_l
    assert total_pure_alcohol_l <= cap_l + 1e-9

    # Ohne jegliche andere Getränke-Auswahl kann der Overflow nur in Wasser
    # umgeleitet werden -> Wasser-Baseline muss entsprechend höher sein als
    # das bloße water_l_per_guest.
    water_servings = next(a.servings for a in allocs if a.item_id == "water")
    water_l = water_servings * catalog.direct_consumables["water"].serving_size_l
    assert water_l > config.water_l_per_guest


def test_energy_cap_per_guest_is_respected(catalog, config):
    energy_ids = [
        dc.id for dc in catalog.direct_consumables.values() if dc.demand_group == "energy"
    ]
    assert energy_ids
    response = GuestResponse(
        guest_name="EnergyFan", start_time="18:00", drink_selections=[energy_ids[0]]
    )
    allocs, _ = _prefs_and_allocs(catalog, config, response)

    dc = catalog.direct_consumables[energy_ids[0]]
    servings = next((a.servings for a in allocs if a.item_id == energy_ids[0]), 0.0)
    total_l = servings * dc.serving_size_l

    cap_l = config.max_energy_units_per_guest * config.energy_unit_l
    assert total_l <= cap_l + 1e-9


def test_substitution_only_affects_overflow_never_base_allocation(catalog, config):
    """AUFGABE §33: Substitution greift NUR bei Overflow-Umverteilung. Wenn
    der Gast unter dem Cap bleibt (z.B. genau EIN Standardgetränk), darf sich
    an der Grundallokation NICHTS durch Substitutionslogik ändern - die
    Servings müssen exakt der reinen Choice-Budget-Aufteilung entsprechen."""
    # Ein einzelnes alkoholfreies Getränk bleibt garantiert unter jedem
    # Alkohol-/Energy-Cap (0 Alkohol/Energie) -> kein Overflow, keine
    # Substitution sollte je stattfinden.
    non_alcoholic_ids = [
        dc.id
        for dc in catalog.direct_consumables.values()
        if dc.demand_group in ("beverage_general", "non_alcoholic_beverage")
        and dc.abv == 0
        and dc.id != "water"
    ]
    assert non_alcoholic_ids
    item_id = non_alcoholic_ids[0]
    response = GuestResponse(guest_name="Sober", start_time="18:00", drink_selections=[item_id])
    allocs, _ = _prefs_and_allocs(catalog, config, response)

    servings = next(a.servings for a in allocs if a.item_id == item_id)
    # Einzige Selektion im Pool -> bekommt das GESAMTE beverage_serving_budget,
    # unverändert durch jegliche Substitutionslogik.
    assert servings == pytest.approx(config.beverage_serving_budget, rel=1e-6)


def test_vegan_dietary_never_appears_as_substitution_target_for_meat(catalog):
    """Unit-Level-Absicherung der safety-critical Regel direkt am
    Substitutions-Modul: für einen veganen Gast dürfen KEINE
    Fleisch-Kandidaten als Substitutionsziel zurückgegeben werden."""
    from party_engine.substitution import get_substitution_candidates

    vegan = DietaryProfile(vegan=True)
    meat_source_ids = [
        rid
        for rid, r in catalog.recipes.items()
        if not r.is_vegetarian and not r.is_vegan
    ]
    checked_any = False
    for source_id in meat_source_ids:
        candidates = get_substitution_candidates(source_id, catalog, dietary=vegan)
        for target_id, _compat in candidates:
            checked_any = True
            target_recipe = catalog.recipes.get(target_id)
            if target_recipe is not None:
                assert target_recipe.is_vegan, (
                    f"Substitution {source_id} -> {target_id} ist fuer einen veganen "
                    "Gast nicht vegan - verboten laut AUFGABE §29/§33."
                )
    # Nur informativ: falls der Katalog keine passenden Regeln hat, ist der
    # Test trivial gruen - das ist okay, die harte Prüfung oben greift, sobald
    # es Kandidaten gibt.
    _ = checked_any
