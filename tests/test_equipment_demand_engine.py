"""Tests für ``equipment_engine.engine.calculate_equipment_demand`` gegen
den echten Katalog - mirrort die Teststrategie von ``tests/test_engine_e2e.py``
(reale Pipeline statt isolierter Einzelschritte, Kreuzvalidierung durch
unabhängige Teil-Läufe statt geratener Magic Numbers)."""

from __future__ import annotations

import pytest

from equipment_engine.engine import calculate_equipment_demand


def test_paper_cup_demand_aggregates_from_baseline_and_beer_pong_station(equipment_catalog):
    """paper_cup hat sowohl eine per-guest-Baseline-Regel als auch einen
    per_station-Zuschlag von der Beer-Pong-Station - beide müssen in
    GENAU EINEN Demand-Eintrag münden, mit je einer eigenen Contribution
    (mirrort test_vodka_from_two_different_cocktails_aggregates_into_one_entry)."""
    combined = calculate_equipment_demand(
        equipment_catalog, guest_count=20, station_activity_interest={"beer_pong": 2}
    )
    paper_cup = combined.demand["paper_cup"]
    assert len(paper_cup.contributions) == 2
    sources = {c.source.split(":")[0] for c in paper_cup.contributions}
    assert sources == {"item_baseline", "station"}

    baseline_only = calculate_equipment_demand(equipment_catalog, guest_count=20)
    station_only = calculate_equipment_demand(
        equipment_catalog, guest_count=0, station_activity_interest={"beer_pong": 2}
    )
    assert paper_cup.raw_quantity == pytest.approx(
        baseline_only.demand["paper_cup"].raw_quantity + station_only.demand["paper_cup"].raw_quantity,
        rel=1e-6,
    )
    assert paper_cup.raw_quantity == pytest.approx(60.0)  # 2.0*20 (baseline) + 10.0*2 (station)


def test_reserve_is_applied_once_after_global_aggregation(equipment_catalog):
    result = calculate_equipment_demand(
        equipment_catalog, guest_count=20, station_activity_interest={"beer_pong": 2}
    )
    paper_cup = result.demand["paper_cup"]
    assert paper_cup.reserve_pct == pytest.approx(0.10)
    assert paper_cup.quantity_after_reserve == pytest.approx(paper_cup.raw_quantity * 1.10)
    assert paper_cup.quantity_after_reserve == pytest.approx(66.0)


def test_capacity_based_cooler_rounds_up_from_liters_needed(equipment_catalog):
    """Spec §57's Beispiel exakt: 75L Bedarf / 30L Kapazität pro Kühler = 2.5,
    aufgerundet auf 3 - die Division selbst rundet NICHT (2.5 bleibt bis zur
    finalen Beschaffungsrundung erhalten)."""
    result = calculate_equipment_demand(
        equipment_catalog, guest_count=30, capacity_need_overrides={"large_beverage_cooler": 75.0}
    )
    cooler = result.demand["large_beverage_cooler"]
    assert cooler.raw_quantity == pytest.approx(2.5)
    assert cooler.quantity_after_reserve == pytest.approx(2.5)  # reserve_pct=0.0 auf diesem Item
    assert cooler.missing_quantity == pytest.approx(2.5)  # kein Inventar
    assert cooler.final_required_quantity == 3

    plan_item = next(p for p in result.purchase_plan if p.item_id == "large_beverage_cooler")
    assert plan_item.total_purchased_quantity == 3
    assert plan_item.sku_breakdown == []  # rental, keine SKU-Verpackung


def test_per_station_beer_pong_table_scales_with_station_count_not_guest_count(equipment_catalog):
    small = calculate_equipment_demand(equipment_catalog, guest_count=10, station_activity_interest={"beer_pong": 2})
    large = calculate_equipment_demand(equipment_catalog, guest_count=200, station_activity_interest={"beer_pong": 2})
    assert small.demand["beer_pong_table"].raw_quantity == large.demand["beer_pong_table"].raw_quantity == 2.0
    assert small.demand["beer_pong_rack"].raw_quantity == large.demand["beer_pong_rack"].raw_quantity == 4.0


def test_optional_game_item_only_included_when_selected(equipment_catalog):
    without = calculate_equipment_demand(equipment_catalog, guest_count=20)
    assert "cornhole_set" not in without.demand
    assert "dinner_plate" in without.demand  # always_on-Baseline ist immer da

    with_selection = calculate_equipment_demand(equipment_catalog, guest_count=20, selected_item_ids=["cornhole_set"])
    assert "cornhole_set" in with_selection.demand
    assert with_selection.demand["cornhole_set"].raw_quantity == 1.0


def test_fixed_driver_item_ignores_guest_count(equipment_catalog):
    small = calculate_equipment_demand(equipment_catalog, guest_count=5)
    large = calculate_equipment_demand(equipment_catalog, guest_count=500)
    assert small.demand["cocktail_shaker"].raw_quantity == large.demand["cocktail_shaker"].raw_quantity == 1.0
