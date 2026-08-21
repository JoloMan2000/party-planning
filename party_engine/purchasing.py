"""
Purchase SKU Optimization
=========================

Letzter Schritt der Pipeline: rundet den (bereits reserve-behafteten)
Ingredient-Bedarf auf reale Einkaufsgebinde (§35-36, §41).

Designentscheidung (Bin-Packing-Strategie): einfaches, deterministisches
Greedy-Verfahren - Gebinde werden nach gelieferter Menge (``size * pack_count``)
absteigend sortiert, größte Gebinde zuerst so oft wie möglich verwendet,
danach kleinere für den Rest. Bleibt am Ende ein (kleiner) Rest > 0 übrig,
wird zusätzlich EIN weiteres Gebinde der kleinsten verfügbaren Größe
gekauft (Aufrunden erst hier, nicht vorher - §36). Das ist kein optimales
Bin-Packing (das wäre NP-hart), aber für Party-Einkaufslisten mit wenigen,
großzügig bemessenen Gebindegrößen praxistauglich und nachvollziehbar.
"""

from __future__ import annotations

from party_engine.domain import (
    IngredientDemand,
    PartyCatalog,
    PurchasePlanItem,
    PurchaseSKU,
    ReviewIssue,
    SKUBreakdownEntry,
)

_EPSILON = 1e-9


def _pack_volume(sku: PurchaseSKU) -> float:
    return sku.size * max(sku.pack_count, 1)


def optimize_purchase(quantity_needed: float, skus: list[PurchaseSKU]) -> list[SKUBreakdownEntry]:
    if quantity_needed <= _EPSILON or not skus:
        return []

    sorted_skus = sorted(skus, key=_pack_volume, reverse=True)
    remaining = quantity_needed
    counts: dict[int, int] = {i: 0 for i in range(len(sorted_skus))}

    for i, sku in enumerate(sorted_skus):
        pack_vol = _pack_volume(sku)
        if pack_vol <= 0:
            continue
        n = int(remaining / pack_vol + 1e-9)
        if n > 0:
            counts[i] += n
            remaining -= n * pack_vol

    if remaining > _EPSILON:
        # kleinstes Gebinde für den Rest aufrunden (§36: erst hier runden)
        smallest_idx = min(range(len(sorted_skus)), key=lambda i: _pack_volume(sorted_skus[i]))
        counts[smallest_idx] += 1

    breakdown: list[SKUBreakdownEntry] = []
    for i, sku in enumerate(sorted_skus):
        if counts[i] > 0:
            # Designentscheidung: ``SKUBreakdownEntry.size`` bildet die pro
            # gekaufter Einheit GELIEFERTE Gesamtmenge ab (size * pack_count,
            # z.B. 6 Stück für einen "6er Pack" oder 9 L für einen
            # "Kasten (6x1,5L)"), da das Domain-Modell kein separates
            # ``pack_count``-Feld auf ``SKUBreakdownEntry`` vorsieht.
            breakdown.append(
                SKUBreakdownEntry(
                    size=_pack_volume(sku), unit=sku.unit, count=counts[i], pack_label=sku.pack_label
                )
            )
    return breakdown


def build_purchase_plan(
    demand: dict[str, IngredientDemand], catalog: PartyCatalog
) -> tuple[list[PurchasePlanItem], list[ReviewIssue]]:
    plan: list[PurchasePlanItem] = []
    issues: list[ReviewIssue] = []

    for ingredient_id, entry in sorted(demand.items(), key=lambda kv: kv[1].name):
        if entry.quantity_after_reserve <= _EPSILON:
            continue
        skus = catalog.purchase_skus.get(ingredient_id, [])
        breakdown = optimize_purchase(entry.quantity_after_reserve, skus)

        if not breakdown:
            issues.append(
                ReviewIssue(
                    guest_name="",
                    raw_text=ingredient_id,
                    issue_type="ambiguous",
                    message=(
                        f'Für Zutat "{entry.name}" existiert Bedarf '
                        f"({entry.quantity_after_reserve:.2f} {entry.unit}), aber kein "
                        "hinterlegtes Einkaufsgebinde (PurchaseSKU)."
                    ),
                )
            )

        total_purchased = sum(b.size * b.count for b in breakdown)
        plan.append(
            PurchasePlanItem(
                ingredient_id=ingredient_id,
                name=entry.name,
                quantity_needed=entry.quantity_after_reserve,
                unit=entry.unit,
                sku_breakdown=breakdown,
                total_purchased_quantity=total_purchased,
            )
        )

    return plan, issues
