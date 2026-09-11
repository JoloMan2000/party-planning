"""Tests für ``equipment_engine.purchasing.build_equipment_purchase_plan`` -
unit-testet den Beschaffungs-Rundungsschritt direkt gegen manuell gebaute
``EquipmentDemand``-Objekte statt über die volle Pipeline (mirrort
``tests/test_purchasing.py``'s direkten ``optimize_purchase``-Test-Stil)."""

from __future__ import annotations

from equipment_engine.domain import EquipmentCatalog, EquipmentDemand, EquipmentItem
from equipment_engine.purchasing import build_equipment_purchase_plan


def test_consumable_napkin_demand_rounds_up_to_pack_count(equipment_catalog):
    """Spec §72's Beispiel exakt: Bedarf 118, Gebinde Pack-of-50 -> 3 Packs, 150 Stück."""
    demand = {
        "cocktail_napkin": EquipmentDemand(
            item_id="cocktail_napkin", name="Cocktail Napkin", unit="pcs", missing_quantity=118.0
        )
    }
    plan, issues = build_equipment_purchase_plan(demand, equipment_catalog)
    assert issues == []
    assert len(plan) == 1
    item = plan[0]
    assert item.total_purchased_quantity == 150
    assert len(item.sku_breakdown) == 1
    assert item.sku_breakdown[0].count == 3
    assert item.sku_breakdown[0].size == 50


def test_durable_item_rounds_to_whole_units_without_sku_packing(equipment_catalog):
    demand = {
        "dinner_plate": EquipmentDemand(item_id="dinner_plate", name="Dinner Plate", unit="pcs", missing_quantity=2.2)
    }
    plan, issues = build_equipment_purchase_plan(demand, equipment_catalog)
    assert issues == []
    item = plan[0]
    assert item.sku_breakdown == []
    assert item.total_purchased_quantity == 3


def test_missing_purchase_sku_creates_review_issue():
    """Ein Consumable mit Bedarf, aber ohne hinterlegtes PurchaseSKU, muss
    einen ReviewIssue erzeugen statt eine falsche Präzision vorzutäuschen -
    mirrort ``party_engine/purchasing.py``'s identisches Verhalten."""
    catalog = EquipmentCatalog(
        items={
            "mystery_item": EquipmentItem(
                id="mystery_item", name="Mystery Item", category_id="tableware", equipment_type="consumable"
            )
        }
    )
    demand = {
        "mystery_item": EquipmentDemand(item_id="mystery_item", name="Mystery Item", unit="pcs", missing_quantity=5.0)
    }
    plan, issues = build_equipment_purchase_plan(demand, catalog)
    assert len(plan) == 1
    assert plan[0].total_purchased_quantity == 0
    assert plan[0].sku_breakdown == []
    assert len(issues) == 1
    assert issues[0].issue_type == "ambiguous"
    assert issues[0].guest_name == ""
