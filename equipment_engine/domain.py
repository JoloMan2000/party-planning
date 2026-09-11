"""Datenstrukturen der Equipment Engine (Phase 1) - KEINE Logik, mirrort
``party_engine/domain.py``. ``PurchaseSKU``/``SKUBreakdownEntry``/
``ReviewIssue`` werden direkt aus ``party_engine.domain`` wiederverwendet
(generische Einkaufs-/Review-Konzepte, nicht Food-spezifisch) statt
parallel dupliziert zu werden (Plan §2, Spec §174: "Bestehende ...
Architektur weiterverwenden")."""

from __future__ import annotations

from dataclasses import dataclass, field

from party_engine.domain import PurchaseSKU, ReviewIssue, SKUBreakdownEntry

__all__ = [
    "PurchaseSKU",
    "ReviewIssue",
    "SKUBreakdownEntry",
    "EquipmentCategory",
    "EquipmentRecommendationMetadata",
    "EquipmentDemandRule",
    "EquipmentItem",
    "EquipmentDemandContribution",
    "EquipmentDemand",
    "EquipmentPurchasePlanItem",
    "EquipmentDemandResult",
    "PartyEquipmentInventoryItem",
    "EquipmentCatalog",
]


@dataclass
class EquipmentCategory:
    """Zweistufige Kategorie-Taxonomie (Spec §5/§15) - Food/Beverage hat
    dafür nur ein freies ``category``-String-Feld, Equipment braucht eine
    echte Hierarchie fürs kategoriebasierte Browsing-UI (Phase 6+)."""

    id: str
    name: str
    parent_id: str | None = None
    description: str = ""


@dataclass
class EquipmentRecommendationMetadata:
    """Vereinfacht gegenüber der rohen Spec (§82, dort ein Dutzend
    separater ``*_tags``-Sets): ein generisches ``tags``-Set (mirrort
    ``CatalogItem.tags`` in ``party_engine/domain.py``) plus
    ``required_capabilities``/``preferred_capabilities`` (mirrort
    ``party_context.domain.ContextAffinity``, dieselbe Capability-Vokabular
    wie ``party_context.capabilities.derive_capabilities()`` liefert - z.B.
    "grill", "power", "running_water"). Food/Beverages ~20 kontinuierliche
    Scores (``indoor_score`` etc.) lösen ein anderes Problem (Ranking vieler
    ähnlicher Optionen gegen Gäste-Geschmack) und passen hier nicht - Phase 1
    hat ohnehin noch keinen Recommendation-/Scoring-Pass (siehe Non-Goals)."""

    tags: set[str] = field(default_factory=set)
    required_capabilities: set[str] = field(default_factory=set)
    preferred_capabilities: set[str] = field(default_factory=set)


@dataclass
class EquipmentDemandRule:
    """Datengetriebene Demand-Regel (Spec §55). Phase 1 unterstützt vier
    Driver-Typen (Spec §56): ``fixed``, ``per_guest``, ``capacity_based``,
    ``per_station`` - die vier, die ohne echte PartyContext-/Food-/
    Beverage-Integration testbar sind (die übrigen Driver-Typen ``per_table``/
    ``per_area``/``per_room``/``per_duration``/``per_food_service``/
    ``per_drink_service``/``per_activity``/``conditional`` kommen mit
    Phase 2/3).

    ``station_id``/``target_item_id`` sind Phase-1-Ergänzungen gegenüber der
    rohen Spec: sie erlauben einer ``per_station``-Regel, ein Item
    "aufzustocken", das UNABHÄNGIG davon bereits eine eigene Baseline-Regel
    hat (z.B. Becher: per-guest-Baseline + Beer-Pong-Station-Zuschlag) -
    genau das macht den echten Multi-Source-Aggregations-Testfall möglich
    (mirrort ``test_vodka_from_two_different_cocktails_aggregates_into_one_entry``)."""

    id: str
    driver_type: str  # "fixed" | "per_guest" | "capacity_based" | "per_station"
    base_quantity: float = 0.0
    per_guest: float | None = None
    per_station: float | None = None
    capacity_per_unit: float | None = None
    minimum_quantity: float | None = None
    maximum_quantity: float | None = None
    station_id: str | None = None
    target_item_id: str | None = None


