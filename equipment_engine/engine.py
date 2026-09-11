"""Haupteinstiegspunkt der Equipment Engine (Phase 1) - mirrort
``party_engine.engine.compute_party_demand`` / ``music_engine.engine.plan_party_music``
(eine schlichte Top-Level-Funktion, KEINE Engine-Klasse - abweichend vom
Klassen-Beispiel der rohen Spec §168, aber konsistent mit jedem anderen
Planning-Entry-Point dieser Codebase)."""

from __future__ import annotations

from equipment_engine.demand import aggregate_equipment_demand, apply_reserve, net_against_inventory
from equipment_engine.domain import EquipmentCatalog, EquipmentDemandResult, PartyEquipmentInventoryItem
from equipment_engine.purchasing import build_equipment_purchase_plan


def calculate_equipment_demand(
    catalog: EquipmentCatalog,
    *,
    guest_count: int,
    selected_item_ids: list[str] | None = None,
    station_activity_interest: dict[str, int] | None = None,
    capacity_need_overrides: dict[str, float] | None = None,
    host_inventory: list[PartyEquipmentInventoryItem] | None = None,
) -> EquipmentDemandResult:
    """Phase-1-Einstiegspunkt. Bewusst NICHT die volle Signatur aus Spec §12
    (``party, derived_context, guest_responses, food_plan, beverage_plan,
    music_plan``) - siehe ``equipment_engine/__init__.py`` für die
    geplanten Phase-2/3-Landeplätze. Zwei Parameter sind explizite
    Phase-1-Platzhalter für noch nicht gebaute Features:

    ``station_activity_interest``: Platzhalter für echte Activities +
    Gäste-Voting (Phase 3, Spec §89/§90). Wert = Anzahl GLEICHZEITIGER
    Stationen für diese ``station_id`` DIREKT - noch kein von Popularität/
    Fläche abgeleiteter Stationsanzahl-Algorithmus (Spec §58, Phase 3).

    ``capacity_need_overrides``: Platzhalter für echte Beverage-/Food-Plan-
    Anbindung (Phase 2). ``item_id -> Rohbedarf`` in der Treiber-Einheit
    des Items (z.B. Liter gekühlter Getränke für "large_beverage_cooler").
    """
    selected_item_ids = selected_item_ids or []
    station_activity_interest = station_activity_interest or {}
    capacity_need_overrides = capacity_need_overrides or {}
    host_inventory = host_inventory or []

    raw = aggregate_equipment_demand(
        catalog,
        guest_count=guest_count,
        selected_item_ids=selected_item_ids,
        station_activity_interest=station_activity_interest,
        capacity_need_overrides=capacity_need_overrides,
    )
    reserved = apply_reserve(raw, catalog)
    netted = net_against_inventory(reserved, host_inventory)
    purchase_plan, issues = build_equipment_purchase_plan(netted, catalog)

    return EquipmentDemandResult(demand=netted, purchase_plan=purchase_plan, review_issues=issues)
