"""Einkaufsplan-Erstellung (Phase 1) - rundet als EINZIGER Schritt der
gesamten Pipeline (mirrort ``party_engine/purchasing.py``). Für
Verbrauchsmaterial (``equipment_type="consumable"``) wird die bestehende,
generische ``optimize_purchase`` aus ``party_engine.purchasing``
WIEDERVERWENDET (kein Duplikat - Greedy-Bin-Packing über ``PurchaseSKU``s,
größte Gebinde zuerst, rundet nur am Ende). Für durable/rental Items gibt
es keine Gebinde-Logik - man kauft/mietet Tische nicht im 6er-Pack -
dort wird stattdessen auf ganze Einheiten aufgerundet."""

from __future__ import annotations

import math

from party_engine.purchasing import optimize_purchase

from equipment_engine.domain import (
    EquipmentCatalog,
    EquipmentDemand,
    EquipmentPurchasePlanItem,
    ReviewIssue,
)

_EPSILON = 1e-9

_NO_SKU_PACKING_TYPES = ("durable", "rental")


def build_equipment_purchase_plan(
    demand: dict[str, EquipmentDemand], catalog: EquipmentCatalog
) -> tuple[list[EquipmentPurchasePlanItem], list[ReviewIssue]]:
    plan: list[EquipmentPurchasePlanItem] = []
    issues: list[ReviewIssue] = []

    for item_id, entry in sorted(demand.items(), key=lambda kv: kv[1].name):
        if entry.missing_quantity <= _EPSILON:
            continue

        item = catalog.items.get(item_id)
        if item is not None and item.equipment_type in _NO_SKU_PACKING_TYPES:
            total = math.ceil(entry.missing_quantity - _EPSILON)
            entry.final_required_quantity = total
            plan.append(
                EquipmentPurchasePlanItem(
                    item_id=item_id, name=entry.name, quantity_needed=entry.missing_quantity,
                    unit=entry.unit, sku_breakdown=[], total_purchased_quantity=total,
                )
            )
            continue

        skus = catalog.purchase_skus.get(item_id, [])
        breakdown = optimize_purchase(entry.missing_quantity, skus)
        if not breakdown:
            issues.append(
                ReviewIssue(
                    guest_name="",
                    raw_text=item_id,
                    issue_type="ambiguous",
                    message=(
                        f'Equipment "{entry.name}" hat Bedarf '
                        f"({entry.missing_quantity:.2f} {entry.unit}), aber kein "
                        "hinterlegtes Einkaufsgebinde (PurchaseSKU)."
                    ),
                )
            )
        total_purchased = sum(b.size * b.count for b in breakdown)
        entry.final_required_quantity = total_purchased
        plan.append(
            EquipmentPurchasePlanItem(
                item_id=item_id, name=entry.name, quantity_needed=entry.missing_quantity,
                unit=entry.unit, sku_breakdown=breakdown, total_purchased_quantity=total_purchased,
            )
        )

    return plan, issues