@dataclass
class EquipmentItem:
    """Ein Equipment-/Verbrauchsmaterial-Katalogeintrag (Spec §4).

    ``reserve_pct`` liegt bewusst PRO ITEM statt in einem kategorie-
    geschlüsselten ``PartyConfig.reserve_percentages``-artigen Dict (wie bei
    Food/Beverage) - die eigenen Beispiele der Spec (§69: Servietten 15%,
    Müllbeutel 20%, Beer-Pong-Bälle 25%) sind bereits effektiv pro Item, eine
    Familien-Indirektion würde hier keinen Mehrwert bringen.

    ``always_on`` unterscheidet Items, die grundsätzlich für jede Party
    relevant sind (Geschirr, Bar-Werkzeug, Reinigung - jeder Aufruf wertet
    sie aus), von optionalen (Gesellschaftsspiele - nur bei expliziter
    Auswahl über ``selected_item_ids``)."""

    id: str
    name: str
    category_id: str
    subcategory_id: str | None = None
    equipment_type: str = "consumable"  # "durable" | "consumable" | "rental" ("service" ungenutzt in Phase 1)
    unit: str = "pcs"
    tags: set[str] = field(default_factory=set)
    recommendation: EquipmentRecommendationMetadata = field(default_factory=EquipmentRecommendationMetadata)
    demand_rule_id: str | None = None
    reserve_pct: float = 0.05
    always_on: bool = True
    active: bool = True


@dataclass
class EquipmentDemandContribution:
    """Mirrort ``party_engine.domain.IngredientDemandContribution`` - eine
    einzelne Quelle, die zum Gesamtbedarf eines Items beiträgt."""

    source: str  # z.B. "item_baseline:rule_paper_cup_per_guest", "station:beer_pong:rule_x"
    amount: float
    note: str = ""


@dataclass
class EquipmentDemand:
    """Mirrort ``party_engine.domain.IngredientDemand``, erweitert um
    Inventar-Netting (``existing_quantity``/``missing_quantity``, Spec §8)
    und die finale gerundete/verpackte Menge (``final_required_quantity``).
    KEIN ``recommendation_strength``/``source_reasons`` wie in der rohen
    Spec - es gibt in Phase 1 noch keinen Recommendation-/Scoring-Pass
    (siehe Non-Goals)."""

    item_id: str
    name: str
    unit: str
    raw_quantity: float = 0.0
    contributions: list[EquipmentDemandContribution] = field(default_factory=list)
    reserve_pct: float = 0.0
    quantity_after_reserve: float = 0.0
    existing_quantity: float = 0.0
    missing_quantity: float = 0.0
    final_required_quantity: float = 0.0


@dataclass
class EquipmentPurchasePlanItem:
    """Mirrort ``party_engine.domain.PurchasePlanItem``. ``sku_breakdown``
    bleibt leer für durable/rental Items (die werden stückweise gerundet,
    nicht paketweise eingekauft, siehe ``equipment_engine/purchasing.py``)."""

    item_id: str
    name: str
    quantity_needed: float
    unit: str
    sku_breakdown: list[SKUBreakdownEntry] = field(default_factory=list)
    total_purchased_quantity: float = 0.0


@dataclass
class EquipmentDemandResult:
    """Ergebnis von ``calculate_equipment_demand()`` - mirrort
    ``party_engine.domain.PartyDemandResult``."""

    demand: dict[str, EquipmentDemand] = field(default_factory=dict)
    purchase_plan: list[EquipmentPurchasePlanItem] = field(default_factory=list)
    review_issues: list[ReviewIssue] = field(default_factory=list)


@dataclass
class PartyEquipmentInventoryItem:
    """Was ein Host bereits besitzt (Spec §7). ``UNIQUE(owner_user_id,
    equipment_item_id)`` auf Storage-Ebene - "2 Beer-Pong-Tische besitzen"
    ist EINE Zeile mit ``quantity=2``, nicht zwei Zeilen (siehe
    ``equipment_engine/storage.py``)."""

    id: str
    owner_user_id: str
    equipment_item_id: str
    quantity: float = 1.0
    condition: str = ""
    available: bool = True
    notes: str = ""


@dataclass
class EquipmentCatalog:
    """In-Memory-Katalog-Container - mirrort ``party_engine.domain.PartyCatalog``
    (dict-/list-Attribute, direkter Zugriff durch Aufrufer, siehe
    ``equipment_engine/catalog.py``)."""

    categories: dict[str, EquipmentCategory] = field(default_factory=dict)
    items: dict[str, EquipmentItem] = field(default_factory=dict)
    demand_rules: dict[str, EquipmentDemandRule] = field(default_factory=dict)
    purchase_skus: dict[str, list[PurchaseSKU]] = field(default_factory=dict)

    def get_item(self, item_id: str) -> EquipmentItem | None:
        return self.items.get(item_id)

    def search(
        self,
        *,
        category_id: str | None = None,
        equipment_type: str | None = None,
        tags: set[str] | None = None,
        active_only: bool = True,
    ) -> list[EquipmentItem]:
        """Durchsucht den Katalog (Spec §170/§104 - "Search equipment").
        ``category_id`` matcht sowohl Top-Level- als auch Subkategorie."""
        results: list[EquipmentItem] = []
        for item in self.items.values():
            if active_only and not item.active:
                continue
            if category_id is not None and category_id not in (item.category_id, item.subcategory_id):
                continue
            if equipment_type is not None and item.equipment_type != equipment_type:
                continue
            if tags and not tags.issubset(item.tags):
                continue
            results.append(item)
        return results
