"""PartyContext-Integration (Phase 2, Spec §83/§98/§147/§148/§154). Nimmt
bewusst nur schmale, bereits abgeleitete Werte entgegen (``DerivedPartyContext``
oder plain scalars), NICHT den rohen ``party_context.PartyContext`` -
``DerivedPartyContext`` ist bereits eine akzeptierte Cross-Package-Abhängigkeit
(siehe ``EquipmentRecommendationMetadata``'s Docstring-Verweis auf
``party_context.domain.ContextAffinity``), der rohe ``PartyContext`` bliebe
eine zusätzliche, unnötige Kopplung."""

from __future__ import annotations

from party_context.domain import DerivedPartyContext

from equipment_engine.domain import (
    EquipmentCatalog,
    EquipmentContextRecommendation,
    EquipmentDemand,
    ReviewIssue,
)

_OUTDOOR_ISH = ("outdoor", "mixed")
_DEFAULT_SEATING_RATIO = 0.6  # Spec §59 Beispiel: 40 guests * 0.60 = 24 seats
_GUESTS_PER_DINING_TABLE = 8.0  # Planungs-Default, NICHT spec-belegt (§60 nennt keine Zahl)
_GUESTS_PER_BUFFET_TABLE = 25.0  # Planungs-Default, NICHT spec-belegt (§60 nennt keine Zahl)


def compute_context_recommendations(
    catalog: EquipmentCatalog,
    derived_context: DerivedPartyContext,
    selected_item_ids: list[str],
) -> list[EquipmentContextRecommendation]:
    """Spec §83/§147/§154 "Recommendation ≠ Demand": ADVISORY ONLY - wird NIE
    zu echtem Procurement Demand, egal wie eindeutig der Trigger ist. Nur der
    Host kann ein Item über ``selected_item_ids`` real auswählen. Bereits
    ausgewählte Items werden nicht erneut empfohlen (es gibt nichts mehr zu
    entscheiden)."""
    selected = set(selected_item_ids)
    outdoor_ish = derived_context.indoor_outdoor in _OUTDOOR_ISH
    recommendations: list[EquipmentContextRecommendation] = []

    for item in catalog.items.values():
        if not item.active or item.id in selected:
            continue
        trigger = item.recommendation.weather_trigger
        if trigger is None:
            continue
        if trigger == "rain" and outdoor_ish and "outdoor_rain_risk" in derived_context.operational_constraints:
            reason = "Outdoor-Party mit erhöhter Regenwahrscheinlichkeit."
        elif trigger == "heat" and outdoor_ish and derived_context.temperature_class in ("warm", "hot"):
            reason = "Outdoor-Party bei warmem/heißem Wetter."
        elif trigger == "cold" and outdoor_ish and derived_context.temperature_class in ("cold", "cool"):
            reason = "Outdoor-Party bei kaltem/kühlem Wetter."
        else:
            continue
        recommendations.append(EquipmentContextRecommendation(item_id=item.id, name=item.name, reason=reason))

    return recommendations


def compute_missing_capability_issues(
    demand: dict[str, EquipmentDemand],
    catalog: EquipmentCatalog,
    derived_context: DerivedPartyContext,
) -> list[ReviewIssue]:
    """Spec §148 "TEST - NO POWER": fehlt eine für ein TATSÄCHLICH benötigtes
    Item (nicht nur ein empfohlenes) erforderliche Capability, wird ein
    Review Issue erzeugt - KEINE automatische Lösung/kein automatisches
    Entfernen des Items."""
    issues: list[ReviewIssue] = []
    for item_id, entry in demand.items():
        if entry.quantity_after_reserve <= 0:
            continue
        item = catalog.items.get(item_id)
        if item is None:
            continue
        required = item.recommendation.required_capabilities
        if not required:
            continue
        missing = required - derived_context.available_capabilities
        if not missing:
            continue
        issues.append(
            ReviewIssue(
                guest_name="",
                raw_text=item_id,
                issue_type="missing_capability",
                message=(
                    f'Equipment "{entry.name}" benötigt {", ".join(sorted(missing))}, '
                    "das laut Party-Context nicht verfügbar ist."
                ),
            )
        )
    return issues


def compute_seating_and_table_capacity_needs(
    guest_count: int,
    seating_ratio: float | None,
) -> dict[str, float]:
    """Spec §59/§60: liefert ROHE Bedarfswerte in der jeweiligen Regel-
    Treiber-Einheit (mirrort das bestehende ``large_beverage_cooler``-Muster:
    dort sind es Liter, die ``capacity_based``-Regel selbst teilt durch
    ``capacity_per_unit`` - HIER NICHT vordividieren, sonst wird doppelt
    geteilt). ``folding_chair``s Einheit ist bereits "Sitzplätze"
    (``capacity_per_unit=1.0``, §59-Beispiel: 40 * 0.60 = 24 Sitzplätze).
    ``dining_table``/``buffet_table``s Einheit ist "Gäste"
    (``capacity_per_unit=8.0``/``25.0`` macht die Umrechnung in Tischanzahl)."""
    ratio = seating_ratio if seating_ratio is not None else _DEFAULT_SEATING_RATIO
    return {
        "folding_chair": guest_count * ratio,
        "dining_table": float(guest_count),
        "buffet_table": float(guest_count),
    }
