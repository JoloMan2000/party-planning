"""
Occasion Recommendation Engine — Scoring & Strategien
========================================================

Implementiert die eigentliche Scoring-/Strategie-Logik der "Occasion
Recommendation Engine" (siehe Claude-Code-Memory,
``recommendation_engine_full_spec.txt``, insbesondere §1, §7, §51/52,
§58-69, §78/79, §82-84). Baut ausschließlich auf bereits abgeschlossenen
Modulen auf:

    party_engine/recommendation_domain.py   -> Datenstrukturen
    party_engine/tags.py                    -> Tag-Registry
    party_engine/occasions.py               -> OccasionProfile-Loader
    party_engine/recommendation_tagging.py  -> Tag-/Metadaten-Ableitung
    party_engine/catalog.py + domain.py     -> PartyCatalog/CatalogItem

KRITISCHE INVARIANTEN (§78/§79 — dürfen an KEINER Stelle verletzt werden):
    * Eine Empfehlung erzeugt NIEMALS ``Preference``/``DemandAllocation``/
      ``IngredientDemand``. Dieses Modul importiert daher bewusst NICHTS aus
      ``party_engine.engine``, ``party_engine.allocation``,
      ``party_engine.bom``, ``party_engine.substitution`` oder
      ``party_engine.purchasing``.
    * "Admin pinned"/"Signature" bedeutet ausschließlich "prominent
      anbieten", niemals "automatisch kaufen" (kein
      ``admin_committed_supply``-Seiteneffekt irgendwo in diesem Modul).
    * Ein Gast mit hartem ``DietaryProfile``-Constraint (vegan/vegetarisch/
      no_pork/no_beef/pescatarian) darf ein strukturell inkompatibles Item
      NIEMALS empfohlen bekommen — nicht nur niedriger bewertet, sondern
      vollständig ausgeschlossen (siehe ``_dietary_violation_reason`` sowie
      die doppelte Durchsetzung in ``score_item_for_occasion`` UND
      ``recommend_for_guest``).

Streamlit-frei, reines Python — funktioniert mit ``python3``/``pytest``
analog zu allen anderen ``party_engine``-Modulen.
"""

from __future__ import annotations

from dataclasses import replace

from party_engine.domain import (
    CatalogItem,
    DirectConsumable,
    GuestResponse,
    PartyCatalog,
    Recipe,
)
from party_engine.occasions import get_occasion, resolve_combined_profile
from party_engine.recommendation_domain import (
    DEFAULT_OCCASION_ID,
    GroupSignal,
    OccasionProfile,
    RecommendationContext,
    RecommendationExposure,
    RecommendationScore,
)
from party_context.context_fit import calculate_context_fit
from party_context.domain import DerivedPartyContext, FoodContextModifiers, LearningHistory

# ---------------------------------------------------------------------------
# §7 — Basisformel-Gewichte
# ---------------------------------------------------------------------------
#   base_score = 0.40*tag_match + 0.15*category_match + 0.10*popularity_prior
#              + 0.10*crowd_pleaser_score + 0.10*context_match
#              + 0.10*operational_fit + 0.05*dietary_coverage
# Danach: + occasion_affinity_override + admin_boost - admin_suppression
#         - complexity_penalties - diversity_penalties (letztere: Listenebene)
_W_TAG_MATCH = 0.40
_W_CATEGORY = 0.15
_W_POPULARITY = 0.10
_W_CROWD_PLEASER = 0.10
_W_CONTEXT = 0.10
_W_OPERATIONAL = 0.10
_W_DIETARY = 0.05

# Adaptives Gruppenfeedback (§62) ist laut Spec ein zusätzlicher, später
# ("adaptiv") hinzukommender Term, NICHT Teil der obigen Basisformel. Wir
# gewichten ihn als kleine, begrenzte Verschiebung relativ zum Popularitäts-
# Prior (nur wirksam, wenn ein GroupSignal übergeben wird).
_W_GROUP_SIGNAL = 0.15

# §78 (Party-Context-Engine-Spec): ContextFitScore (Saison/Location/Daypart/
# Wetter/Infrastruktur aus dem zentralen ``party_context``-Package) ist
# explizit eine EIGENE, additive Schicht - "Nicht Context Logic in
# score_item_for_occasion() hineinmischen". Wird nur angewendet, wenn ein
# ``derived_context`` übergeben wird (sonst 0.0, volle Rückwärtskompatibilität
# zur bisherigen Basisformel/Tests).
_W_CONTEXT_FIT = 0.15

# Geo-Kultur-Spec §7: gelernte Cross-Party-Präferenz - analog zu
# _W_GROUP_SIGNAL eine kleine, additive Verschiebung relativ zum NEUTRALEN
# Prior 0.5 (nicht zum popularity_score - ``compute_learned_preference_score``
# schrumpft bereits selbst Richtung 0.5, siehe dortige Docstring). Bewusst
# klein gehalten (§5-Prinzip: Historie ergänzt, überstimmt nie tatsächliche
# aktuelle Gästewünsche/``group_signal``). 0.0 Effekt bei leerer Historie
# (Kaltstart-Pflichtverhalten, §7) — learned_score ist dann exakt 0.5.
_W_LEARNED = 0.08

# §24-28 (Party-Context-Engine-Spec): FoodContextModifiers-Präferenzen sind
# tag-basiert (analog zum bereits etablierten Diät-Heuristik-Muster in
# ``_structural_diet_flags``) - das Domain-Modell hat keine expliziten
# "ist Salat"/"ist Fingerfood"-Felder, das bestehende Tag-Vokabular
# (``party_engine/tags.py``) deckt diese Kategorien aber bereits ab.
_FOOD_PREFERENCE_TAG_GROUPS: dict[str, frozenset[str]] = {
    "fresh_food_preference": frozenset({"fresh", "vegetable", "fruit", "light_food", "refreshing_food"}),
    "hot_food_preference": frozenset({"baked_food", "cooked", "rich"}),
    "comfort_food_preference": frozenset({"comfort_food", "rich", "filling"}),
    "salad_preference": frozenset({"salad"}),
    "grill_preference": frozenset({"grilled_food", "bbq", "grilled"}),
    "fingerfood_preference": frozenset({"fingerfood", "fingerfood_food", "handheld", "snack"}),
    "dessert_preference": frozenset({"dessert", "sweet_food"}),
}

# §28/§29: Hinweis-Tags auf potenziell kühlkritische/verderbliche Speisen,
# genutzt als Fallback, wenn kein explizites ``perishability_score``/
# ``requires_cooling`` auf dem Item selbst kuratiert ist (Katalog-Default
# bleibt neutral 0.5/False, siehe ``party_engine/domain.py``).
_PERISHABLE_HINT_TAGS: frozenset[str] = frozenset({"creamy", "cheese", "fish", "seafood"})

# total_score wird NICHT hart auf [0, 1] geklemmt (das würde für Ranking-
# Zwecke Signal verlieren, insbesondere positive occasion_affinity_overrides
# und Admin-Boosts sollen sich weiterhin gegenüber Score 1.0 absetzen können).
# Ein grosszügiges Clipping verhindert nur pathologische Ausreisser.
_SCORE_CLIP_MIN = -0.5
_SCORE_CLIP_MAX = 1.5

# §52: Schwellenwerte für "kleine" vs. "grosse" Gruppe (dokumentierte,
# konfigurierbare Heuristik — die Spec gibt keine exakten Zahlen vor).
_SMALL_GROUP_THRESHOLD = 15
_LARGE_GROUP_THRESHOLD = 40

