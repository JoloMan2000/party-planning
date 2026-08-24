"""
Unified Party Demand Engine - Haupteinstiegspunkt
====================================================

Öffentliche API für Aufrufer (z.B. später die Streamlit-UI / einen Legacy-
Adapter):

    from party_engine.catalog import load_catalog
    from party_engine.engine import compute_party_demand
    from party_engine.domain import PartyConfig

    catalog = load_catalog()
    result = compute_party_demand(catalog, guest_responses, PartyConfig())

Implementiert die vollständige Pipeline aus AUFGABE §2:

    GuestResponse -> Normalization -> Preference -> Demand Allocation ->
    Expected Servings -> DirectConsumable/Recipe -> Recipe BOM Explosion ->
    IngredientDemand -> Global Aggregation -> Production Rules ->
    Substitution -> Reserve -> Purchase SKU Optimization -> Purchase Plan

Zentrale Architekturregel (§46): Dieses Modul kennt KEINE konkreten
Cocktails/Gerichte/Zutaten. Neue Katalogeinträge erfordern keine Änderung an
diesem Code.
"""

from __future__ import annotations

from collections import defaultdict

from party_engine.allocation import GuestAllocation, allocate_guest_demand, resolve_guest_preferences
from party_engine.bom import apply_production_rules, apply_reserve, compute_ice_demand_kg, explode_to_ingredient_demand
from party_engine.domain import (
    GuestResponse,
    ItemDemandSummary,
    PartyCatalog,
    PartyConfig,
    PartyDemandResult,
    ReviewIssue,
)
from party_engine.purchasing import build_purchase_plan
from party_engine.resolver import get_resolver_index
from party_context.domain import DerivedPartyContext


def _summarize_item_demand(allocations: list[GuestAllocation], catalog: PartyCatalog) -> list[ItemDemandSummary]:
    supporters: dict[str, set[str]] = defaultdict(set)
    servings_sum: dict[str, float] = defaultdict(float)
    item_types: dict[str, str] = {}

    for alloc in allocations:
        if alloc.source == "baseline":
            continue  # Wasser-Grundversorgung erscheint nicht als "Präferenz"
        supporters[alloc.item_id].add(alloc.guest_name)
        servings_sum[alloc.item_id] += alloc.servings
        item_types[alloc.item_id] = alloc.item_type

    summaries = []
    for item_id, supporter_set in supporters.items():
        item = catalog.get_item(item_id)
        name = item.name if item else item_id
        summaries.append(
            ItemDemandSummary(
                item_id=item_id,
                item_name=name,
                item_type=item_types[item_id],
                supporters=len(supporter_set),
                expected_servings=servings_sum[item_id],
            )
        )
    summaries.sort(key=lambda s: s.expected_servings, reverse=True)
    return summaries


def compute_party_demand(
    catalog: PartyCatalog,
    responses: list[GuestResponse],
    config: PartyConfig | None = None,
    derived_context: DerivedPartyContext | None = None,
) -> PartyDemandResult:
    """Führt die vollständige Demand-Pipeline für alle Gästeantworten aus.

    ``derived_context`` (§77 Party-Context-Engine-Spec, optional): zentral
    von ``PartyContextEngine.derive_context()`` abgeleiteter Kontext. Wird
    unverändert an ``allocate_guest_demand`` (Wasser-/Getränke-Modifier) und
    ``compute_ice_demand_kg`` (Eis-Modifier) durchgereicht - siehe dortige
    Docstrings. Bleibt ``None`` (Standard), ist das Verhalten unverändert."""
    config = config or PartyConfig()
    index = get_resolver_index(catalog)

    all_review_issues: list[ReviewIssue] = []
    all_allocations: list[GuestAllocation] = []

    for response in responses:
        preferences, issues = resolve_guest_preferences(response, catalog, index, config)
        all_review_issues.extend(issues)
        allocations = allocate_guest_demand(
            response.guest_name,
            preferences,
            catalog,
            config,
            dietary=response.dietary,
            derived_context=derived_context,
        )
        all_allocations.extend(allocations)

    item_demand = _summarize_item_demand(all_allocations, catalog)

    raw_ingredient_demand = explode_to_ingredient_demand(all_allocations, catalog)
    expanded_ingredient_demand = apply_production_rules(raw_ingredient_demand, catalog)
    final_ingredient_demand = apply_reserve(expanded_ingredient_demand, catalog, config)

    purchase_plan, purchase_issues = build_purchase_plan(final_ingredient_demand, catalog)
    all_review_issues.extend(purchase_issues)

    ice_multiplier = derived_context.beverage_modifiers.ice_multiplier if derived_context is not None else 1.0
    ice_demand_kg = compute_ice_demand_kg(all_allocations, catalog, ice_multiplier=ice_multiplier)

    return PartyDemandResult(
        item_demand=item_demand,
        ingredient_demand=final_ingredient_demand,
        purchase_plan=purchase_plan,
        review_issues=all_review_issues,
        ice_demand_kg=ice_demand_kg,
    )
