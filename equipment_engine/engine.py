"""Haupteinstiegspunkt der Equipment Engine (Phase 1 + PartyContext-
Integration in Phase 2) - mirrort ``party_engine.engine.compute_party_demand``
/ ``music_engine.engine.plan_party_music`` (eine schlichte Top-Level-Funktion,
KEINE Engine-Klasse - abweichend vom Klassen-Beispiel der rohen Spec §168,
aber konsistent mit jedem anderen Planning-Entry-Point dieser Codebase)."""

from __future__ import annotations

from party_context.domain import DerivedPartyContext

from equipment_engine.context import compute_context_recommendations, compute_missing_capability_issues
from equipment_engine.demand import aggregate_equipment_demand, apply_reserve, net_against_inventory
from equipment_engine.domain import (
    EquipmentCatalog,
    EquipmentDemandResult,
    PartyEquipmentInventoryItem,
    PartyEquipmentProvision,
)
from equipment_engine.purchasing import build_equipment_purchase_plan


def calculate_equipment_demand(
    catalog: EquipmentCatalog,
    *,
    guest_count: int,
    selected_item_ids: list[str] | None = None,
    station_activity_interest: dict[str, int] | None = None,
    capacity_need_overrides: dict[str, float] | None = None,
    host_inventory: list[PartyEquipmentInventoryItem] | None = None,
    duration_hours: float = 0.0,
    venue_provisions: list[PartyEquipmentProvision] | None = None,
    derived_context: DerivedPartyContext | None = None,
) -> EquipmentDemandResult:
    """Bewusst NICHT die volle Signatur aus Spec §12 (``party, derived_context,
    guest_responses, food_plan, beverage_plan, music_plan``) - siehe
    ``equipment_engine/__init__.py`` für die geplanten Phase-3-Landeplätze.
    Drei Parameter bleiben explizite Platzhalter für noch nicht gebaute
    Features:

    ``station_activity_interest``: Platzhalter für echte Activities +
    Gäste-Voting (Phase 3, Spec §89/§90). Wert = Anzahl GLEICHZEITIGER
    Stationen für diese ``station_id`` DIREKT - noch kein von Popularität/
    Fläche abgeleiteter Stationsanzahl-Algorithmus (Spec §58, Phase 3).

    ``capacity_need_overrides``: Platzhalter für echte Beverage-/Food-Plan-
    Anbindung (Phase 3). ``item_id -> Rohbedarf`` in der Treiber-Einheit des
    Items (z.B. Liter gekühlter Getränke für "large_beverage_cooler"). Phase
    2 füllt hier bereits die Seating-/Tisch-Einträge über
    ``equipment_engine.context.compute_seating_and_table_capacity_needs``
    (vom Aufrufer VOR diesem Funktionsaufruf gemergt, siehe
    ``backend/app/routers/admin_equipment.py``).

    ``derived_context``: Phase-2-Ergänzung. Wenn übergeben, werden zusätzlich
    ``context_recommendations`` (Spec §83/§147/§154, advisory-only - siehe
    ``equipment_engine/context.py``) und Missing-Capability-``ReviewIssue``s
    (Spec §148) berechnet. ``None`` (z.B. in reinen Unit-Tests ohne
    PartyContext) degradiert graceful auf das Phase-1-Verhalten (Spec §155
    "Weather Fallback").
    """
    selected_item_ids = selected_item_ids or []
    station_activity_interest = station_activity_interest or {}
    capacity_need_overrides = capacity_need_overrides or {}
    host_inventory = host_inventory or []
    venue_provisions = venue_provisions or []

    raw = aggregate_equipment_demand(
        catalog,
        guest_count=guest_count,
        selected_item_ids=selected_item_ids,
        station_activity_interest=station_activity_interest,
        capacity_need_overrides=capacity_need_overrides,
        duration_hours=duration_hours,
    )
    reserved = apply_reserve(raw, catalog)
    netted = net_against_inventory(reserved, host_inventory, venue_provisions)
    purchase_plan, issues = build_equipment_purchase_plan(netted, catalog)

    result = EquipmentDemandResult(demand=netted, purchase_plan=purchase_plan, review_issues=issues)

    if derived_context is not None:
        result.context_recommendations = compute_context_recommendations(catalog, derived_context, selected_item_ids)
        result.review_issues = result.review_issues + compute_missing_capability_issues(
            netted, catalog, derived_context
        )

    return result