# §64/§66: Food-Protein-Familien (aus dem bereits vorhandenen Tag-Vokabular,
# siehe tags.py FOOD_CHARACTER_TAGS). Bewusst NUR die eigentlichen
# Fleisch-/Fisch-Proteinfamilien (§64: "food protein" als Diversity-Dimension
# soll verhindern, dass z.B. 10 Rindfleisch-Gerichte in Folge empfohlen
# werden) — "vegetarian"/"vegan" sind hier ABSICHTLICH ausgeschlossen. Es
# sind Diät-COVERAGE-Tags (fast jedes Getränk/viele Speisen tragen sie
# korrekterweise), keine knappe "Familie": würde man sie mit demselben
# Deckel wie "beef"/"fish" behandeln, würde bereits nach
# max_same_food_protein_family vegan/vegetarischen Items JEDES weitere
# vegane/vegetarische Getränk oder Gericht blockiert (realer Bug: hat z.B.
# bei cocktail_party fast alle Cocktails aus der Empfehlungsliste verdrängt,
# da praktisch jeder Cocktail korrekt "vegan"+"vegetarian" trägt). §66
# verlangt sogar MEHR vegetarische/vegane Abdeckung, nie eine Obergrenze.
FOOD_PROTEIN_TAGS: frozenset[str] = frozenset({"beef", "pork", "poultry", "fish"})

# Für die (best-effort) tag-basierte Diät-Strukturprüfung, wenn kein Catalog
# zur Ingredient-Auflösung zur Verfügung steht (siehe _dietary_violation_reason).
_MEAT_ISH_TAGS: frozenset[str] = frozenset({"meat", "beef", "pork", "poultry", "fish", "seafood"})
# Zusätzliche Hinweis-Tags auf tierische (aber nicht "Fleisch"-) Zutaten, für
# die Vegan-Fallback-Heuristik relevant (z.B. Milchprodukte). Bewusst NICHT
# Teil von _MEAT_ISH_TAGS, da "vegetarisch" davon unberührt bleibt (Käse ist
# vegetarisch-kompatibel, aber nicht vegan-kompatibel).
_NON_VEGAN_HINT_TAGS: frozenset[str] = _MEAT_ISH_TAGS | {"cheese", "creamy"}

_BEVERAGE_DEMAND_GROUPS: frozenset[str] = frozenset(
    {"alcoholic_beverage", "non_alcoholic_beverage", "beverage_general", "energy"}
)

# §59: Ingredient-Overlap-Bonus — bewusst klein gehalten ("do not let overlap
# destroy diversity ... use only a small bonus").
_INGREDIENT_OVERLAP_BONUS_PER_SHARED = 0.03
_INGREDIENT_OVERLAP_BONUS_CAP = 0.08


# ---------------------------------------------------------------------------
# §61/§78 — Diät-Sicherheits-Invariante
# ---------------------------------------------------------------------------


def _structural_diet_flags(item: CatalogItem, catalog: PartyCatalog | None) -> dict:
    """Liefert bereits vorhandene strukturelle Diät-Signale für ``item``
    (KEINE Neu-Ableitung — nutzt ausschließlich Felder, die schon anderswo
    im Codebase berechnet wurden):

        * Recipe: ``item.is_vegan`` / ``item.is_vegetarian`` (bereits von
          build_catalog.py aus den Zutaten abgeleitet).
        * DirectConsumable (mit ``catalog`` verfügbar): Auflösung über das
          referenzierte ``Ingredient`` (``item.ingredient_id`` ->
          ``catalog.ingredients[...].is_vegan/.is_vegetarian``).
        * Fallback (kein Catalog verfügbar, z.B. innerhalb von
          ``score_item_for_occasion``, das keinen Catalog-Parameter besitzt):
          nutzt die bereits abgeleiteten ``item.recommendation.tags``. Ein
          fehlender expliziter "vegan"-Tag bedeutet dabei NICHT
          automatisch "nicht vegan" (die meisten vegan-verträglichen Items,
          z.B. reine Spirituosen, tragen gar keinen expliziten "vegan"-Tag)
          — stattdessen wird konservativ auf tierische Hinweis-Tags geprüft
          (``_NON_VEGAN_HINT_TAGS``: Fleisch/Fisch/Käse/Sahne-artig). Fehlen
          diese, gilt das Item als vegan-verträglich. Das entspricht dem
          tatsächlichen Verhalten von ``derive_recommendation_metadata()``
          (siehe recommendation_tagging.py), das "vegan" nur für explizit
          als vegan markierte Zutaten-Familien setzt, aber KEIN "nicht
          vegan"-Signal für alles andere erzeugt.
    """
    tags = item.recommendation.tags

    if isinstance(item, Recipe):
        is_vegan = item.is_vegan
        is_vegetarian = item.is_vegetarian
    elif isinstance(item, DirectConsumable) and catalog is not None and item.ingredient_id:
        ingredient = catalog.ingredients.get(item.ingredient_id)
        if ingredient is not None:
            is_vegan = ingredient.is_vegan
            is_vegetarian = ingredient.is_vegetarian
        else:
            is_vegan = not bool(tags & _NON_VEGAN_HINT_TAGS)
            is_vegetarian = not bool(tags & _MEAT_ISH_TAGS)
    else:
        is_vegan = not bool(tags & _NON_VEGAN_HINT_TAGS)
        is_vegetarian = not bool(tags & _MEAT_ISH_TAGS)

    return {
        "is_vegan": is_vegan,
        "is_vegetarian": is_vegetarian,
        "has_pork": "pork" in tags,
        "has_beef": "beef" in tags,
        "has_meat": bool(tags & {"meat", "beef", "pork", "poultry"}),
        "has_fish": bool(tags & {"fish", "seafood"}),
    }


def _dietary_violation_reason(
    item: CatalogItem,
    guest: GuestResponse | None,
    catalog: PartyCatalog | None = None,
) -> str | None:
    """Prüft harte ``DietaryProfile``-Constraints (§61/§78). Gibt einen
    kurzen deutschen Ausschlussgrund zurück, falls ``item`` strukturell
    inkompatibel ist, sonst ``None``.

    Bewusst NUR für Constraints geprüft, für die ein verlässliches
    strukturelles Signal existiert (vegan/vegetarian/no_pork/no_beef/
    pescatarian). ``gluten_free``/``lactose_free``/``halal_required``/
    ``allergies`` werden hier NICHT hart gefiltert — die einzigen
    verfügbaren Tags dafür sind ``potential_gluten_free``/
    ``potential_lactose_free``, die die Spec (§3) explizit als "keine
    Allergiesicherheitsgarantie" markiert. Ein harter Ausschluss auf dieser
    Basis würde eine Sicherheit vortäuschen, die nicht besteht.
    """
    if guest is None:
        return None
    dietary = guest.dietary
    if dietary is None or dietary.is_empty():
        return None

    flags = _structural_diet_flags(item, catalog)

    if dietary.vegan and not flags["is_vegan"]:
        return "Nicht vegan"
    if dietary.vegetarian and not flags["is_vegetarian"]:
        return "Nicht vegetarisch"
    if dietary.no_pork and flags["has_pork"]:
        return "Enthält Schweinefleisch"
    if dietary.no_beef and flags["has_beef"]:
        return "Enthält Rindfleisch"
    if dietary.pescatarian and flags["has_meat"] and not flags["has_fish"]:
        return "Nicht pescatarisch"
    return None


# ---------------------------------------------------------------------------
# §1/§7 — Tag-Match (occasion_match)
# ---------------------------------------------------------------------------


