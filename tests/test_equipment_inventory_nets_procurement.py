"""Tests für ``equipment_engine.demand.net_against_inventory`` - Spec §8:
Required - Existing = Procurement Need."""

from __future__ import annotations

from equipment_engine.demand import net_against_inventory
from equipment_engine.domain import EquipmentDemand, PartyEquipmentInventoryItem


def test_host_inventory_reduces_missing_quantity():
    """Spec §8's Beispiel exakt: Required 24, Host besitzt 12 -> Need 12."""
    demand = {
        "wine_glass": EquipmentDemand(item_id="wine_glass", name="Wine Glass", unit="pcs", quantity_after_reserve=24.0)
    }
    inventory = [
        PartyEquipmentInventoryItem(id="inv1", owner_user_id="host1", equipment_item_id="wine_glass", quantity=12.0)
    ]
    result = net_against_inventory(demand, inventory)
    assert result["wine_glass"].existing_quantity == 12.0
    assert result["wine_glass"].missing_quantity == 12.0


def test_unavailable_inventory_row_does_not_offset_demand():
    demand = {
        "wine_glass": EquipmentDemand(item_id="wine_glass", name="Wine Glass", unit="pcs", quantity_after_reserve=24.0)
    }
    inventory = [
        PartyEquipmentInventoryItem(
            id="inv1", owner_user_id="host1", equipment_item_id="wine_glass", quantity=12.0, available=False
        )
    ]
    result = net_against_inventory(demand, inventory)
    assert result["wine_glass"].existing_quantity == 0.0
    assert result["wine_glass"].missing_quantity == 24.0


def test_multiple_inventory_rows_for_same_item_are_summed():
    demand = {
        "wine_glass": EquipmentDemand(item_id="wine_glass", name="Wine Glass", unit="pcs", quantity_after_reserve=24.0)
    }
    inventory = [
        PartyEquipmentInventoryItem(id="inv1", owner_user_id="host1", equipment_item_id="wine_glass", quantity=8.0),
        PartyEquipmentInventoryItem(id="inv2", owner_user_id="host1", equipment_item_id="wine_glass", quantity=10.0),
    ]
    result = net_against_inventory(demand, inventory)
    assert result["wine_glass"].existing_quantity == 18.0
    assert result["wine_glass"].missing_quantity == 6.0


def test_more_inventory_than_needed_clamps_missing_to_zero():
    demand = {
        "wine_glass": EquipmentDemand(item_id="wine_glass", name="Wine Glass", unit="pcs", quantity_after_reserve=24.0)
    }
    inventory = [
        PartyEquipmentInventoryItem(id="inv1", owner_user_id="host1", equipment_item_id="wine_glass", quantity=40.0)
    ]
    result = net_against_inventory(demand, inventory)
    assert result["wine_glass"].missing_quantity == 0.0
