"""Tests für ``equipment_engine.food_beverage_integration`` (Phase 3: echte
Food-/Beverage-Plan-Integration) - reine Funktionstests gegen handgebaute
``PartyDemandResult``-Objekte, aber den ECHTEN ``catalog``-Fixture (party_engine's
``PartyCatalog``, mirrort ``equipment_catalog``'s Verwendung in
``tests/test_equipment_context.py``) für realistische Ingredient-Families."""

from __future__ import annotations

from party_engine.domain import IngredientDemand, ItemDemandSummary, PartyDemandResult

from equipment_engine.food_beverage_integration import (
    compute_beverage_capacity_needs,
    compute_food_triggered_item_ids,
)


def _ingredient_demand(ingredient_id: str, liters: float) -> IngredientDemand:
    return IngredientDemand(
        ingredient_id=ingredient_id, name=ingredient_id, unit="l",
        raw_quantity=liters, quantity_after_reserve=liters,
    )


def test_cold_beverage_families_sum_into_cooler_capacity_need(catalog):
    result = PartyDemandResult(
        ingredient_demand={
            "beer_pils": _ingredient_demand("beer_pils", 10.0),  # family "beer" - cold
            "cola": _ingredient_demand("cola", 5.0),  # family "softdrink" - cold
        }
    )
    needs = compute_beverage_capacity_needs(result, catalog)
    assert needs["large_beverage_cooler"] == 15.0


def test_non_cold_families_excluded_from_cooler_capacity_need(catalog):
    spirit_id = next(i.id for i in catalog.ingredients.values() if i.family in ("spirit", "wine", "liqueur"))
    result = PartyDemandResult(ingredient_demand={spirit_id: _ingredient_demand(spirit_id, 100.0)})
    needs = compute_beverage_capacity_needs(result, catalog)
    assert needs["large_beverage_cooler"] == 0.0


def test_ice_bag_capacity_need_equals_ice_demand_kg_directly(catalog):
    result = PartyDemandResult(ice_demand_kg=12.5)
    needs = compute_beverage_capacity_needs(result, catalog)
    assert needs["ice_bag"] == 12.5


def test_cake_with_positive_servings_triggers_cake_accessories():
    result = PartyDemandResult(
        item_demand=[ItemDemandSummary(item_id="kaesekuchen", item_name="Käsekuchen", item_type="recipe", supporters=1, expected_servings=4.0)]
    )
    assert compute_food_triggered_item_ids(result) == {"cake_knife", "cake_server"}


def test_cake_with_zero_servings_does_not_trigger():
    result = PartyDemandResult(
        item_demand=[ItemDemandSummary(item_id="kaesekuchen", item_name="Käsekuchen", item_type="recipe", supporters=0, expected_servings=0.0)]
    )
    assert compute_food_triggered_item_ids(result) == set()


def test_non_cake_dessert_does_not_trigger():
    result = PartyDemandResult(
        item_demand=[ItemDemandSummary(item_id="cupcakes", item_name="Cupcakes", item_type="recipe", supporters=1, expected_servings=6.0)]
    )
    assert compute_food_triggered_item_ids(result) == set()


def test_no_item_demand_at_all_does_not_trigger():
    assert compute_food_triggered_item_ids(PartyDemandResult()) == set()