def _tag_match_score(
    item_tags: set[str],
    preferred_tags: dict[str, float],
    discouraged_tags: dict[str, float],
) -> float:
    """Gewichtete Tag-Ähnlichkeit zwischen Item und Occasion (§7).

    ``raw = sum(preferred[t] for t in item_tags) - sum(discouraged[t] for t
    in item_tags)``. Normalisierung: Division durch einen fixen
    Sättigungspunkt (3.0) statt durch ``len(item_tags)``/``len(preferred)``
    (beides würde entweder Items mit vielen Tags oder Occasions mit vielen
    preferred_tags systematisch benachteiligen). 3 bis 4 stark bevorzugte
    Tags (Gewicht ~1.0) reichen damit bereits aus, um den oberen Bereich zu
    erreichen — konsistent mit den Occasion-Profil-Beispielen in §8-29, wo
    "signature" Items i.d.R. 3+ stark gewichtete Tags treffen. Ergebnis wird
    auf [0, 1] geklemmt.
    """
    if not item_tags:
        return 0.0
    positive = sum(preferred_tags.get(t, 0.0) for t in item_tags)
    negative = sum(discouraged_tags.get(t, 0.0) for t in item_tags)
    normalized = (positive - negative) / 3.0
    return max(0.0, min(1.0, normalized))


# ---------------------------------------------------------------------------
# §7 — category_match (fuzzy Abgleich gegen Admin-Slot-Kategorien)
# ---------------------------------------------------------------------------


def _tokenize(value: str) -> set[str]:
    return set(value.split("_")) if value else set()


def _category_match_score(item: CatalogItem, occasion_profile: OccasionProfile) -> float:
    """Kleineres Signal (§7 ``category_match``): wie gut passt
    ``item.category``/``item.demand_group`` zu den vom Occasion-Profil
    definierten Admin-Slot-Keys (``admin_food_slots``/``admin_beverage_slots``,
    z.B. ``"grill_main"``, ``"side_salad"``, ``"water_non_alcoholic"``)?

    Dokumentierte Heuristik (bewusst simpel gehalten, siehe Task-Vorgabe
    "fuzzy/substring match is fine — keep simple and documented"): beide
    Seiten werden an ``"_"`` in Tokens zerlegt (z.B. ``"side_salad"`` ->
    ``{"side", "salad"}``, item-Tokens = Vereinigung aus ``category`` und
    ``demand_group``-Tokens). Für jeden Slot-Key wird
    ``|common| / min(|item_tokens|, |slot_tokens|)`` berechnet, der Max-Wert
    über alle Slot-Keys gewinnt. Kein Treffer -> 0.0.
    """
    slot_keys = list(occasion_profile.admin_food_slots) + list(occasion_profile.admin_beverage_slots)
    if not slot_keys:
        return 0.0

    item_tokens = _tokenize(item.category) | _tokenize(item.demand_group)
    if not item_tokens:
        return 0.0

    best = 0.0
    for slot_key in slot_keys:
        slot_tokens = _tokenize(slot_key)
        if not slot_tokens:
            continue
        common = item_tokens & slot_tokens
        if not common:
            continue
        score = len(common) / min(len(item_tokens), len(slot_tokens))
        best = max(best, score)
    return best


# ---------------------------------------------------------------------------
# §51/§52 — Kontext-Modifikatoren (Saison / Tageszeit / Gruppengrösse)
# ---------------------------------------------------------------------------


def _season_component(item: CatalogItem, season: str | None) -> float:
    if not season:
        return 0.5
    return getattr(item.recommendation, f"{season}_score", 0.5)


def _time_component(item: CatalogItem, hour_of_day: int | None) -> float:
    """§51 Tageszeit-Boosts. Exakte Bänder aus der Spec:
        < 14:00        -> brunch/coffee/juice/non_alcoholic/light_food
        14:00 - 18:00   -> daytime/refreshing/outdoor
        > 18:00         -> evening/cocktail/wine
        "late-night"    -> late_night/snack/late_night_food

    Die Spec nennt für "late-night" keine exakte Stundengrenze — wir
    interpretieren (dokumentiert) 23:00-04:59 als late-night (Partys, die
    über Mitternacht hinausgehen), 18:00-22:59 als "evening" gemäss Vorgabe
    "after 18:00". ``daytime_score``/``evening_score``/``late_night_score``
    aus RecommendationMetadata werden als Basiswert je Band verwendet, ein
    Tag-Treffer im band-spezifischen Set gibt einen zusätzlichen Bonus.
    """
    if hour_of_day is None:
        return 0.5

    tags = item.recommendation.tags
    if hour_of_day >= 23 or hour_of_day < 5:
        band_tags = {"late_night", "snack", "late_night_food"}
        base = item.recommendation.late_night_score
    elif hour_of_day < 14:
        band_tags = {"brunch", "coffee", "juice", "non_alcoholic", "light_food"}
        base = item.recommendation.daytime_score
    elif hour_of_day < 18:
        band_tags = {"daytime", "refreshing", "outdoor"}
        base = item.recommendation.daytime_score
    else:
        band_tags = {"evening", "cocktail", "wine"}
        base = item.recommendation.evening_score

    bonus = 0.15 if (tags & band_tags) else 0.0
    return max(0.0, min(1.0, base + bonus))


def _group_size_component(item: CatalogItem, guest_count: int | None) -> float:
    """§52: kleine Gruppen boosten ``small_group_score``, grosse Gruppen
    ``large_group_score``. Zwischen den Schwellenwerten wird linear
    interpoliert, statt hart umzuschalten (vermeidet Sprungstellen im
    Ranking bei z.B. 20 vs. 21 Gästen)."""
    if guest_count is None:
        return 0.5
    small = item.recommendation.small_group_score
    large = item.recommendation.large_group_score
    if guest_count <= _SMALL_GROUP_THRESHOLD:
        return small
    if guest_count >= _LARGE_GROUP_THRESHOLD:
        return large
    span = _LARGE_GROUP_THRESHOLD - _SMALL_GROUP_THRESHOLD
    weight_large = (guest_count - _SMALL_GROUP_THRESHOLD) / span
    return (1 - weight_large) * small + weight_large * large


def _is_bar_focused_occasion(occasion_profile: OccasionProfile) -> bool:
    """§14/§52: eine Occasion gilt als "cocktail-fokussiert", wenn
    "cocktail" oder "bar_style" mit hohem Gewicht (>= 0.8) preferred ist
    (z.B. cocktail_party). Wird sowohl für die Operational-Score-Dämpfung
    als auch für die Grossgruppen-Komplexitätsstrafe genutzt."""
    return (
        occasion_profile.preferred_tags.get("bar_style", 0.0) >= 0.8
        or occasion_profile.preferred_tags.get("cocktail", 0.0) >= 0.8
    )


def _large_group_complexity_penalty(
    item: CatalogItem,
    guest_count: int | None,
    is_bar_occasion: bool,
) -> float:
    """§52 explizites Beispiel: ein Rezept mit 6+ unterschiedlichen frischen
    Komponenten bekommt für grosse Gruppen (>= ``_LARGE_GROUP_THRESHOLD``)
    eine operative Strafe, AUSSER die Occasion ist explizit
    cocktail-/bar-fokussiert. Zusätzlich ein kleinerer, kontinuierlicher
    Malus proportional zu ``purchase_complexity``."""
    if guest_count is None or guest_count < _LARGE_GROUP_THRESHOLD:
        return 0.0
    if is_bar_occasion:
        return 0.0

    penalty = 0.10 * item.recommendation.purchase_complexity
    if isinstance(item, Recipe) and len(item.components) >= 6:
        penalty += 0.15
    return penalty


