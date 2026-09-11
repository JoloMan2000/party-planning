"""Tests für ``equipment_engine.catalog`` gegen den ECHTEN Katalog (kein
Mocking, mirrort ``tests/test_engine_e2e.py``'s Konvention) - nutzt die
session-gescopte ``equipment_catalog``-Fixture aus ``tests/conftest.py``."""

from __future__ import annotations


def test_catalog_item_count_within_phase1_target(equipment_catalog):
    assert 50 <= len(equipment_catalog.items) <= 80


def test_every_item_subcategory_belongs_to_its_top_level_category(equipment_catalog):
    for item in equipment_catalog.items.values():
        assert item.category_id in equipment_catalog.categories
        if item.subcategory_id is not None:
            sub = equipment_catalog.categories[item.subcategory_id]
            assert sub.parent_id == item.category_id


def test_every_item_demand_rule_id_resolves(equipment_catalog):
    for item in equipment_catalog.items.values():
        if item.demand_rule_id is not None:
            assert item.demand_rule_id in equipment_catalog.demand_rules


def test_search_by_category_returns_only_matching_items(equipment_catalog):
    results = equipment_catalog.search(category_id="ice_cooling")
    assert {r.id for r in results} == {"ice_bucket", "cooler_box", "cool_bag", "large_beverage_cooler"}


def test_search_by_equipment_type_excludes_other_types(equipment_catalog):
    results = equipment_catalog.search(equipment_type="rental")
    assert all(r.equipment_type == "rental" for r in results)
    assert "large_beverage_cooler" in {r.id for r in results}
    assert "cooler_box" not in {r.id for r in results}


def test_search_active_only_default_excludes_inactive_items(equipment_catalog):
    # Kein inaktives Item im Phase-1-Katalog vorgesehen - Sanity-Check, dass
    # active_only zumindest nichts fälschlich rausfiltert.
    assert len(equipment_catalog.search(active_only=True)) == len(equipment_catalog.items)


def test_beer_pong_top_up_rule_targets_a_real_item_not_owned_by_it(equipment_catalog):
    topup = equipment_catalog.demand_rules["rule_paper_cup_beer_pong_topup"]
    assert topup.driver_type == "per_station"
    assert topup.target_item_id == "paper_cup"
    target_item = equipment_catalog.items["paper_cup"]
    # paper_cup's OWN demand_rule_id ist die per-guest-Baseline, nicht der Zuschlag.
    assert target_item.demand_rule_id == "rule_paper_cup"
