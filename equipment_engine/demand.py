"""Equipment-Demand-Pipeline (Phase 1) - mirrort ``party_engine/bom.py``'s
zentrale Regel exakt: Bedarf wird über ALLE Quellen GLOBAL in einem
``dict[item_id, EquipmentDemand]`` aggregiert (jede Quelle addiert
``raw_quantity`` und hängt eine ``EquipmentDemandContribution`` an), BEVOR
irgendeine Rundung stattfindet. Reserve wird GENAU EINMAL nach der
globalen Aggregation angewendet (``apply_reserve``). Rundung/Verpackung
passiert erst ganz am Ende in ``equipment_engine/purchasing.py`` - hier
passiert NIE eine Rundung, auch die ``capacity_based``-Division nicht
(75/30=2.5 ist exakte Arithmetik, keine Rundung)."""

from __future__ import annotations

from collections import defaultdict

from equipment_engine.domain import (
    EquipmentCatalog,
    EquipmentDemand,
    EquipmentDemandContribution,
    EquipmentDemandRule,
    PartyEquipmentInventoryItem,
    PartyEquipmentProvision,
)

_EPSILON = 1e-9

_BASELINE_DRIVER_TYPES = ("fixed", "per_guest", "capacity_based")


def evaluate_rule_quantity(
    rule: EquipmentDemandRule,
    *,
    guest_count: int = 0,
    station_count: float = 0.0,
    capacity_need: float = 0.0,
    duration_hours: float = 0.0,
) -> float:
    """Wertet EINE Regel zu ihrem Roh-Beitrag aus (Spec §56/§57/§58).
    Keine Rundung - fünf Driver-Typen (Phase 1 + ``per_duration`` in Phase 2)."""
    if rule.driver_type == "fixed":
        qty = rule.base_quantity
    elif rule.driver_type == "per_guest":
        qty = rule.base_quantity + (rule.per_guest or 0.0) * guest_count
    elif rule.driver_type == "per_station":
        qty = rule.base_quantity + (rule.per_station or 0.0) * station_count
    elif rule.driver_type == "capacity_based":
        qty = (capacity_need / rule.capacity_per_unit) if rule.capacity_per_unit else 0.0
    elif rule.driver_type == "per_duration":
        qty = rule.base_quantity + (rule.per_duration or 0.0) * duration_hours
    else:
        raise ValueError(f"unsupported driver_type in Phase 1/2: {rule.driver_type!r}")

    if rule.minimum_quantity is not None:
        qty = max(qty, rule.minimum_quantity)
    if rule.maximum_quantity is not None:
        qty = min(qty, rule.maximum_quantity)
    return qty


def aggregate_equipment_demand(
    catalog: EquipmentCatalog,
    *,
    guest_count: int,
    selected_item_ids: list[str],
    station_activity_interest: dict[str, int],
    capacity_need_overrides: dict[str, float],
    duration_hours: float = 0.0,
) -> dict[str, EquipmentDemand]:
    """Drei Pässe, alle rein additiv in denselben Dict - mirrort
    ``party_engine.bom.explode_to_ingredient_demand``'s dict-keyed-by-id +
    contributions-Liste-Aggregation."""
    demand: dict[str, EquipmentDemand] = {}
    selected = set(selected_item_ids)

    def _add(item_id: str, amount: float, source: str) -> None:
        if amount <= _EPSILON:
            return
        item = catalog.items.get(item_id)
        if item is None or not item.active:
            return
        entry = demand.get(item_id)
        if entry is None:
            entry = EquipmentDemand(item_id=item_id, name=item.name, unit=item.unit)
            demand[item_id] = entry
        entry.raw_quantity += amount
        entry.contributions.append(EquipmentDemandContribution(source=source, amount=amount))

    # Pass 1: jedes Items eigene Baseline-Regel (fixed/per_guest/capacity_based).
    for item in catalog.items.values():
        if not item.active or not item.demand_rule_id:
            continue
        if not item.always_on and item.id not in selected:
            continue
        rule = catalog.demand_rules.get(item.demand_rule_id)
        if rule is None or rule.driver_type not in _BASELINE_DRIVER_TYPES:
            continue
        amount = evaluate_rule_quantity(
            rule, guest_count=guest_count, capacity_need=capacity_need_overrides.get(item.id, 0.0)
        )
        _add(item.id, amount, f"item_baseline:{rule.id}")

    # Pass 2: unabhängige per_station-Zuschlags-Regeln - können ein Item
    # treffen, das in Pass 1 bereits einen Eintrag hat (Multi-Source-Fall,
    # z.B. paper_cup: per-guest-Baseline + Beer-Pong-Zuschlag).
    for rule in catalog.demand_rules.values():
        if rule.driver_type != "per_station" or not rule.station_id or not rule.target_item_id:
            continue
        station_count = station_activity_interest.get(rule.station_id, 0)
        if station_count <= 0:
            continue
        amount = evaluate_rule_quantity(rule, guest_count=guest_count, station_count=station_count)
        _add(rule.target_item_id, amount, f"station:{rule.station_id}:{rule.id}")

    # Pass 3 (Phase 2): unabhängige per_duration-Zuschlags-Regeln - mirrort
    # Pass 2, aber ohne "Interesse"-Gate: sobald duration_hours bekannt ist,
    # gilt die Regel immer (kein Analogon zu station_activity_interest nötig).
    for rule in catalog.demand_rules.values():
        if rule.driver_type != "per_duration" or not rule.target_item_id:
            continue
        amount = evaluate_rule_quantity(rule, duration_hours=duration_hours)
        _add(rule.target_item_id, amount, f"duration:{rule.id}")

    return demand


def apply_reserve(demand: dict[str, EquipmentDemand], catalog: EquipmentCatalog) -> dict[str, EquipmentDemand]:
    """Mirrort ``party_engine.bom.apply_reserve`` exakt - GENAU EINMAL,
    nach globaler Aggregation, mutiert+liefert dieselben Objekte zurück."""
    for item_id, entry in demand.items():
        item = catalog.items.get(item_id)
        reserve_pct = item.reserve_pct if item else 0.0
        entry.reserve_pct = reserve_pct
        entry.quantity_after_reserve = entry.raw_quantity * (1 + reserve_pct)
    return demand


def net_against_inventory(
    demand: dict[str, EquipmentDemand],
    host_inventory: list[PartyEquipmentInventoryItem],
    venue_provisions: list[PartyEquipmentProvision] | None = None,
) -> dict[str, EquipmentDemand]:
    """Spec §8/§98: Required - (Host-Inventar + Venue-Provisions) = Procurement
    Need. Nicht verfügbare (``available=False``) Host-Inventar-Zeilen tragen
    nichts zur Deckung bei; Venue-Provisions gelten immer (kein
    ``available``-Flag - eine Location "hat" ihre Stühle einfach). Beide
    Quellen fließen additiv in denselben Akkumulator (keine getrennte
    Nachverfolgung auf ``EquipmentDemand`` - das gilt bereits für mehrere
    ``host_inventory``-Zeilen desselben Items)."""
    existing_by_item: dict[str, float] = defaultdict(float)
    for inv in host_inventory:
        if inv.available:
            existing_by_item[inv.equipment_item_id] += inv.quantity
    for provision in venue_provisions or []:
        existing_by_item[provision.equipment_item_id] += provision.quantity

    for item_id, entry in demand.items():
        entry.existing_quantity = existing_by_item.get(item_id, 0.0)
        entry.missing_quantity = max(0.0, entry.quantity_after_reserve - entry.existing_quantity)
    return demand