def _food_context_preference_score(item: CatalogItem, food_modifiers: FoodContextModifiers) -> float:
    """§24-27 (Party-Context-Engine-Spec): mittelt die ``FoodContextModifiers``-
    Präferenzwerte über alle Tag-Gruppen, die ``item`` trifft (z.B. Sommer
    boostet ``fresh_food_preference``/``salad_preference`` für ein Item mit
    Tag "salad"). Trifft ein Item keine Gruppe (z.B. ein reines Getränk),
    ergibt sich neutral 0.0. Werte liegen typischerweise in
    ``FOOD_MODIFIER_FIELD_BOUNDS`` (0.5-1.6) - zentriert auf 1.0 -> als
    additiver Score-Delta wird ``multiplier - 1.0`` verwendet."""
    tags = item.recommendation.tags
    deltas = [
        getattr(food_modifiers, field_name) - 1.0
        for field_name, group_tags in _FOOD_PREFERENCE_TAG_GROUPS.items()
        if tags & group_tags
    ]
    if not deltas:
        return 0.0
    return sum(deltas) / len(deltas)


def _food_spoilage_penalty(item: CatalogItem, food_modifiers: FoodContextModifiers) -> float:
    """§28/§29: wendet ``spoilage_operational_penalty`` NUR auf Items an, die
    tatsächlich ein Verderbs-/Kühlrisiko tragen (kuratiertes
    ``perishability_score``/``requires_cooling``/``temperature_sensitive``
    auf Ingredient/Recipe, sonst Tag-Fallback über
    ``_PERISHABLE_HINT_TAGS``) - ein uniform auf ALLE Food-Items angewendeter
    Malus würde die Verderbs-Warnung bedeutungslos machen."""
    if food_modifiers.spoilage_operational_penalty <= 0:
        return 0.0
    perishability_score = getattr(item, "perishability_score", 0.5)
    requires_cooling = getattr(item, "requires_cooling", False)
    temperature_sensitive = getattr(item, "temperature_sensitive", False)
    is_perishable = requires_cooling or temperature_sensitive or perishability_score >= 0.6
    if not is_perishable:
        is_perishable = bool(item.recommendation.tags & _PERISHABLE_HINT_TAGS)
    return food_modifiers.spoilage_operational_penalty if is_perishable else 0.0


def _operational_score(item: CatalogItem, is_bar_occasion: bool) -> float:
    """§53/§54 Komplexitäts-Philosophie: belohnt operativ einfache Items
    (``1 - complexity``), gewichtet Vorbereitung am stärksten, dann Service,
    dann Einkauf. Für explizit bar-/cocktail-fokussierte Occasions (§14:
    "prep_complexity and bar_required penalties should be substantially
    lower for this occasion") wird der Effekt der Komplexität gedämpft,
    indem der Rohwert zur Hälfte mit einem neutral-hohen Baseline-Wert
    (0.75) gemischt wird — ein komplexer Cocktail fällt so nicht mehr so
    stark ab, wie es bei einer "normalen" Occasion der Fall wäre."""
    prep = item.recommendation.prep_complexity
    service = item.recommendation.service_complexity
    purchase = item.recommendation.purchase_complexity
    ease = (1 - prep) * 0.40 + (1 - service) * 0.35 + (1 - purchase) * 0.25
    if is_bar_occasion:
        ease = 0.5 * ease + 0.5 * 0.75
    return max(0.0, min(1.0, ease))


# ---------------------------------------------------------------------------
# §77/§83 — Reason-Strings
# ---------------------------------------------------------------------------


def _build_reasons(
    item: CatalogItem,
    occasion_profile: OccasionProfile,
    *,
    tag_match_score: float,
    context_score: float,
    dietary_score: float,
    crowd_pleaser_score: float,
    popularity_score: float,
    group_signal: GroupSignal | None,
    group_score: float,
    admin_override: dict[str, float] | None,
    guest_count: int | None,
    is_signature: bool,
    context_fit_score: float = 0.0,
    learned_score: float = 0.5,
) -> list[str]:
    reasons: list[str] = []
    if tag_match_score >= 0.55:
        reasons.append(f"Typisch für {occasion_profile.label_de}")
    if context_score >= 0.70:
        reasons.append("Passt gut zum aktuellen Kontext (Saison/Uhrzeit)")
    if context_fit_score >= 0.70:
        reasons.append("Passt gut zu Ort, Wetter und Infrastruktur der Party")
    if learned_score >= 0.60:
        # Geo-Kultur-Spec §8: Explainability für die gelernte Komponente -
        # nur sichtbar, wenn sie den Score TATSÄCHLICH spürbar verschoben hat
        # (0.5 = neutral/Kaltstart, kein Reason-Text).
        reasons.append("Bei früheren Partys in ähnlichem Kontext häufig gewählt")
    if (
        guest_count is not None
        and guest_count >= _LARGE_GROUP_THRESHOLD
        and item.recommendation.large_group_score >= 0.70
    ):
        reasons.append("Einfach für größere Gruppen")
    if dietary_score >= 0.80 and (item.recommendation.tags & {"vegetarian_friendly", "vegan_friendly"}):
        reasons.append("Vegetarische/vegane Option mit breiter Abdeckung")
    if crowd_pleaser_score >= 0.80:
        reasons.append("Aktuell allgemein beliebt")
    if group_signal is not None and group_signal.eligible_response_count > 0 and group_score > popularity_score + 0.05:
        reasons.append("Aktuell bei euren Gästen beliebt")
    if admin_override:
        if admin_override.get("boost", 0.0) > 0:
            reasons.append("Manuell hervorgehoben")
        if admin_override.get("suppress", 0.0) > 0:
            reasons.append("Manuell zurückgestuft")
    if is_signature:
        reasons.append(f"Signature-Empfehlung für {occasion_profile.label_de}")
    return reasons


# ---------------------------------------------------------------------------
# §82 — Haupt-Scoring-API
# ---------------------------------------------------------------------------


