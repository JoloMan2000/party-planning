"""
Demand Allocation
=================

Setzt die Pipeline-Schritte ``GuestResponse -> Normalization -> Preference ->
Demand Allocation -> Expected Servings`` um (AUFGABE §2, §30-32).

Zentrales Prinzip: Eine Gaststimme ist eine PRÄFERENZ, kein Kaufauftrag.
Mehrfachauswahl innerhalb derselben ``demand_group`` konkurriert um ein
gemeinsames "Choice-Budget" statt jeweils voll gerechnet zu werden (§30).

Alle konkreten Namen/IDs werden ausschließlich aus dem ``PartyCatalog``
gelesen - dieses Modul kennt keine konkreten Cocktails/Gerichte (§46).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from party_engine.domain import (
    CatalogItem,
    DemandAllocation,
    DietaryProfile,
    GuestResponse,
    Ingredient,
    PartyCatalog,
    PartyConfig,
    Preference,
    ResolutionResult,
    ReviewIssue,
)
from party_engine.resolver import ResolverIndex, get_resolver_index, resolve_freetext_field
from party_engine.substitution import get_substitution_candidates

WEIGHT_SELECTION = 1.0
# Designentscheidung: explizit getippter Freitext-Wunsch wird geringfügig
# stärker gewichtet als eine simple Multiselect-Auswahl (analog zu
# drink_model.py's WEIGHT_FREETEXT_* Konstanten, hier vereinheitlicht).
WEIGHT_FREETEXT = 1.1

# Demand-Groups, die sich ein gemeinsames Choice-Budget teilen ("beverage"-Pool,
# siehe AUFGABE §31: beverage_serving_budget gilt über ALLE Getränke-Gruppen).
_POOL_BY_DEMAND_GROUP: dict[str, str] = {
    "beverage_general": "beverage",
    "alcoholic_beverage": "beverage",
    "non_alcoholic_beverage": "beverage",
    "energy": "beverage",
    "main": "main",
    "side": "side",
    "snack": "snack",
    "dessert": "dessert",
    "condiment": "condiment",
}

_WATER_DIRECT_CONSUMABLE_ID = "water"


@dataclass
class GuestAllocation:
    """Erweiterung von ``DemandAllocation`` um Modifier-/Brand-Infos für die
    BOM-Explosion (bewusst außerhalb von domain.py, siehe party_engine/engine.py
    Modul-Docstring: domain.py bleibt unverändert)."""

    base: DemandAllocation
    brand: str = ""
    applied_modifiers: list[str] = field(default_factory=list)
    source: str = "selection"  # selection, freetext, baseline, overflow

    @property
    def guest_name(self) -> str:
        return self.base.guest_name

    @property
    def item_id(self) -> str:
        return self.base.item_id

    @property
    def item_type(self) -> str:
        return self.base.item_type

    @property
    def servings(self) -> float:
        return self.base.servings


@dataclass
class _RawPreference:
    item_id: str
    item_type: str
    weight: float
    brand: str
    applied_modifiers: list[str]
    source: str


# ---------------------------------------------------------------------------
# Schritt: Normalization / Preference
# ---------------------------------------------------------------------------


def resolve_guest_preferences(
    response: GuestResponse,
    catalog: PartyCatalog,
    index: ResolverIndex | None = None,
    config: PartyConfig | None = None,
) -> tuple[list[Preference], list[ReviewIssue]]:
    """Vereinheitlicht Multiselect-Auswahl + Freitext zu ``Preference``-Objekten
    und erzeugt dabei ``ReviewIssue``s für unklare/unbekannte Eingaben."""
    idx = index or get_resolver_index(catalog)
    config = config or PartyConfig()

    preferences: list[Preference] = []
    issues: list[ReviewIssue] = []

    def add_selection(item_id: str) -> None:
        item = catalog.get_item(item_id)
        if item is None:
            issues.append(
                ReviewIssue(
                    guest_name=response.guest_name,
                    raw_text=item_id,
                    issue_type="unknown",
                    message=f'Ausgewählte Katalog-ID "{item_id}" existiert nicht im Katalog.',
                )
            )
            return
        target_type = "recipe" if item_id in catalog.recipes else "direct_consumable"
        resolution = ResolutionResult(
            raw_text=item_id,
            target_type=target_type,
            target_id=item_id,
            confidence=1.0,
            method="selection",
        )
        preferences.append(Preference(response.guest_name, item_id, resolution, weight=WEIGHT_SELECTION))

    for item_id in response.drink_selections:
        add_selection(item_id)
    for item_id in response.food_selections:
        add_selection(item_id)

    def add_freetext_field(freetext: str) -> None:
        for result in resolve_freetext_field(freetext, catalog, idx):
            _handle_freetext_result(response.guest_name, result, catalog, config, preferences, issues)

    add_freetext_field(response.drinks_freetext)
    add_freetext_field(response.food_freetext)

    if response.dietary.allergies:
        issues.append(
            ReviewIssue(
                guest_name=response.guest_name,
                raw_text="",
                issue_type="allergy",
                message=(
                    f"{response.guest_name} hat Allergien/Unverträglichkeiten angegeben: "
                    f"{', '.join(response.dietary.allergies)}. Es wird KEINE automatische Aussage "
                    "getroffen, dass ein Gericht dafür sicher ist – bitte manuell prüfen."
                ),
            )
        )

    return preferences, issues


def _handle_freetext_result(
    guest_name: str,
    result: ResolutionResult,
    catalog: PartyCatalog,
    config: PartyConfig,
    preferences_out: list[Preference],
    issues_out: list[ReviewIssue],
) -> None:
    if result.target_type == "unknown":
        issues_out.append(
            ReviewIssue(
                guest_name=guest_name,
                raw_text=result.raw_text,
                issue_type="unknown",
                message=f'Freitext "{result.raw_text}" konnte keinem Katalogeintrag zugeordnet werden.',
            )
        )
        return

    target_type, target_id = result.target_type, result.target_id

    # Ingredient-Treffer ohne eigenständiges DirectConsumable-Pendant sind für
    # die Gästeoberfläche nicht direkt "bestellbar" -> Review statt Demand.
    if target_type == "ingredient":
        if target_id in catalog.direct_consumables:
            target_type = "direct_consumable"
        else:
            issues_out.append(
                ReviewIssue(
                    guest_name=guest_name,
                    raw_text=result.raw_text,
                    issue_type="ambiguous",
                    message=(
                        f'Freitext "{result.raw_text}" wurde als Zutat "{target_id}" erkannt, '
                        "es existiert dafür aber kein direkt wählbares Produkt."
                    ),
                )
            )
            return

    if result.confidence < config.confidence_review:
        issues_out.append(
            ReviewIssue(
                guest_name=guest_name,
                raw_text=result.raw_text,
                issue_type="low_confidence",
                message=(
                    f'Freitext "{result.raw_text}" wurde nur mit niedriger Confidence '
                    f"({result.confidence:.2f}) auf \"{target_id}\" abgebildet und wird NICHT "
                    "automatisch in die Bedarfsrechnung übernommen."
                ),
            )
        )
        return

    if result.confidence < config.confidence_auto:
        issues_out.append(
            ReviewIssue(
                guest_name=guest_name,
                raw_text=result.raw_text,
                issue_type="ambiguous",
                message=(
                    f'Freitext "{result.raw_text}" wurde als "{target_id}" interpretiert '
                    f"(Confidence {result.confidence:.2f}) – bitte prüfen."
                ),
            )
        )

    # Designentscheidung: ein per Fuzzy-Matching gefundener, freistehender
    # Spirituosen-Direktkonsum ohne erkannten Mixer wird zusätzlich als
    # "missing_mixer" markiert (z.B. Tippfehler bei einem eigentlich
    # gemeinten Longdrink).
    if result.method == "fuzzy" and target_type == "direct_consumable":
        dc = catalog.direct_consumables.get(target_id)
        ingredient = catalog.ingredients.get(dc.ingredient_id) if dc else None
        if ingredient is not None and ingredient.family == "spirit":
            issues_out.append(
                ReviewIssue(
                    guest_name=guest_name,
                    raw_text=result.raw_text,
                    issue_type="missing_mixer",
                    message=(
                        f'Freitext "{result.raw_text}" wurde als reine Spirituose "{target_id}" '
                        "interpretiert - ggf. war ein Mixgetränk gemeint. Bitte prüfen."
                    ),
                )
            )

    preferences_out.append(
        Preference(guest_name, result.raw_text, result, weight=WEIGHT_FREETEXT)
    )
    # Brand/Modifier-Infos werden über das ResolutionResult selbst transportiert
    # (Preference.resolution) und in _collect_raw_preferences ausgewertet.


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Volumen / Alkoholgehalt eines Items pro Portion
# ---------------------------------------------------------------------------


def _ingredient_for(item_id: str, item_type: str, catalog: PartyCatalog) -> Ingredient | None:
    if item_type == "direct_consumable":
        dc = catalog.direct_consumables.get(item_id)
        if dc:
            return catalog.ingredients.get(dc.ingredient_id)
    return None


def volume_l_per_serving(item_id: str, item_type: str, catalog: PartyCatalog) -> float:
    if item_type == "direct_consumable":
        dc = catalog.direct_consumables.get(item_id)
        return dc.serving_size_l if dc else 0.0
    if item_type == "recipe":
        recipe = catalog.recipes.get(item_id)
        if not recipe:
            return 0.0
        return sum(c.amount for c in recipe.components if c.unit == "l")
    return 0.0


def pure_alcohol_l_per_serving(item_id: str, item_type: str, catalog: PartyCatalog) -> float:
    if item_type == "direct_consumable":
        dc = catalog.direct_consumables.get(item_id)
        if not dc:
            return 0.0
        return dc.serving_size_l * (dc.abv / 100.0)
    if item_type == "recipe":
        recipe = catalog.recipes.get(item_id)
        if not recipe:
            return 0.0
        total = 0.0
        for comp in recipe.components:
            ingredient = catalog.ingredients.get(comp.ingredient_id)
            if ingredient and ingredient.abv and comp.unit == "l":
                total += comp.amount * (ingredient.abv / 100.0)
        return total
    return 0.0


def is_alcoholic_item(item_id: str, item_type: str, catalog: PartyCatalog) -> bool:
    item = catalog.get_item(item_id)
    if item is None:
        return False
    if item_type == "recipe":
        return bool(getattr(item, "contains_alcohol", False))
    if item_type == "direct_consumable":
        return bool(getattr(item, "abv", 0.0) > 0)
    return False


def is_energy_item(item_id: str, item_type: str, catalog: PartyCatalog) -> bool:
    item = catalog.get_item(item_id)
    return bool(item and getattr(item, "demand_group", "") == "energy")


def _demand_group_of(item_id: str, item_type: str, catalog: PartyCatalog) -> str:
    item = catalog.get_item(item_id)
    return item.demand_group if item else "unknown"


def _category_of(item_id: str, item_type: str, catalog: PartyCatalog) -> str:
    item = catalog.get_item(item_id)
    return item.category if item else ""


# ---------------------------------------------------------------------------
# Schritt: Demand Allocation / Expected Servings
# ---------------------------------------------------------------------------


def _collect_raw_preferences(
    preferences: list[Preference], catalog: PartyCatalog
) -> dict[str, _RawPreference]:
    """Dedupliziert Preferences pro (item_id) und behält die höchstgewichtete."""
    by_item: dict[str, _RawPreference] = {}
    for pref in preferences:
        res = pref.resolution
        item_id, item_type = res.target_id, res.target_type
        if item_type not in ("recipe", "direct_consumable"):
            continue
        if catalog.get_item(item_id) is None:
            continue
        existing = by_item.get(item_id)
        source = "selection" if res.method == "selection" else "freetext"
        if existing is None or pref.weight > existing.weight:
            by_item[item_id] = _RawPreference(
                item_id=item_id,
                item_type=item_type,
                weight=pref.weight,
                brand=res.brand,
                applied_modifiers=list(res.applied_modifiers),
                source=source,
            )
    return by_item


def allocate_guest_demand(
    guest_name: str,
    preferences: list[Preference],
    catalog: PartyCatalog,
    config: PartyConfig,
    dietary: DietaryProfile | None = None,
) -> list[GuestAllocation]:
    """Verteilt Choice-Budgets pro Demand-Group-Pool, wendet Alkohol-/Energy-
    Caps mit Overflow-Umverteilung an und liefert die finalen "Expected
    Servings" je Gast (inkl. Wasser-Baseline).

    ``dietary`` (falls übergeben) wird an jede Overflow-Substitution
    weitergereicht (siehe ``party_engine.substitution``), damit Dietary
    Constraints - safety-critical, §29/§33 - JEDE automatische Substitution
    schlagen, nicht nur solche für Food-Demand-Groups."""
    allocations: list[GuestAllocation] = []

    raw_by_item = _collect_raw_preferences(preferences, catalog)

    # Wasser-Baseline: IMMER, unabhängig von der Auswahl (§31).
    water_dc = catalog.direct_consumables.get(_WATER_DIRECT_CONSUMABLE_ID)
    water_l_total = config.water_l_per_guest

    # Wasser als explizite Auswahl nimmt NICHT am Choice-Budget teil (Baseline
    # deckt es bereits ab) - wird daher aus dem Pool entfernt.
    raw_by_item.pop(_WATER_DIRECT_CONSUMABLE_ID, None)

    pools: dict[str, dict[str, _RawPreference]] = {}
    for item_id, raw in raw_by_item.items():
        demand_group = _demand_group_of(item_id, raw.item_type, catalog)
        pool_key = _POOL_BY_DEMAND_GROUP.get(demand_group, "other")
        pools.setdefault(pool_key, {})[item_id] = raw

    allocated_servings: dict[str, float] = {}

    def distribute_count_budget(pool_items: dict[str, _RawPreference], total_budget: float) -> None:
        total_weight = sum(p.weight for p in pool_items.values())
        if total_weight <= 0:
            return
        for item_id, raw in pool_items.items():
            allocated_servings[item_id] = (raw.weight / total_weight) * total_budget

    def distribute_weight_budget_kg(pool_items: dict[str, _RawPreference], total_kg: float) -> None:
        total_weight = sum(p.weight for p in pool_items.values())
        if total_weight <= 0:
            return
        for item_id, raw in pool_items.items():
            kg_share = (raw.weight / total_weight) * total_kg
            serving_kg = volume_l_per_serving(item_id, raw.item_type, catalog) or 0.1
            allocated_servings[item_id] = kg_share / serving_kg

    def distribute_uncapped(pool_items: dict[str, _RawPreference]) -> None:
        for item_id, raw in pool_items.items():
            allocated_servings[item_id] = raw.weight

    if "beverage" in pools:
        distribute_count_budget(pools["beverage"], config.beverage_serving_budget)
    if "main" in pools:
        distribute_count_budget(pools["main"], config.main_budget_per_guest)
    if "side" in pools:
        distribute_count_budget(pools["side"], config.side_budget_per_guest)
    if "dessert" in pools:
        distribute_count_budget(pools["dessert"], config.dessert_budget_per_guest)
    if "snack" in pools:
        distribute_weight_budget_kg(pools["snack"], config.snack_g_per_guest / 1000.0)
    if "condiment" in pools:
        distribute_uncapped(pools["condiment"])
    if "other" in pools:
        distribute_uncapped(pools["other"])

    # --- Alkohol-/Energy-Caps mit Overflow-Umverteilung (§31, §33) ----------
    beverage_items = pools.get("beverage", {})
    water_l_total += _cap_and_redistribute(
        beverage_items,
        allocated_servings,
        member_fn=lambda iid: is_alcoholic_item(iid, beverage_items[iid].item_type, catalog),
        value_fn=lambda iid: pure_alcohol_l_per_serving(iid, beverage_items[iid].item_type, catalog),
        cap_value=config.max_alcohol_units_per_guest * config.alcohol_unit_pure_alcohol_l,
        candidate_fn=lambda iid: not is_alcoholic_item(iid, beverage_items[iid].item_type, catalog),
        catalog=catalog,
        dietary=dietary,
    )
    water_l_total += _cap_and_redistribute(
        beverage_items,
        allocated_servings,
        member_fn=lambda iid: is_energy_item(iid, beverage_items[iid].item_type, catalog),
        value_fn=lambda iid: volume_l_per_serving(iid, beverage_items[iid].item_type, catalog),
        cap_value=config.max_energy_units_per_guest * config.energy_unit_l,
        candidate_fn=lambda iid: not is_energy_item(iid, beverage_items[iid].item_type, catalog),
        catalog=catalog,
        dietary=dietary,
    )

    water_servings = (water_l_total / water_dc.serving_size_l) if (water_dc and water_dc.serving_size_l > 0) else 0.0
    if water_dc and water_servings > 0:
        allocations.append(
            GuestAllocation(
                base=DemandAllocation(guest_name, water_dc.id, "direct_consumable", water_servings),
                source="baseline",
            )
        )

    for pool_items in pools.values():
        for item_id, raw in pool_items.items():
            servings = allocated_servings.get(item_id, 0.0)
            if servings <= 0:
                continue
            allocations.append(
                GuestAllocation(
                    base=DemandAllocation(guest_name, item_id, raw.item_type, servings),
                    brand=raw.brand,
                    applied_modifiers=raw.applied_modifiers,
                    source=raw.source,
                )
            )

    return allocations


def _cap_and_redistribute(
    pool_items: dict[str, _RawPreference],
    allocated_servings: dict[str, float],
    member_fn,
    value_fn,
    cap_value: float,
    candidate_fn,
    catalog: PartyCatalog,
    dietary: DietaryProfile | None = None,
) -> float:
    """Kappt die Summe von ``value_fn(servings)`` über alle ``member_fn``-Items
    auf ``cap_value`` und verteilt den Überschuss proportional (gewichtet nach
    Substitutionskompatibilität) auf ``candidate_fn``-Items um. Nicht
    umverteilbarer Rest fließt in den Wasserbedarf (in Litern).

    Rückgabe: zusätzlich benötigte Wasser-SERVINGS-Menge in Litern (nicht
    Servings!) für den Aufrufer, der das direkt zu ``water_servings`` addiert
    - Designentscheidung: hier bewusst in Litern, weil der Wasserbedarf des
    Gastes ohnehin literbasiert (``water_l_per_guest``) geführt wird und der
    Rückgabewert direkt zu ``water_servings`` (Liter / serving_size) passen
    muss; siehe Aufrufstelle, die das Ergebnis vor der Umrechnung in Servings
    bereits in Liter-Einheiten interpretiert.
    """
    members = [iid for iid in pool_items if member_fn(iid)]
    if not members:
        return 0.0

    total_value = sum(allocated_servings.get(iid, 0.0) * value_fn(iid) for iid in members)
    if total_value <= cap_value or total_value <= 0:
        return 0.0

    scale = cap_value / total_value
    overflow_servings: dict[str, float] = {}
    for iid in members:
        original = allocated_servings.get(iid, 0.0)
        reduced = original * scale
        overflow_servings[iid] = original - reduced
        allocated_servings[iid] = reduced

    candidates = [iid for iid in pool_items if candidate_fn(iid) and iid not in overflow_servings]
    extra_water_l = 0.0

    for source_id, overflow in overflow_servings.items():
        if overflow <= 0:
            continue
        source_type = pool_items[source_id].item_type
        subs = get_substitution_candidates(source_id, catalog, dietary=dietary)
        sub_ids_available = {sid: compat for sid, compat in subs if sid in candidates}

        weighted: dict[str, float] = {}
        for cid in candidates:
            base_weight = max(allocated_servings.get(cid, 0.0), 1e-6)
            compat = sub_ids_available.get(cid, 0.15)  # schwache Default-Affinität
            weighted[cid] = base_weight * compat

        total_weight = sum(weighted.values())
        if total_weight <= 0:
            extra_water_l += overflow * volume_l_per_serving(source_id, source_type, catalog)
            continue

        for cid, w in weighted.items():
            share = overflow * (w / total_weight)
            allocated_servings[cid] = allocated_servings.get(cid, 0.0) + share

    return extra_water_l
