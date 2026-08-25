"""
Domain-Modell der Unified Party Demand Engine.
================================================

Zentrale Regel (siehe AUFGABE, Abschlussregel):
    Eine Stimme ist eine Präferenz und kein Kaufauftrag.
    Ein Cocktail/Gericht ist ein Rezept und kein Einkaufsprodukt.
    Eingekauft werden ausschließlich Ingredients.

Dieses Modul enthält NUR Datenstrukturen (dataclasses). Es enthält keine
Katalogdaten (siehe catalog/*.json) und keine konkreten Gerichte/Cocktails.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from party_engine.recommendation_domain import RecommendationMetadata


# --- Konfiguration -----------------------------------------------------------


@dataclass
class PartyConfig:
    """Zentral konfigurierbare Mengen-Parameter (siehe AUFGABE §31/32/37)."""

    party_duration_hours: float = 7.0

    # Getränke
    water_l_per_guest: float = 1.5
    beverage_serving_budget: float = 3.5
    max_alcohol_units_per_guest: float = 2.0
    max_energy_units_per_guest: float = 1.0
    alcohol_unit_pure_alcohol_l: float = 0.02  # 1 "Einheit" Reinalkohol
    energy_unit_l: float = 0.25  # 1 "Einheit" Energy-Getränk

    # Essen
    main_budget_per_guest: float = 1.10
    side_budget_per_guest: float = 1.40
    snack_g_per_guest: float = 70.0
    dessert_budget_per_guest: float = 0.50

    # Reserve pro Ingredient-Familie bzw. Demand-Group (0.10 = 10 %)
    reserve_percentages: dict[str, float] = field(
        default_factory=lambda: {
            "water": 0.15,
            "softdrink": 0.10,
            "juice": 0.10,
            "beer": 0.05,
            "wine": 0.05,
            "sparkling_wine": 0.05,
            "spirit": 0.05,
            "liqueur": 0.05,
            "energy": 0.05,
            "coffee": 0.10,
            "main_meat": 0.08,
            "main_vegetarian": 0.10,
            "side": 0.10,
            "salad": 0.10,
            "bread": 0.12,
            "snack": 0.10,
            "sauce": 0.15,
            "fresh": 0.10,
            "dessert": 0.08,
            "default": 0.10,
        }
    )

    # Confidence-Schwellen für den Freitext-Resolver
    confidence_auto: float = 0.90
    confidence_review: float = 0.75


@dataclass
class CatalogCurationSettings:
    """Admin-Limitierung der für Gäste sichtbaren Katalog-Items ("engere
    Auswahl"): ist ``enabled`` True UND ``curated_item_ids`` nicht leer,
    sehen Gäste in der Getränke-/Speisen-Auswahl NUR noch Items aus dieser
    Menge (siehe ``party_engine.catalog_curation.filter_items_by_curation``).
    Bewusst getrennt von ``PartyConfig`` (dort: Mengen-Parameter, hier:
    Sortiments-Auswahl). Default (``enabled=False``) verhält sich exakt wie
    vor Einführung dieser Funktion - voller Katalog für alle Gäste sichtbar."""

    enabled: bool = False
    curated_item_ids: set[str] = field(default_factory=set)


# --- Gäste & Antworten ---------------------------------------------------------


@dataclass
class DietaryProfile:
    """Ernährungs-Constraints. Schlagen jede Substitution (siehe §29)."""

    vegetarian: bool = False
    vegan: bool = False
    pescatarian: bool = False
    no_pork: bool = False
    no_beef: bool = False
    halal_required: bool = False
    gluten_free: bool = False
    lactose_free: bool = False
    allergies: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.vegetarian
            or self.vegan
            or self.pescatarian
            or self.no_pork
            or self.no_beef
            or self.halal_required
            or self.gluten_free
            or self.lactose_free
            or self.allergies
        )


@dataclass
class Guest:
    name: str


@dataclass
class GuestResponse:
    guest_name: str
    start_time: str
    drink_selections: list[str] = field(default_factory=list)  # Katalog-IDs
    drinks_freetext: str = ""
    food_selections: list[str] = field(default_factory=list)  # Katalog-IDs
    food_freetext: str = ""
    songs: list[dict] = field(default_factory=list)
    dietary: DietaryProfile = field(default_factory=DietaryProfile)


# --- Katalog-Basistypen --------------------------------------------------------


@dataclass
class CatalogItem:
    id: str
    name: str
    category: str  # UI-Kategorie, z.B. "beer", "burger", "cocktail_vodka"
    demand_group: str  # z.B. "alcoholic_beverage", "main", "side", ...
    tags: list[str] = field(default_factory=list)
    popular: bool = False
    aliases_hint: list[str] = field(default_factory=list)  # nur informativ

    # Empfehlungs-Metadaten (Tag-/Occasion-Mapping). Rein additiv, wird von der
    # Demand-Pipeline (engine.py/allocation.py/bom.py) nicht gelesen — siehe
    # recommendation_domain.py für die Architekturregel "Empfehlung != Demand".
    recommendation: RecommendationMetadata = field(default_factory=RecommendationMetadata)


@dataclass
class Ingredient(CatalogItem):
    unit: str = "l"  # l, kg, g, pcs
    family: str = "misc"  # spirit, liqueur, wine, beer, softdrink, meat, ...
    purchasable: bool = True  # False => wird über ProductionRule erzeugt
    is_meat: bool = False
    is_fish: bool = False
    is_vegetarian: bool = True
    is_vegan: bool = False
    contains_alcohol: bool = False
    abv: float = 0.0  # Vol.-% falls Alkohol
    contains_caffeine: bool = False
    allergens: list[str] = field(default_factory=list)
    gluten_free: bool = True
    lactose_free: bool = True

    # §29 (Party-Context-Engine-Spec): beeinflusst ``operational_fit``
    # (Lagerungs-/Verderbsrisiko, z.B. Sahne-/Mayonnaise-/Rohfisch-lastige
    # Zutaten bei Outdoor+Hitze+kein Kühlschrank). Neutrale Defaults, sofern
    # nicht explizit im Katalog kuratiert (analog zu den 0.5-Neutral-Defaults
    # von RecommendationMetadata).
    perishability_score: float = 0.5
    requires_cooling: bool = False
    temperature_sensitive: bool = False


@dataclass
class DirectConsumable(CatalogItem):
    """Ein direkt trinkbares/konsumierbares Getränk (kein Rezept)."""

    ingredient_id: str = ""
    serving_size_l: float = 0.3
    abv: float = 0.0
    contains_caffeine: bool = False


@dataclass
class RecipeComponent:
    ingredient_id: str
    amount: float
    unit: str = "l"
    optional: bool = False
    note: str = ""


@dataclass
class Recipe(CatalogItem):
    """Cocktail ODER Gericht — beides ist ein virtuelles Produkt mit BOM."""

    components: list[RecipeComponent] = field(default_factory=list)
    ice_profile: str = ""  # shaken, stirred, highball, crushed, blended, no_ice
    garnish: list[str] = field(default_factory=list)
    satiety_factor: float = 1.0  # nur für Food relevant
    serving_unit: str = "portion"
    is_vegetarian: bool = True
    is_vegan: bool = False
    contains_alcohol: bool = False

    # §29 (Party-Context-Engine-Spec), siehe ``Ingredient`` oben. Für Rezepte
    # bewusst eigenständig kuratierbar statt automatisch aus den Komponenten
    # abgeleitet (ein Rezept kann z.B. Sahne enthalten, aber komplett
    # durchgegart/nicht kühlkritisch sein - eine reine Max-Aggregation über
    # Komponenten würde das nicht korrekt abbilden).
    perishability_score: float = 0.5
    requires_cooling: bool = False
    temperature_sensitive: bool = False


@dataclass
class Modifier:
    id: str
    name: str
    applies_to: list[str] = field(default_factory=lambda: ["*"])
    effect_type: str = "add_component"  # add_component, remove_component, set_brand_preference, scale
    target_ingredient_id: str = ""
    amount: float = 0.0
    unit: str = "l"
    brand: str = ""


@dataclass
class Alias:
    alias_text: str  # bereits normalisiert
    target_type: str  # ingredient, direct_consumable, recipe, modifier
    target_id: str
    confidence: float = 1.0
    brand: str = ""


@dataclass
class SubstitutionRule:
    from_id: str
    to_id: str
    compatibility: float  # 0..1
    direction: str = "bidirectional"  # bidirectional, one_way
    note: str = ""


@dataclass
class ProductionRule:
    output_ingredient_id: str
    inputs: list[dict] = field(default_factory=list)  # [{"ingredient_id": .., "ratio": ..}]
    note: str = ""


@dataclass
class PurchaseSKU:
    ingredient_id: str
    size: float
    unit: str
    pack_label: str = ""
    pack_count: int = 1  # z.B. 6er-Pack Burger Buns -> size=1 pcs, pack_count=6


# --- Ergebnisse des Resolvers --------------------------------------------------


@dataclass
class ResolutionResult:
    raw_text: str
    target_type: str  # ingredient, direct_consumable, recipe, modifier, unknown
    target_id: str = ""
    confidence: float = 0.0
    method: str = "unknown"  # exact_canonical, exact_alias, normalized, brand, recipe_modifier, fuzzy, unknown
    brand: str = ""
    applied_modifiers: list[str] = field(default_factory=list)


@dataclass
class Preference:
    guest_name: str
    raw_text: str
    resolution: ResolutionResult
    weight: float = 1.0


@dataclass
class ReviewIssue:
    guest_name: str
    raw_text: str
    issue_type: str  # unknown, low_confidence, allergy, missing_mixer, ambiguous
    message: str


# --- Demand-Pipeline -----------------------------------------------------------


@dataclass
class DemandAllocation:
    guest_name: str
    item_id: str
    item_type: str  # direct_consumable, recipe
    servings: float


@dataclass
class IngredientDemandContribution:
    source_item_id: str
    source_item_name: str
    amount: float
    unit: str


@dataclass
class IngredientDemand:
    ingredient_id: str
    name: str
    unit: str
    raw_quantity: float
    contributions: list[IngredientDemandContribution] = field(default_factory=list)
    reserve_pct: float = 0.0
    quantity_after_reserve: float = 0.0


@dataclass
class SKUBreakdownEntry:
    size: float
    unit: str
    count: int
    pack_label: str = ""


@dataclass
class PurchasePlanItem:
    ingredient_id: str
    name: str
    quantity_needed: float
    unit: str
    sku_breakdown: list[SKUBreakdownEntry] = field(default_factory=list)
    total_purchased_quantity: float = 0.0


@dataclass
class ItemDemandSummary:
    item_id: str
    item_name: str
    item_type: str
    supporters: int
    expected_servings: float


@dataclass
class PartyDemandResult:
    item_demand: list[ItemDemandSummary] = field(default_factory=list)
    ingredient_demand: dict[str, IngredientDemand] = field(default_factory=dict)
    purchase_plan: list[PurchasePlanItem] = field(default_factory=list)
    review_issues: list[ReviewIssue] = field(default_factory=list)
    ice_demand_kg: float = 0.0


# --- Katalog-Container -----------------------------------------------------------


@dataclass
class PartyCatalog:
    ingredients: dict[str, Ingredient] = field(default_factory=dict)
    direct_consumables: dict[str, DirectConsumable] = field(default_factory=dict)
    recipes: dict[str, Recipe] = field(default_factory=dict)
    modifiers: dict[str, Modifier] = field(default_factory=dict)
    aliases: list[Alias] = field(default_factory=list)
    substitution_rules: list[SubstitutionRule] = field(default_factory=list)
    production_rules: list[ProductionRule] = field(default_factory=list)
    purchase_skus: dict[str, list[PurchaseSKU]] = field(default_factory=dict)

    def all_selectable_items(self) -> list[CatalogItem]:
        """Alle Items, die ein Gast direkt auswählen kann (UI-Quelle)."""
        items: list[CatalogItem] = []
        items.extend(self.direct_consumables.values())
        items.extend(self.recipes.values())
        return items

    def get_item(self, item_id: str) -> CatalogItem | None:
        if item_id in self.direct_consumables:
            return self.direct_consumables[item_id]
        if item_id in self.recipes:
            return self.recipes[item_id]
        if item_id in self.ingredients:
            return self.ingredients[item_id]
        return None