def score_item_for_occasion(
    item: CatalogItem,
    occasion_profile: OccasionProfile,
    party_context: RecommendationContext,
    guest: GuestResponse | None = None,
    group_signal: GroupSignal | None = None,
    admin_override: dict[str, float] | None = None,
    derived_context: DerivedPartyContext | None = None,
    learning_history: LearningHistory | None = None,
) -> RecommendationScore:
    """§7/§82: Kern-Scoring-Funktion. ``admin_override`` ist optional ein
    Dict mit den Keys ``"boost"``/``"suppress"`` (beide >= 0, additiv
    verrechnet als ``boost - suppress``).

    ``derived_context`` (§76/§78 der Party-Context-Engine-Spec): optionaler,
    zentral von ``PartyContextEngine.derive_context()`` abgeleiteter
    Kontext (Saison/Location/Daypart/Wetter/Infrastruktur). Wird bewusst NICHT
    in die bestehende ``context_score``-Basisformel gemischt, sondern als
    eigene additive Schicht (``context_fit_score``, siehe
    ``party_context.context_fit.calculate_context_fit``) angewendet - "Nicht
    Context Logic in score_item_for_occasion() hineinmischen" (§78). Bleibt
    ``derived_context`` ``None`` (Standard), ist ``context_fit_score`` 0.0 und
    das Verhalten identisch zur bisherigen Formel.

    ``learning_history`` (Geo-Kultur-Spec §7): optional, aggregierte Sicht
    über vergangene ``party_runs``/``selection_events``
    (``party_context.learning_storage.get_learning_history``). Nur wirksam,
    wenn ZUSÄTZLICH ``derived_context`` übergeben wird (liefert die
    Kontext-Dimensionen season/location_type/country_code für den
    Ähnlichkeits-Abgleich). Bleibt ``learning_history`` ``None`` oder ist sie
    leer (Kaltstart), ist ``learned_score`` exakt 0.5 und hat GAR KEINEN
    Effekt auf ``total_score`` (Rückwärtskompatibilität).

    Diät-Sicherheit (§61/§78): wird ein harter ``guest.dietary``-Constraint
    strukturell verletzt, wird SOFORT ein Score mit ``total_score=0.0``
    zurückgegeben (Item wird nirgendwo in der Formel weiterverrechnet). Dies
    ist die "defense in depth"-Ebene innerhalb des Einzel-Item-Scorings; die
    AUTORITATIVE (catalog-bewusste) Durchsetzung erfolgt zusätzlich auf
    Listenebene in ``recommend_for_guest`` (dort wird das Item bereits VOR
    dem Scoring komplett aus dem Kandidatenpool entfernt, siehe dortige
    Docstring).
    """
    violation = _dietary_violation_reason(item, guest, catalog=None)
    if violation is not None:
        return RecommendationScore(
            item_id=item.id,
            total_score=0.0,
            dietary_score=0.0,
            penalties={"dietary_hard_constraint": -1.0},
            reasons=[violation],
            is_signature=False,
        )

    tags = item.recommendation.tags
    tag_match = _tag_match_score(tags, occasion_profile.preferred_tags, occasion_profile.discouraged_tags)
    category_score = _category_match_score(item, occasion_profile)

    is_bar_occasion = _is_bar_focused_occasion(occasion_profile)

    season_component = _season_component(item, party_context.season)
    time_component = _time_component(item, party_context.hour_of_day)
    group_component = _group_size_component(item, party_context.guest_count)
    context_score = max(0.0, min(1.0, (season_component + time_component + group_component) / 3.0))

    operational_score = _operational_score(item, is_bar_occasion)

    popularity_score = item.recommendation.popularity_prior
    crowd_pleaser_score = item.recommendation.crowd_pleaser_score
    dietary_score = item.recommendation.dietary_coverage

    base_score = (
        _W_TAG_MATCH * tag_match
        + _W_CATEGORY * category_score
        + _W_POPULARITY * popularity_score
        + _W_CROWD_PLEASER * crowd_pleaser_score
        + _W_CONTEXT * context_score
        + _W_OPERATIONAL * operational_score
        + _W_DIETARY * dietary_score
    )

    total_score = base_score

    occasion_override = item.recommendation.occasion_affinity_overrides.get(occasion_profile.id, 0.0)
    total_score += occasion_override

    if admin_override:
        admin_score = admin_override.get("boost", 0.0) - admin_override.get("suppress", 0.0)
    else:
        admin_score = 0.0
    total_score += admin_score

    if group_signal is not None:
        group_score = compute_group_signal_score(group_signal, popularity_score)
        # §62: Gruppenfeedback ist ein additiver, adaptiver Zusatzterm -
        # verschiebt den Score relativ zum Popularitäts-Prior, statt ihn zu
        # ersetzen (verhindert, dass ein einzelnes GroupSignal die gesamte
        # Basisformel dominiert).
        total_score += _W_GROUP_SIGNAL * (group_score - popularity_score)
    else:
        group_score = 0.0

    if derived_context is not None:
        context_fit_score = calculate_context_fit(item, derived_context).total_score
        total_score += _W_CONTEXT_FIT * context_fit_score
    else:
        context_fit_score = 0.0

    if derived_context is not None and learning_history is not None:
        context_dims = {
            "season": derived_context.season,
            "location_type": derived_context.location_type,
            "country_code": derived_context.country_code,
        }
        learned_score = compute_learned_preference_score(item.id, context_dims, learning_history)
        # Analog zu §62 (Gruppenfeedback): additive, begrenzte Verschiebung
        # relativ zum NEUTRALEN Prior 0.5 (nicht zum popularity_score) - bei
        # 0.5 (Kaltstart/keine ähnliche Historie) exakt 0.0 Effekt.
        total_score += _W_LEARNED * (learned_score - 0.5)
    else:
        learned_score = 0.5

    penalties: dict[str, float] = {}

    if derived_context is not None:
        food_preference_delta = _food_context_preference_score(item, derived_context.food_modifiers)
        if food_preference_delta:
            total_score += _W_CONTEXT_FIT * food_preference_delta
        spoilage_penalty = _food_spoilage_penalty(item, derived_context.food_modifiers)
        if spoilage_penalty > 0:
            penalties["food_spoilage_risk"] = -spoilage_penalty
            total_score -= spoilage_penalty

    complexity_penalty = _large_group_complexity_penalty(item, party_context.guest_count, is_bar_occasion)
    if complexity_penalty > 0:
        penalties["complexity"] = -complexity_penalty
        total_score -= complexity_penalty

    total_score = max(_SCORE_CLIP_MIN, min(_SCORE_CLIP_MAX, total_score))

    # §67: Signature-Status wird aus Metadaten abgeleitet, nicht hardcoded.
    is_signature = tag_match >= 0.8 and (popularity_score >= 0.6 or occasion_override > 0.0)

    reasons = _build_reasons(
        item,
        occasion_profile,
        tag_match_score=tag_match,
        context_score=context_score,
        dietary_score=dietary_score,
        crowd_pleaser_score=crowd_pleaser_score,
        popularity_score=popularity_score,
        group_signal=group_signal,
        group_score=group_score,
        admin_override=admin_override,
        guest_count=party_context.guest_count,
        is_signature=is_signature,
        context_fit_score=context_fit_score,
        learned_score=learned_score,
    )

    return RecommendationScore(
        item_id=item.id,
        total_score=total_score,
        tag_match_score=tag_match,
        category_score=category_score,
        context_score=context_score,
        popularity_score=popularity_score,
        crowd_pleaser_score=crowd_pleaser_score,
        operational_score=operational_score,
        dietary_score=dietary_score,
        group_score=group_score,
        admin_score=admin_score,
        context_fit_score=context_fit_score,
        learned_score=learned_score,
        penalties=penalties,
        reasons=reasons,
        is_signature=is_signature,
    )


# ---------------------------------------------------------------------------
# §62 — Adaptiver Gruppen-Score (Bayesian Shrinkage)
# ---------------------------------------------------------------------------


def compute_group_signal_score(
    group_signal: GroupSignal,
    occasion_prior: float,
    prior_strength: float = 10.0,
) -> float:
    """§62: ``posterior = (supporting_guests + prior_strength * occasion_prior)
    / (eligible_response_count + prior_strength)``.

    ``occasion_prior`` wird vom Aufrufer übergeben (i.d.R.
    ``item.recommendation.popularity_prior``, siehe Docstring in
    ``score_item_for_occasion``, wo genau dieser Wert verwendet wird).
    Schutz gegen Division durch 0: ohne belastbare Stichprobe
    (``eligible_response_count == 0``) wird unverändert der Prior
    zurückgegeben.
    """
    if group_signal.eligible_response_count <= 0:
        return occasion_prior
    return (
        group_signal.supporting_guests + prior_strength * occasion_prior
    ) / (group_signal.eligible_response_count + prior_strength)


# ---------------------------------------------------------------------------
# Geo-Kultur-Spec §7 — Persistentes Cross-Party-Lernen (Bayesian Shrinkage)
# ---------------------------------------------------------------------------

