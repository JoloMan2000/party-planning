"""Tests für ``equipment_engine.context`` (Phase 2: PartyContext-Integration)
- reine Funktionstests gegen handgebaute ``DerivedPartyContext``/
``EquipmentDemand``-Objekte, kein DB-/API-Involvement (mirrort
``equipment_engine``'s DB-freie Testphilosophie für Pipeline-Bausteine)."""

from __future__ import annotations

from party_context.domain import DerivedPartyContext

from equipment_engine.context import (
    compute_context_recommendations,
    compute_missing_capability_issues,
    compute_seating_and_table_capacity_needs,
)
from equipment_engine.domain import EquipmentDemand


def test_rain_trigger_recommends_gazebo_when_outdoor_and_rain_risk(equipment_catalog):
    ctx = DerivedPartyContext(indoor_outdoor="outdoor", operational_constraints={"outdoor_rain_risk"})
    recs = compute_context_recommendations(equipment_catalog, ctx, selected_item_ids=[])
    assert "rain_cover_gazebo" in {r.item_id for r in recs}


def test_no_rain_recommendation_without_rain_risk_constraint(equipment_catalog):
    ctx = DerivedPartyContext(indoor_outdoor="outdoor")
    recs = compute_context_recommendations(equipment_catalog, ctx, selected_item_ids=[])
    assert "rain_cover_gazebo" not in {r.item_id for r in recs}


def test_heat_trigger_recommends_parasol_when_outdoor_and_hot(equipment_catalog):
    ctx = DerivedPartyContext(indoor_outdoor="outdoor", temperature_class="hot")
    recs = compute_context_recommendations(equipment_catalog, ctx, selected_item_ids=[])
    assert "sun_shade_parasol" in {r.item_id for r in recs}


def test_cold_trigger_recommends_heater_when_outdoor_and_cold(equipment_catalog):
    ctx = DerivedPartyContext(indoor_outdoor="outdoor", temperature_class="cold")
    recs = compute_context_recommendations(equipment_catalog, ctx, selected_item_ids=[])
    assert "outdoor_heater" in {r.item_id for r in recs}


def test_indoor_party_gets_no_weather_recommendations(equipment_catalog):
    ctx = DerivedPartyContext(
        indoor_outdoor="indoor", temperature_class="hot", operational_constraints={"outdoor_rain_risk"}
    )
    recs = compute_context_recommendations(equipment_catalog, ctx, selected_item_ids=[])
    assert recs == []


def test_already_selected_item_is_not_recommended_again(equipment_catalog):
    ctx = DerivedPartyContext(indoor_outdoor="outdoor", temperature_class="hot")
    recs = compute_context_recommendations(equipment_catalog, ctx, selected_item_ids=["sun_shade_parasol"])
    assert "sun_shade_parasol" not in {r.item_id for r in recs}


def test_missing_capability_raises_review_issue_for_string_lights_without_power(equipment_catalog):
    demand = {
        "outdoor_string_lights": EquipmentDemand(
            item_id="outdoor_string_lights", name="Outdoor String Lights", unit="pcs",
            raw_quantity=1.0, quantity_after_reserve=1.0,
        )
    }
    ctx = DerivedPartyContext(available_capabilities=set())  # kein "power"
    issues = compute_missing_capability_issues(demand, equipment_catalog, ctx)
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_capability"
    assert "power" in issues[0].message


def test_no_missing_capability_issue_when_power_available(equipment_catalog):
    demand = {
        "outdoor_string_lights": EquipmentDemand(
            item_id="outdoor_string_lights", name="Outdoor String Lights", unit="pcs",
            raw_quantity=1.0, quantity_after_reserve=1.0,
        )
    }
    ctx = DerivedPartyContext(available_capabilities={"power"})
    assert compute_missing_capability_issues(demand, equipment_catalog, ctx) == []


def test_no_missing_capability_issue_when_item_not_actually_demanded(equipment_catalog):
    demand = {
        "outdoor_string_lights": EquipmentDemand(
            item_id="outdoor_string_lights", name="Outdoor String Lights", unit="pcs",
            raw_quantity=0.0, quantity_after_reserve=0.0,
        )
    }
    ctx = DerivedPartyContext(available_capabilities=set())
    assert compute_missing_capability_issues(demand, equipment_catalog, ctx) == []


def test_seating_and_table_capacity_needs_matches_spec_59_example():
    needs = compute_seating_and_table_capacity_needs(guest_count=40, seating_ratio=0.60)
    assert needs["folding_chair"] == 24.0  # Spec §59: 40 * 0.60 = 24


def test_seating_defaults_to_point_six_when_seating_ratio_missing():
    needs = compute_seating_and_table_capacity_needs(guest_count=40, seating_ratio=None)
    assert needs["folding_chair"] == 24.0


def test_table_capacity_needs_are_raw_guest_count_for_rule_to_divide():
    needs = compute_seating_and_table_capacity_needs(guest_count=40, seating_ratio=0.6)
    assert needs["dining_table"] == 40.0
    assert needs["buffet_table"] == 40.0
