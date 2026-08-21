"""Tests für ``party_engine.purchasing`` - Rundung erfolgt AUSSCHLIESSLICH im
letzten Pipelineschritt, immer aufgerundet (AUFGABE §36)."""

from __future__ import annotations

import pytest

from party_engine.purchasing import optimize_purchase
from party_engine.domain import PurchaseSKU


def test_purchase_rounding_rounds_up_never_down():
    skus = [PurchaseSKU(ingredient_id="vodka", size=0.7, unit="l", pack_label="0.7L", pack_count=1)]
    breakdown = optimize_purchase(0.75, skus)
    total = sum(b.size * b.count for b in breakdown)
    # 0.75 L Bedarf mit nur 0.7L-Flaschen -> muss auf 2 Flaschen (1.4L) aufgerundet
    # werden, NICHT auf 1 Flasche (0.7L, das wäre Abrunden = Fehlmenge).
    assert total >= 0.75
    assert total == pytest.approx(1.4)


def test_purchase_rounding_exact_multiple_no_overage():
    skus = [PurchaseSKU(ingredient_id="water", size=1.5, unit="l", pack_label="1.5L", pack_count=1)]
    breakdown = optimize_purchase(3.0, skus)
    total = sum(b.size * b.count for b in breakdown)
    assert total == pytest.approx(3.0)


def test_end_to_end_ingredient_demand_is_not_rounded_before_purchase_step(catalog, config):
    """AUFGABE §36: quantity_after_reserve (Ergebnis der Reserve-Stufe) darf
    selbst NICHT bereits auf ein Gebinde gerundet sein - Rundung passiert
    erst beim Bau des Purchase-Plans."""
    from party_engine.domain import GuestResponse
    from party_engine.engine import compute_party_demand

    responses = [
        GuestResponse(guest_name="A", start_time="18:00", drink_selections=["espresso_martini"]),
        GuestResponse(guest_name="B", start_time="18:00", drink_selections=["moscow_mule"]),
    ]
    result = compute_party_demand(catalog, responses, config)
    vodka = result.ingredient_demand["vodka"]

    vodka_skus = {round(s.size, 6) for s in catalog.purchase_skus.get("vodka", [])}
    # Die (nicht gerundete) Bedarfsmenge nach Reserve darf i.d.R. NICHT exakt
    # einer SKU-Größe entsprechen (reines Rechenergebnis, keine Rundung).
    assert round(vodka.quantity_after_reserve, 6) not in vodka_skus

    purchase_item = next(p for p in result.purchase_plan if p.ingredient_id == "vodka")
    # Der finale Einkaufsplan MUSS mindestens den (reserve-behafteten) Bedarf
    # decken (aufgerundet), niemals darunter liegen.
    assert purchase_item.total_purchased_quantity >= vodka.quantity_after_reserve - 1e-9