# Kontext-Dimensionen, über die ÄHNLICHKEIT vergangener Partys bestimmt wird
# (Geo-Kultur-Spec §7: "gleiche season ODER gleicher location_type ODER
# gleicher country_code - gewichtete Teilmengen-Übereinstimmung"). Bewusst
# als Modulkonstante, damit der Aufrufer (``score_item_for_occasion``) und
# ``compute_learned_preference_score`` denselben Dimensions-Satz verwenden.
_LEARNING_CONTEXT_DIMENSIONS: tuple[str, ...] = ("season", "location_type", "country_code")


def compute_learned_preference_score(
    item_id: str,
    context_dims: dict[str, str],
    history: LearningHistory,
    prior_strength: float = 10.0,
) -> float:
    """Geo-Kultur-Spec §7: identisches mathematisches Muster wie
    ``compute_group_signal_score`` (Bayesian Shrinkage Richtung eines
    neutralen Priors), nur über ``history.runs``/``history.events`` (mehrere
    vergangene Partys) statt über die Gäste-Antworten EINER Party.

    ``observed_rate`` = Anteil ÄHNLICHER vergangener Partys (mindestens eine
    übereinstimmende Dimension aus ``context_dims``, gewichtet nach Anzahl
    übereinstimmender Dimensionen - kein exaktes Kontext-Match nötig, sonst
    zu wenige Datenpunkte), in denen ``item_id`` tatsächlich gewählt wurde.

    Kaltstart (Pflicht, §7): ohne Historie (``history.runs`` leer) oder ohne
    auch nur eine ähnliche vergangene Party liefert diese Funktion exakt
    ``0.5`` (neutral) - hat dann per Definition KEINEN Effekt auf die
    Ranking-Reihenfolge (siehe ``_W_LEARNED``-Verrechnung in
    ``score_item_for_occasion``, die relativ zu diesem Neutral-Prior 0.5
    verschiebt, nicht relativ zu ``popularity_score``)."""
    if not history.runs:
        return 0.5

    dim_names = [dim for dim in _LEARNING_CONTEXT_DIMENSIONS if context_dims.get(dim)]
    if not dim_names:
        return 0.5

    selected_item_ids_by_run: dict[int, set[str]] = {}
    for event in history.events:
        if event.event_type != "selected":
            continue
        selected_item_ids_by_run.setdefault(event.party_run_id, set()).add(event.item_id)

    eligible_weight = 0.0
    supporting_weight = 0.0
    for run in history.runs:
        matches = sum(1 for dim in dim_names if getattr(run, dim, "") == context_dims[dim])
        if matches == 0:
            continue
        weight = matches / len(dim_names)
        eligible_weight += weight
        if item_id in selected_item_ids_by_run.get(run.id, set()):
            supporting_weight += weight

    if eligible_weight <= 0:
        return 0.5

    return (supporting_weight + prior_strength * 0.5) / (eligible_weight + prior_strength)


# ---------------------------------------------------------------------------
# §63 — Exposure-Korrektur
# ---------------------------------------------------------------------------


def apply_exposure_shrinkage(
    exposure: RecommendationExposure,
    prior: float,
    min_sample_size: int = 20,
) -> float:
    """§63: schrumpft die empirische ``selection_rate`` stark Richtung
    ``prior``, solange ``shown_count`` klein ist (lineares Shrinkage-Gewicht
    ``min(1.0, shown_count / min_sample_size)``). Bei ``shown_count == 0``
    wird unverändert der Prior zurückgegeben (kein Signal vorhanden) — so
    wird z.B. "1 shown, 1 selected" NICHT als "universell beliebt"
    fehlinterpretiert (explizites Spec-Beispiel §63)."""
    if exposure.shown_count <= 0:
        return prior
    selection_rate = exposure.selection_rate()
    if selection_rate is None:
        return prior
    weight = min(1.0, exposure.shown_count / min_sample_size)
    return weight * selection_rate + (1 - weight) * prior


# ---------------------------------------------------------------------------
# §64/§65 — Diversity-Constraints
# ---------------------------------------------------------------------------


def apply_diversity_constraints(
    scored_items: list[tuple[CatalogItem, RecommendationScore]],
    max_same_subcategory: int = 2,
    max_same_base_spirit: int = 2,
    max_same_food_protein_family: int = 2,
) -> list[tuple[CatalogItem, RecommendationScore]]:
    """§64-66: greedy Auswahl entlang der Score-Reihenfolge, die pro
    Diversity-Dimension Obergrenzen durchsetzt. Items, die eine Grenze
    überschreiten würden, werden übersprungen (Liste wird dadurch kürzer,
    nicht umsortiert — bereits zugelassene Items bleiben score-absteigend).

    Dokumentierte Heuristiken (das Domain-Modell hat keine expliziten
    "subcategory"/"base_spirit"-Felder):
        * ``subcategory``   -> ``item.category`` direkt (z.B. "beer",
          "cocktail_vodka", "salad" — bereits granular genug für die
          Katalog-Kategorisierung, siehe catalog/*.json).
        * ``base_spirit``   -> nur für Cocktails relevant: ``item.category``,
          FALLS er mit ``"cocktail"`` beginnt (z.B. "cocktail_vodka" -> die
          Kategorie selbst kodiert bereits die Basis-Spirituose, siehe
          build_catalog.py-Kategorisierung). Nicht-Cocktail-Items haben
          keinen "base_spirit" und werden für diese Dimension ignoriert.
        * ``food_protein_family`` -> Schnittmenge aus ``item.recommendation
          .tags`` und ``FOOD_PROTEIN_TAGS`` (§64: "beef, pork, poultry,
          fish, vegetarian, vegan"); ein Item kann mehrere Protein-Tags
          gleichzeitig tragen und zählt dann in mehrere Töpfe ein.
    """
    ordered = sorted(scored_items, key=lambda pair: pair[1].total_score, reverse=True)

    subcategory_counts: dict[str, int] = {}
    base_spirit_counts: dict[str, int] = {}
    protein_family_counts: dict[str, int] = {}
    admitted: list[tuple[CatalogItem, RecommendationScore]] = []

    for item, score in ordered:
        subcategory = item.category
        base_spirit = item.category if item.category.startswith("cocktail") else None
        protein_families = item.recommendation.tags & FOOD_PROTEIN_TAGS

        if subcategory_counts.get(subcategory, 0) >= max_same_subcategory:
            continue
        if base_spirit and base_spirit_counts.get(base_spirit, 0) >= max_same_base_spirit:
            continue
        if protein_families and any(
            protein_family_counts.get(family, 0) >= max_same_food_protein_family for family in protein_families
        ):
            continue

        admitted.append((item, score))
        subcategory_counts[subcategory] = subcategory_counts.get(subcategory, 0) + 1
        if base_spirit:
            base_spirit_counts[base_spirit] = base_spirit_counts.get(base_spirit, 0) + 1
        for family in protein_families:
            protein_family_counts[family] = protein_family_counts.get(family, 0) + 1

    return admitted


def ensure_required_coverage(
    admitted: list[tuple[CatalogItem, RecommendationScore]],
    candidate_pool: list[tuple[CatalogItem, RecommendationScore]],
    domain: str,
) -> list[tuple[CatalogItem, RecommendationScore]]:
    """§66: stellt sicher, dass die finale Liste eine Mindestabdeckung
    besitzt, und füllt bei Bedarf aus ``candidate_pool`` auf (höchster
    verbleibender Score zuerst).

    ``domain="beverage"``: mind. 2 non_alcoholic-Items, mind. 1 breit
    beliebtes Item (``crowd_pleaser_score >= 0.7``), mind. 1 Signature-Item.
    ``domain="food"``: mind. 1 vegetarian_friendly/vegan_friendly Item,
    mind. 1 Crowd-Pleaser, mind. 1 Signature-Item.

    Diätsicherheit beim Nachfüllen: diese Funktion filtert ``candidate_pool``
    selbst NICHT nach Gästen-Diät — sie geht davon aus, dass der Aufrufer
    (``recommend_for_guest``) bereits VOR dem Scoring alle strukturell
    inkompatiblen Items aus dem Pool entfernt hat (siehe dortige Docstring).
    Wird ``candidate_pool`` korrekt vorgefiltert übergeben, kann das
    Nachfüllen keinen harten Diät-Constraint verletzen.
    """
    result = list(admitted)
    admitted_ids = {item.id for item, _ in result}
    pool_sorted = sorted(candidate_pool, key=lambda pair: pair[1].total_score, reverse=True)

    def backfill(predicate, needed: int) -> None:
        have = sum(1 for item, score in result if predicate(item, score))
        if have >= needed:
            return
        for item, score in pool_sorted:
            if have >= needed:
                break
            if item.id in admitted_ids:
                continue
            if predicate(item, score):
                result.append((item, score))
                admitted_ids.add(item.id)
                have += 1

    if domain == "beverage":
        backfill(lambda it, sc: "non_alcoholic" in it.recommendation.tags, 2)
        backfill(lambda it, sc: it.recommendation.crowd_pleaser_score >= 0.7, 1)
        backfill(lambda it, sc: sc.is_signature, 1)
    else:  # "food"
        backfill(lambda it, sc: bool(it.recommendation.tags & {"vegetarian_friendly", "vegan_friendly"}), 1)
        backfill(lambda it, sc: it.recommendation.crowd_pleaser_score >= 0.7, 1)
        backfill(lambda it, sc: sc.is_signature, 1)

    result.sort(key=lambda pair: pair[1].total_score, reverse=True)
    return result


# ---------------------------------------------------------------------------
# Gemeinsame Hilfsfunktion: Kandidaten scoren + nach Domain splitten
# ---------------------------------------------------------------------------


def _split_by_domain(
    scored: list[tuple[CatalogItem, RecommendationScore]]
) -> tuple[list[tuple[CatalogItem, RecommendationScore]], list[tuple[CatalogItem, RecommendationScore]]]:
    """Trennt eine gescorte Liste in (Getränke-Pool, Essen-Pool) anhand
    ``item.demand_group`` (siehe ``_BEVERAGE_DEMAND_GROUPS``)."""
    beverages = [pair for pair in scored if pair[0].demand_group in _BEVERAGE_DEMAND_GROUPS]
    food = [pair for pair in scored if pair[0].demand_group not in _BEVERAGE_DEMAND_GROUPS]
    return beverages, food


def _dedupe_sorted(
    pairs: list[tuple[CatalogItem, RecommendationScore]]
) -> list[tuple[CatalogItem, RecommendationScore]]:
    pairs = sorted(pairs, key=lambda pair: pair[1].total_score, reverse=True)
    seen: set[str] = set()
    deduped: list[tuple[CatalogItem, RecommendationScore]] = []
    for item, score in pairs:
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append((item, score))
    return deduped


# ---------------------------------------------------------------------------
# §60/§61 — Gast-Empfehlungsstrategie
# ---------------------------------------------------------------------------


def recommend_for_guest(
    catalog: PartyCatalog,
    occasion_profile: OccasionProfile,
    party_context: RecommendationContext,
    guest: GuestResponse,
    already_selected_ids: set[str] | None = None,
    top_n: int = 12,
    derived_context: DerivedPartyContext | None = None,
    learning_history: LearningHistory | None = None,
) -> list[tuple[CatalogItem, RecommendationScore]]:
    """§60-61/§64-67: rankt alle empfehlbaren Items für einen konkreten
    Gast. Optimiert für Anlass-Fit, persönliche Diät-Kompatibilität,
    Popularität, Diversity und Entdeckung — NICHT für Einkaufs-Effizienz
    (das ist die Aufgabe von ``recommend_for_admin``).

    ``derived_context`` (§76 Party-Context-Engine-Spec): optional, wird
    unverändert an ``score_item_for_occasion`` durchgereicht (eigene additive
    ContextFit-Schicht, §78).

    Diät-Sicherheit (§61/§78, AUTORITATIVE Durchsetzung): strukturell
    inkompatible Items werden HIER, VOR jeglichem Scoring, aus dem
    Kandidatenpool entfernt (mittels ``catalog``-bewusster
    ``_dietary_violation_reason``-Prüfung, die für ``DirectConsumable`` das
    referenzierte ``Ingredient`` auflöst statt nur auf Tags zurückzugreifen).
    Ein bereits ausgeschlossenes Item wird nie gescort und kann daher auch
    nicht über ``ensure_required_coverage`` wieder hereinrutschen.

    Erzeugt garantiert KEINE ``Preference``/``DemandAllocation``/
    ``IngredientDemand`` (§78) — reine Ranking-Funktion, importiert nichts
    aus der Demand-Pipeline.
    """
    already_selected_ids = already_selected_ids or set()

    scored: list[tuple[CatalogItem, RecommendationScore]] = []
    for item in catalog.all_selectable_items():
        if item.id in already_selected_ids:
            continue
        if not item.recommendation.recommendation_enabled:
            continue
        if _dietary_violation_reason(item, guest, catalog) is not None:
            continue  # harter Diät-Ausschluss - wird gar nicht erst gescort
        score = score_item_for_occasion(
            item,
            occasion_profile,
            party_context,
            guest=guest,
            derived_context=derived_context,
            learning_history=learning_history,
        )
        scored.append((item, score))

    beverage_pool, food_pool = _split_by_domain(scored)

    beverage_admitted = apply_diversity_constraints(beverage_pool)
    beverage_admitted = ensure_required_coverage(beverage_admitted, beverage_pool, domain="beverage")

    food_admitted = apply_diversity_constraints(food_pool)
    food_admitted = ensure_required_coverage(food_admitted, food_pool, domain="food")

    combined = _dedupe_sorted(beverage_admitted + food_admitted)
    return combined[:top_n]


# ---------------------------------------------------------------------------
# §58/§59 — Admin-Empfehlungsstrategie
# ---------------------------------------------------------------------------


def _selected_ingredient_ids(catalog: PartyCatalog, already_selected_ids: set[str]) -> set[str]:
    ingredient_ids: set[str] = set()
    for selected_id in already_selected_ids:
        selected_item = catalog.get_item(selected_id)
        if isinstance(selected_item, Recipe):
            ingredient_ids.update(component.ingredient_id for component in selected_item.components)
        elif isinstance(selected_item, DirectConsumable) and selected_item.ingredient_id:
            ingredient_ids.add(selected_item.ingredient_id)
    return ingredient_ids


def recommend_for_admin(
    catalog: PartyCatalog,
    occasion_profile: OccasionProfile,
    party_context: RecommendationContext,
    already_selected_ids: set[str] | None = None,
    top_n: int = 20,
    derived_context: DerivedPartyContext | None = None,
    learning_history: LearningHistory | None = None,
) -> list[tuple[CatalogItem, RecommendationScore]]:
    """§58-59: rankt Items für den Admin-Sortiment-Bauassistenten. Optimiert
    für Abdeckung, Balance, operative Einfachheit, Anlass-Fit,
    Diät-Diversität und Einkaufs-Effizienz — NICHT primär für individuelle
    Gast-Präferenzen.

    ``derived_context`` (§76 Party-Context-Engine-Spec): optional, wird
    unverändert an ``score_item_for_occasion`` durchgereicht (eigene additive
    ContextFit-Schicht, §78).

    ``learning_history`` (Geo-Kultur-Spec §7): optional, wird unverändert an
    ``score_item_for_occasion`` durchgereicht (gelernte Cross-Party-Präferenz,
    Bayesian Shrinkage). Kaltstart-neutral (0.5), falls ``None`` oder keine
    ähnliche vergangene Party existiert.

    ``admin_score = recommendation_score + assortment_coverage_bonus +
    dietary_coverage_bonus + ingredient_overlap_bonus - complexity_penalty -
    redundancy_penalty`` (§58). Umsetzung im Detail:
        * ``ingredient_overlap_bonus`` (§59): explizit klein gehalten (+0.03
          je gemeinsamer Zutat mit bereits ausgewählten Recipes, gedeckelt
          bei +0.08), damit Overlap die Diversity nicht dominiert.
        * ``assortment_coverage_bonus``/``dietary_coverage_bonus`` werden
          NICHT als eigener numerischer Term, sondern strukturell über
          ``ensure_required_coverage`` (Backfill fehlender Kategorien)
          durchgesetzt — vermeidet Doppelzählung ggü. dem bereits in
          ``score_item_for_occasion`` enthaltenen ``dietary_score``-Term.
        * ``redundancy_penalty`` wird ebenfalls strukturell über
          ``apply_diversity_constraints`` durchgesetzt, allerdings mit
          leicht gelockerten Obergrenzen (+1 ggü. der Gast-Ansicht) — der
          Admin darf mehr ähnliche Optionen gleichzeitig sehen als ein
          einzelner Gast (§65: "Admin view can show more similar items than
          guest view").

    Erzeugt garantiert KEINE ``Preference``/``DemandAllocation``/
    ``IngredientDemand`` (§78).
    """
    already_selected_ids = already_selected_ids or set()
    selected_ingredient_ids = _selected_ingredient_ids(catalog, already_selected_ids)

    scored: list[tuple[CatalogItem, RecommendationScore]] = []
    for item in catalog.all_selectable_items():
        if item.id in already_selected_ids:
            continue
        if not item.recommendation.recommendation_enabled:
            continue
        base = score_item_for_occasion(
            item,
            occasion_profile,
            party_context,
            derived_context=derived_context,
            learning_history=learning_history,
        )

        overlap_bonus = 0.0
        if isinstance(item, Recipe) and selected_ingredient_ids:
            shared = sum(1 for c in item.components if c.ingredient_id in selected_ingredient_ids)
            overlap_bonus = min(_INGREDIENT_OVERLAP_BONUS_CAP, shared * _INGREDIENT_OVERLAP_BONUS_PER_SHARED)

        reasons = list(base.reasons)
        if overlap_bonus > 0:
            reasons.append("Passt gut zu eurem bisherigen Sortiment")

        adjusted = replace(
            base,
            admin_score=base.admin_score + overlap_bonus,
            total_score=base.total_score + overlap_bonus,
            reasons=reasons,
            penalties=dict(base.penalties),
        )
        scored.append((item, adjusted))

    beverage_pool, food_pool = _split_by_domain(scored)

    # Admin-Ansicht: gelockerte Diversity-Caps (+1 ggü. Gast-Default 2 -> 3).
    beverage_admitted = apply_diversity_constraints(
        beverage_pool, max_same_subcategory=3, max_same_base_spirit=3, max_same_food_protein_family=3
    )
    beverage_admitted = ensure_required_coverage(beverage_admitted, beverage_pool, domain="beverage")

    food_admitted = apply_diversity_constraints(
        food_pool, max_same_subcategory=3, max_same_base_spirit=3, max_same_food_protein_family=3
    )
    food_admitted = ensure_required_coverage(food_admitted, food_pool, domain="food")

    combined = _dedupe_sorted(beverage_admitted + food_admitted)
    return combined[:top_n]


# ---------------------------------------------------------------------------
# §68/§69 — Fallback- / Multi-Occasion-Auflösung
# ---------------------------------------------------------------------------


def resolve_occasion_for_scoring(
    occasion_ids: list[str] | None,
    occasions: dict[str, OccasionProfile],
) -> OccasionProfile:
    """Dünner Wrapper um ``occasions.py`` (§68/§69): leere/``None``-Eingabe
    -> ``DEFAULT_OCCASION_ID`` (``casual_get_together``). Eine oder mehrere
    IDs werden an ``resolve_combined_profile`` durchgereicht, das intern
    bereits die Fallback-Logik (unbekannte IDs -> casual_get_together) sowie
    die Primär-/Sekundär-Gewichtung (0.6/0.4) für Multi-Occasion-Partys
    übernimmt."""
    if not occasion_ids:
        return get_occasion(DEFAULT_OCCASION_ID, occasions)
    return resolve_combined_profile(occasion_ids, occasions)


# ---------------------------------------------------------------------------
# §83 — Admin-Explainability
# ---------------------------------------------------------------------------


_DE_LABELS: dict[str, str] = {
    "tag_match_score": "Anlass-Fit",
    "category_score": "Kategorie-Fit",
    "context_score": "Saison/Zeit/Gruppe",
    "popularity_score": "Popularitätsprior",
    "crowd_pleaser_score": "Crowd-Pleaser",
    "operational_score": "Operational Fit",
    "dietary_score": "Diät-Abdeckung",
    "group_score": "Gruppenfeedback",
    "admin_score": "Admin-Anpassung",
    "context_fit_score": "Party-Kontext (Ort/Wetter/Infrastruktur)",
}

_EN_LABELS: dict[str, str] = {
    "tag_match_score": "Occasion fit",
    "category_score": "Category fit",
    "context_score": "Season/time/group",
    "popularity_score": "Popularity prior",
    "crowd_pleaser_score": "Crowd pleaser",
    "operational_score": "Operational fit",
    "dietary_score": "Dietary coverage",
    "group_score": "Group feedback",
    "admin_score": "Admin adjustment",
    "context_fit_score": "Party context (location/weather/infrastructure)",
}


def format_score_explanation(score: RecommendationScore, lang: str = "de") -> str:
    """§83: rendert eine kurze, für Admins lesbare Score-Aufschlüsselung
    (keine kryptischen ML-Werte ohne Erklärung). Unterstützt ``lang="de"``
    (Standard) sowie ``lang="en"``; unbekannte Keys fallen auf den
    Rohschlüssel zurück."""
    labels = _EN_LABELS if lang == "en" else _DE_LABELS
    total_label = "Total score" if lang == "en" else "Gesamt-Score"

    lines = [f"{total_label}: {score.total_score:.2f}"]

    components = {
        "tag_match_score": score.tag_match_score,
        "category_score": score.category_score,
        "context_score": score.context_score,
        "popularity_score": score.popularity_score,
        "crowd_pleaser_score": score.crowd_pleaser_score,
        "operational_score": score.operational_score,
        "dietary_score": score.dietary_score,
        "group_score": score.group_score,
        "admin_score": score.admin_score,
        "context_fit_score": score.context_fit_score,
    }
    for key, value in components.items():
        if abs(value) < 1e-9:
            continue
        label = labels.get(key, key)
        sign = "+" if value >= 0 else ""
        lines.append(f"{label:<22} {sign}{value:.2f}")

    for name, value in score.penalties.items():
        lines.append(f"{name:<22} {value:.2f}")

    if score.reasons:
        lines.append("")
        lines.append("Reasons:" if lang == "en" else "Begründungen:")
        for reason in score.reasons:
            lines.append(f"- {reason}")

    return "\n".join(lines)
