"""
Recommendation-Tag-Ableitung (§4/§5/§6/§30-50/§53-57/§81 der Recommendation-Spec).
====================================================================================

Dieses Modul enthält AUSSCHLIESSLICH datengetriebene Ableitungslogik — keine
Occasion-Scoring-Matrix (siehe Architekturgrundsatz §1/§85: "Der Anlass
definiert Eigenschaften, nicht Produktlisten"). Es produziert für jedes
CatalogItem ein vollständiges ``RecommendationMetadata`` (Tags + Score-Felder),
ausgehend von genau der Vererbungsreihenfolge aus §4:

    1. Ingredient Family Defaults      -> FAMILY_TAG_DEFAULTS
    2. DirectConsumable/Recipe Category Defaults -> CATEGORY_TAG_DEFAULTS
    3. Recipe Component Derived Tags   -> derive_tags_from_recipe()
    4. Modifier Derived Tags           -> (aktuell keine Modifier-Tags nötig)
    5. Explicit CatalogItem Tags       -> item.tags (bereits in build_catalog.py gepflegt)
    6. Explicit Recommendation Overrides -> EXPLICIT_ITEM_OVERRIDES

Spätere Ebenen ergänzen (Tags: Union) bzw. überschreiben (Scores: letzter Wert
gewinnt) frühere Werte, wie in §4 gefordert.

Öffentliche API:
    derive_recommendation_metadata(item, catalog) -> RecommendationMetadata
        Layer 1-3 (+5), OHNE EXPLICIT_ITEM_OVERRIDES. Dies ist die Fallback-
        Funktion für neue/unbekannte Items (§80 letzter Satz), wird auch von
        party_engine/catalog.py als Defensive-Fallback beim Laden genutzt.

    apply_recommendation_metadata(item, catalog) -> RecommendationMetadata
        derive_recommendation_metadata() + Layer 6 (EXPLICIT_ITEM_OVERRIDES).
        Dies ist der eigentliche Einstiegspunkt, der von build_catalog.py für
        JEDES Ingredient/DirectConsumable/Recipe aufgerufen wird.
"""

from __future__ import annotations

from party_engine.recommendation_domain import RecommendationMetadata

# ---------------------------------------------------------------------------
# Kleine Hilfsfunktionen
# ---------------------------------------------------------------------------


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _resolve_diet_and_alcohol(item, catalog):
    """Liefert (is_vegan, is_vegetarian, is_meat, is_fish, contains_alcohol,
    abv, contains_caffeine) einheitlich für Ingredient/DirectConsumable/Recipe.

    DirectConsumable besitzt selbst keine is_vegan/is_vegetarian-Felder -> wird
    über das referenzierte Ingredient aufgelöst (§81: "recipe components,
    ingredient families" werden ausgewertet, auch für Direktkonsum-Getränke).
    """
    cls_name = type(item).__name__

    if cls_name == "Ingredient":
        return (
            item.is_vegan,
            item.is_vegetarian,
            item.is_meat,
            item.is_fish,
            item.contains_alcohol,
            item.abv,
            item.contains_caffeine,
        )

    if cls_name == "Recipe":
        return (
            item.is_vegan,
            item.is_vegetarian,
            False,  # wird separat über Komponenten-Familien bestimmt
            False,
            item.contains_alcohol,
            0.0,
            False,  # wird separat über derive_tags_from_recipe bestimmt
        )

    if cls_name == "DirectConsumable":
        ing = catalog.ingredients.get(item.ingredient_id) if catalog else None
        is_vegan = ing.is_vegan if ing else True
        is_vegetarian = ing.is_vegetarian if ing else True
        is_meat = ing.is_meat if ing else False
        is_fish = ing.is_fish if ing else False
        contains_alcohol = bool(item.abv and item.abv > 0.0) or (ing.contains_alcohol if ing else False)
        return (
            is_vegan,
            is_vegetarian,
            is_meat,
            is_fish,
            contains_alcohol,
            item.abv,
            item.contains_caffeine,
        )

    # Unbekannter Typ -> neutrale Defaults
    return (False, True, False, False, False, 0.0, False)


# ---------------------------------------------------------------------------
# LAYER 1: Ingredient Family Defaults (§30-35)
# ---------------------------------------------------------------------------
# tags = Basis-Tag-Set für die Familie. Wird v.a. für Ingredient-Objekte
# selbst verwendet; bei DirectConsumables kommt zusätzlich Layer 2
# (CATEGORY_TAG_DEFAULTS, meist deckungsgleich mit der Familie) zum Tragen.

FAMILY_TAG_DEFAULTS: dict[str, set[str]] = {
    "spirit": {"spirit", "alcoholic", "strong_alcohol", "evening", "bar_style"},
    "liqueur": {"spirit", "alcoholic", "bar_style", "evening", "sweet"},
    "fortified_wine": {"alcoholic", "bar_style", "evening", "elegant", "bitter"},
    "wine": {"wine", "alcoholic", "elegant", "evening"},
    "sparkling_wine": {"sparkling", "wine", "alcoholic", "celebratory", "festive"},
    "beer": {"beer", "alcoholic", "casual", "social", "party_classic", "crowd_pleaser", "easy_service"},
    "softdrink": {"softdrink", "non_alcoholic", "crowd_pleaser", "easy_service", "all_day"},
    "energy": {"energy", "caffeinated", "non_alcoholic", "late_night", "house_party"},
    "juice": {"juice", "non_alcoholic", "fruity", "refreshing", "daytime", "brunch"},
    "syrup": {"sweet", "mixer"},
    "coffee": {"coffee", "caffeinated", "non_alcoholic", "hot_drink", "morning"},
    "dairy": {"creamy"},
    "fruit": {"fruit", "fresh", "light_food", "vegan_friendly", "vegetarian_friendly"},
    "citrus": {"fruit", "fresh", "citrus"},
    "herb": {"fresh", "herbal"},
    "meat_beef": {"meat", "beef", "meat_eater", "savory"},
    "meat_pork": {"meat", "pork", "meat_eater", "savory"},
    "meat_lamb": {"meat", "meat_eater", "savory"},
    "poultry": {"meat", "poultry", "meat_eater", "savory"},
    "fish": {"fish", "meat_eater", "pescatarian_friendly", "light_food"},
    "veg_protein": {"vegetarian", "vegetarian_friendly", "cheese"},
    "vegan_protein": {"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"},
    "bread": {"bread", "side", "shareable", "buffet_friendly"},
    "potato": {"potato", "side", "vegan_friendly"},
    "pasta": {"pasta", "side", "filling"},
    "grain": {"grain", "side", "vegan_friendly"},
    "salad_green": {"vegetable", "fresh", "salad", "light_food", "vegan_friendly"},
    "vegetable": {"vegetable", "fresh", "vegan_friendly", "vegetarian_friendly"},
    "cheese": {"cheese", "savory", "vegetarian_friendly"},
    "sauce": {"sauce", "dip", "supporting_item", "shareable"},
    "spice": {"savory", "supporting_item"},
    "snack": {"snack", "casual", "shareable", "easy_service", "party_classic"},
    "dessert_ing": {"dessert", "sweet_food"},
    "ice": {"supporting_item"},
    "water": {"water", "non_alcoholic", "hydrating", "refreshing", "crowd_pleaser", "all_day", "easy_service", "large_group_friendly"},
    "oil": {"supporting_item"},
    "bar_misc": {"bar_style", "supporting_item"},
    "bitters": {"bitter", "bar_style", "supporting_item"},
    "plant_milk": {"creamy", "vegan_friendly", "vegan"},
}

_FAMILY_FALLBACK_TAGS: set[str] = {"casual", "shareable"}


# ---------------------------------------------------------------------------
# LAYER 2: DirectConsumable/Recipe Category Defaults (§30-50)
# ---------------------------------------------------------------------------

CATEGORY_TAG_DEFAULTS: dict[str, set[str]] = {
    # --- Beverage DirectConsumable categories -----------------------------
    "water": {"water", "non_alcoholic", "hydrating", "refreshing", "crowd_pleaser", "all_day", "easy_service", "large_group_friendly"},
    "beer": {"beer", "alcoholic", "casual", "social", "party_classic", "crowd_pleaser", "easy_service", "outdoor", "grill", "sports"},
    "wine": {"wine", "alcoholic", "elegant", "evening"},
    "sparkling_wine": {"sparkling", "wine", "alcoholic", "celebratory", "festive", "brunch"},
    "softdrink": {"softdrink", "non_alcoholic", "crowd_pleaser", "party_classic", "easy_service", "all_day"},
    "juice": {"juice", "non_alcoholic", "fruity", "refreshing", "daytime", "brunch", "summer"},
    "energy": {"energy", "caffeinated", "non_alcoholic", "late_night", "house_party", "festival"},
    "spirit": {"spirit", "alcoholic", "strong_alcohol", "evening", "bar_style"},
    "liqueur": {"spirit", "alcoholic", "bar_style", "evening"},
    "fortified_wine": {"alcoholic", "bar_style", "evening", "elegant"},
    "coffee": {"coffee", "caffeinated", "non_alcoholic", "hot_drink", "morning", "brunch"},
    # --- Food-adjacent DirectConsumable categories -------------------------
    "bread": {"bread", "side", "shareable", "buffet_friendly", "grill"},
    "cheese": {"cheese", "snack", "shareable", "fingerfood_food", "vegetarian_friendly"},
    "vegetable": {"vegetable", "snack", "fresh", "shareable", "vegan_friendly", "vegetarian_friendly"},
    "fruit": {"fruit", "fresh", "dessert", "summer", "light_food", "high_dietary_coverage", "vegan_friendly", "vegetarian_friendly"},
    "snack": {"snack", "casual", "shareable", "easy_service", "party_classic"},
    "sauce": {"dip", "sauce", "supporting_item", "shareable"},
    # --- Recipe categories ---------------------------------------------------
    "burger": {"main", "handheld", "casual", "crowd_pleaser", "party_classic", "filling"},
    "grill": {"main", "grilled_food", "grill", "outdoor"},
    "veg_grill": {"main", "vegetarian", "vegetarian_friendly", "grill", "grilled_food", "outdoor"},
    "salad": {"side", "salad", "shareable", "buffet_friendly"},
    "side": {"side", "shareable", "buffet_friendly", "grill"},
    "fingerfood": {"fingerfood_food", "fingerfood", "shareable", "self_service", "party_classic", "easy_service"},
    "dessert": {"dessert", "sweet_food", "shareable"},
    "main_dish": {"main", "comfort_food", "filling", "indoor"},
    "softdrink_mix": {"softdrink", "non_alcoholic", "casual", "crowd_pleaser", "grill", "sports"},
    "cocktail_vodka": {"cocktail", "spirit", "alcoholic", "evening", "bar_style"},
    "cocktail_gin": {"cocktail", "spirit", "alcoholic", "evening", "bar_style"},
    "cocktail_rum": {"cocktail", "spirit", "alcoholic", "evening", "bar_style"},
    "cocktail_tequila": {"cocktail", "spirit", "alcoholic", "evening", "bar_style"},
    "cocktail_whiskey": {"cocktail", "spirit", "alcoholic", "evening", "bar_style"},
    "cocktail_brandy": {"cocktail", "spirit", "alcoholic", "evening", "bar_style"},
    "cocktail_spritz": {"cocktail", "sparkling", "refreshing", "social", "garden", "summer", "daytime", "outdoor", "easy_service", "trendy"},
    "cocktail_longdrink": {"longdrink", "cocktail", "social", "easy_service", "evening", "casual", "party_classic"},
    "cocktail_complex": {"cocktail", "strong_alcohol", "bar_style", "special_interest", "late_night"},
}

_CATEGORY_FALLBACK_TAGS: set[str] = {"casual", "shareable"}


# ---------------------------------------------------------------------------
# LAYER 3/4: Recipe-Component-Derived Tags (§5/§6)
# ---------------------------------------------------------------------------

_CITRUS_INGREDIENT_IDS: set[str] = {"lime_juice_fresh", "lemon_juice_fresh", "grapefruit_juice", "lime_cordial", "lime", "lemon", "grapefruit"}
_TROPICAL_INGREDIENT_IDS: set[str] = {
    "pineapple_juice", "pineapple", "coconut_cream", "coconut_milk",
    "passionfruit_juice", "passionfruit_liqueur", "passionfruit_syrup", "passionfruit",
}
_CREAMY_INGREDIENT_IDS: set[str] = {"cream", "coconut_cream", "baileys"}
_SPARKLING_WINE_INGREDIENT_IDS: set[str] = {"prosecco", "sekt", "champagne", "cremant", "cava", "franciacorta"}

# Reine Spirituosen/Liköre ab dieser ABV zählen für die "> 2 Spirituosen"-Regel (§5).
_STRONG_SPIRIT_ABV_THRESHOLD = 15.0


def derive_tags_from_recipe(recipe, ingredients_by_id: dict) -> set[str]:
    """Leitet Tags aus den Recipe-Komponenten ab (§5 Drink-Rezepte, §6 Food-Rezepte).

    ``ingredients_by_id`` ist ein dict[str, Ingredient] (oder das äquivalente
    Rohdict aus build_catalog.py mit denselben Feldnamen).
    """
    tags: set[str] = set()

    core_components = [c for c in recipe.components if not _get(c, "optional", False)]
    core_ids = [_get(c, "ingredient_id") for c in core_components]
    core_ings = [ingredients_by_id[i] for i in core_ids if i in ingredients_by_id]

    if not core_ings:
        return tags

    # --- Alkohol -----------------------------------------------------------
    contains_alcohol = _get(recipe, "contains_alcohol", None)
    if contains_alcohol is None:
        contains_alcohol = any(_get(i, "contains_alcohol", False) for i in core_ings)
    tags.add("alcoholic" if contains_alcohol else "non_alcoholic")

    # --- Energy Drink --------------------------------------------------------
    if any(_get(i, "family", "") == "energy" for i in core_ings):
        tags.update({"energy", "caffeinated"})

    # --- Kaffee ----------------------------------------------------------
    if any(_get(i, "family", "") == "coffee" for i in core_ings):
        tags.update({"coffee", "caffeinated"})

    # --- Prosecco/Sekt/Champagner -----------------------------------------
    if any(cid in _SPARKLING_WINE_INGREDIENT_IDS for cid in core_ids):
        tags.update({"sparkling", "celebratory"})

    # --- Mehr als zwei Spirituosen -----------------------------------------
    strong_spirits = [
        i for i in core_ings
        if _get(i, "contains_alcohol", False) and _get(i, "abv", 0.0) >= _STRONG_SPIRIT_ABV_THRESHOLD
    ]
    if len(strong_spirits) > 2:
        tags.add("strong_alcohol")

    # --- Fruchtsäfte/Pürees (fruity) ----------------------------------------
    liquid_components = [c for c in core_components if _get(c, "unit", "l") == "l"]
    total_l = sum(_get(c, "amount", 0.0) for c in liquid_components)
    juice_l = sum(
        _get(c, "amount", 0.0) for c in liquid_components
        if ingredients_by_id.get(_get(c, "ingredient_id"), {}) and _get(ingredients_by_id.get(_get(c, "ingredient_id")), "family", "") == "juice"
    )
    if total_l > 0 and (juice_l / total_l) >= 0.35:
        tags.add("fruity")

    # --- Tropical --------------------------------------------------------
    if any(cid in _TROPICAL_INGREDIENT_IDS for cid in core_ids):
        tags.update({"tropical", "fruity"})

    # --- Citrus/Refreshing -------------------------------------------------
    if any(cid in _CITRUS_INGREDIENT_IDS for cid in core_ids):
        tags.update({"citrus", "refreshing"})

    # --- Creamy ------------------------------------------------------------
    if any(cid in _CREAMY_INGREDIENT_IDS for cid in core_ids):
        tags.add("creamy")

    # --- Food: Fleisch-/Fisch-Familien --------------------------------------
    families = {_get(i, "family", "") for i in core_ings}
    if "meat_beef" in families:
        tags.update({"meat", "beef", "meat_eater"})
    if "meat_pork" in families:
        tags.update({"meat", "pork", "meat_eater"})
    if "meat_lamb" in families:
        tags.update({"meat", "meat_eater"})
    if "poultry" in families:
        tags.update({"meat", "poultry", "meat_eater"})
    if "fish" in families:
        tags.update({"fish", "meat_eater"})
        if not ({"meat_beef", "meat_pork", "meat_lamb", "poultry"} & families):
            tags.add("pescatarian_friendly")

    # --- Food: vegan/vegetarian ------------------------------------------
    is_vegan = _get(recipe, "is_vegan", None)
    is_vegetarian = _get(recipe, "is_vegetarian", None)
    if is_vegan is None:
        is_vegan = all(_get(i, "is_vegan", False) for i in core_ings)
    if is_vegetarian is None:
        is_vegetarian = all(_get(i, "is_vegetarian", True) for i in core_ings)
    if is_vegan:
        tags.update({"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"})
    elif is_vegetarian:
        tags.update({"vegetarian", "vegetarian_friendly"})

    # --- Ice-Profile -> Service-Tags (§30 SERVICE_OPERATION_TAGS) -----------
    ice_profile = _get(recipe, "ice_profile", "")
    if ice_profile in ("shaken", "stirred", "blended"):
        tags.add(ice_profile)

    return tags


def _get(obj, name, default=None):
    """Liest ein Attribut/Key sowohl von dataclass-Instanzen als auch von
    Rohdicts (build_catalog.py arbeitet z.T. noch mit dicts vor der finalen
    Dataclass-Konstruktion)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# LAYER 6: EXPLICIT_ITEM_OVERRIDES (§8-50, hand-kuratierte charakteristische Items)
# ---------------------------------------------------------------------------
# Struktur je Eintrag: {"tags": set[str], "scores": dict[str, float],
#                        "occasion_affinity_overrides": dict[str, float]}
# Tags werden mit den abgeleiteten Tags vereinigt (Union), Scores und
# Occasion-Overrides überschreiben/ergänzen die abgeleiteten Werte (§4).


def _override(ids, tags=None, scores=None, bonus=None, bonus_occasions=None,
              penalty=None, penalty_occasions=None) -> dict:
    """Baut Override-Einträge für eine Liste von Item-IDs, die dieselbe
    charakteristische Tag-/Score-/Occasion-Gruppe teilen (z.B. eine Cocktail-
    Familie oder eine Grill-Subfamilie aus §36-50)."""
    entry = {}
    if tags:
        entry["tags"] = set(tags)
    if scores:
        entry["scores"] = dict(scores)
    oao = {}
    if bonus is not None and bonus_occasions:
        for occ in bonus_occasions:
            oao[occ] = bonus
    if penalty is not None and penalty_occasions:
        for occ in penalty_occasions:
            oao[occ] = penalty
    if oao:
        entry["occasion_affinity_overrides"] = oao
    return {iid: dict(entry) for iid in ids}


def _merge_overrides(*dicts) -> dict:
    result: dict[str, dict] = {}
    for d in dicts:
        for iid, entry in d.items():
            if iid not in result:
                result[iid] = {"tags": set(), "scores": {}, "occasion_affinity_overrides": {}}
            if "tags" in entry:
                result[iid]["tags"] |= entry["tags"]
            if "scores" in entry:
                result[iid]["scores"].update(entry["scores"])
            if "occasion_affinity_overrides" in entry:
                result[iid]["occasion_affinity_overrides"].update(entry["occasion_affinity_overrides"])
    return result


def _build_explicit_overrides() -> dict:
    groups = []

    # ======================================================== WATER (§30)
    groups.append(_override(
        ["water", "mineral_water_still", "mineral_water_medium", "mineral_water_sparkling",
         "tafelwasser"],
        tags={"water", "non_alcoholic", "hydrating", "refreshing", "crowd_pleaser",
              "all_day", "easy_service", "large_group_friendly", "high_dietary_coverage"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.6, "service_complexity": 0.05,
                "purchase_complexity": 0.05, "dietary_coverage": 1.0},
    ))

    # ============================================================ BEER (§30)
    groups.append(_override(
        ["beer_pils", "beer_helles", "beer_export", "beer_kellerbier", "beer_zwickel",
         "beer_maerzen", "beer_festbier", "beer_koelsch", "beer_altbier", "beer_lager"],
        tags={"beer", "alcoholic", "casual", "social", "party_classic", "crowd_pleaser",
              "easy_service", "outdoor", "grill", "sports"},
        scores={"popularity_prior": 0.82, "crowd_pleaser_score": 0.85, "service_complexity": 0.05,
                "prep_complexity": 0.05},
    ))
    groups.append(_override(
        ["beer_hefeweizen", "beer_kristallweizen", "beer_dunkelweizen", "beer_dunkel",
         "beer_schwarzbier", "beer_bockbier", "beer_doppelbock"],
        tags={"beer", "alcoholic", "traditional", "rich", "winter", "evening"},
        scores={"popularity_prior": 0.62, "crowd_pleaser_score": 0.6, "service_complexity": 0.05},
    ))
    groups.append(_override(
        ["beer_pale_ale", "beer_ipa", "beer_double_ipa", "beer_session_ipa", "beer_craft_generic", "beer_sour"],
        tags={"beer", "alcoholic", "modern", "special_interest", "social", "premium"},
        scores={"popularity_prior": 0.42, "crowd_pleaser_score": 0.45, "premium_score": 0.65,
                "novelty_score": 0.7, "service_complexity": 0.08},
    ))
    groups.append(_override(
        ["beer_stout", "beer_porter"],
        tags={"beer", "alcoholic", "rich", "winter", "evening", "special_interest"},
        scores={"popularity_prior": 0.3, "crowd_pleaser_score": 0.35, "premium_score": 0.6,
                "service_complexity": 0.08},
    ))
    groups.append(_override(
        ["beer_pils_alcohol_free", "beer_helles_alcohol_free", "beer_weizen_alcohol_free"],
        tags={"beer", "non_alcoholic", "refreshing", "casual", "grill", "sports", "high_dietary_coverage"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.65, "service_complexity": 0.05,
                "dietary_coverage": 0.95},
    ))

    # ============================================================ WINE (§31)
    groups.append(_override(
        ["white_wine", "grauburgunder", "weissburgunder", "riesling", "chardonnay",
         "sauvignon_blanc", "silvaner", "mueller_thurgau", "gruener_veltliner", "gewuerztraminer"],
        tags={"wine", "alcoholic", "refreshing", "elegant", "garden", "summer"},
        scores={"popularity_prior": 0.62, "crowd_pleaser_score": 0.6, "premium_score": 0.55,
                "service_complexity": 0.08},
    ))
    groups.append(_override(
        ["rose_wine"],
        tags={"wine", "alcoholic", "summer", "garden", "refreshing", "daytime", "social"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.6, "service_complexity": 0.08},
    ))
    groups.append(_override(
        ["red_wine", "primitivo", "merlot", "cabernet_sauvignon", "pinot_noir", "spaetburgunder",
         "tempranillo", "syrah", "shiraz", "rioja", "chianti", "lambrusco"],
        tags={"wine", "alcoholic", "evening", "premium", "winter"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.58, "premium_score": 0.6,
                "service_complexity": 0.08},
    ))
    groups.append(_override(
        ["wine_alcohol_free"],
        tags={"wine", "non_alcoholic", "elegant", "high_dietary_coverage"},
        scores={"dietary_coverage": 0.95, "service_complexity": 0.08},
    ))

    # ===================================================== SPARKLING (§31)
    groups.append(_override(
        ["prosecco", "sekt", "champagne", "cremant", "cava", "franciacorta"],
        tags={"sparkling", "wine", "alcoholic", "celebratory", "festive", "brunch"},
        scores={"popularity_prior": 0.65, "crowd_pleaser_score": 0.65, "premium_score": 0.6,
                "service_complexity": 0.08},
        bonus=0.15, bonus_occasions=["wedding", "new_years_eve", "birthday", "brunch"],
    ))
    groups.append(_override(
        ["champagne"], tags={"premium"}, scores={"premium_score": 0.9, "popularity_prior": 0.5},
    ))
    groups.append(_override(
        ["sparkling_wine_alcohol_free"],
        tags={"sparkling", "wine", "non_alcoholic", "celebratory", "high_dietary_coverage"},
        scores={"dietary_coverage": 0.95},
    ))

    # =================================================== SOFTDRINK (§32)
    groups.append(_override(
        ["cola", "cola_zero", "cola_light", "fanta_orange", "fanta_lemon", "sprite", "seven_up"],
        tags={"softdrink", "non_alcoholic", "crowd_pleaser", "party_classic", "easy_service", "all_day"},
        scores={"popularity_prior": 0.8, "crowd_pleaser_score": 0.85, "service_complexity": 0.05,
                "dietary_coverage": 1.0},
    ))
    groups.append(_override(
        ["lemonade_orange", "lemonade_lemon", "wild_berry_soda", "grapefruit_soda",
         "fassbrause", "root_beer", "cream_soda"],
        tags={"softdrink", "non_alcoholic", "fruity", "refreshing", "summer"},
        scores={"popularity_prior": 0.5, "crowd_pleaser_score": 0.55, "service_complexity": 0.05},
    ))
    groups.append(_override(
        ["tonic_water", "bitter_lemon", "ginger_ale", "ginger_beer", "soda_water"],
        tags={"non_alcoholic", "mixer", "refreshing", "bar_style"},
        scores={"popularity_prior": 0.4, "crowd_pleaser_score": 0.4, "service_complexity": 0.05},
    ))
    groups.append(_override(
        ["club_mate", "mate_lemonade"],
        tags={"softdrink", "non_alcoholic", "caffeinated", "modern", "special_interest"},
        scores={"popularity_prior": 0.35, "crowd_pleaser_score": 0.4},
    ))
    groups.append(_override(
        ["malt_beer"], tags={"softdrink", "non_alcoholic", "traditional"},
    ))

    # ======================================================== JUICE (§34)
    groups.append(_override(
        ["orange_juice", "apple_juice", "pineapple_juice", "cranberry_juice", "cherry_juice",
         "banana_juice", "passionfruit_juice", "mango_juice", "peach_juice", "grapefruit_juice",
         "grape_juice", "currant_juice", "multivitamin_juice", "rhubarb_juice"],
        tags={"juice", "non_alcoholic", "fruity", "refreshing", "daytime", "brunch", "summer"},
        scores={"popularity_prior": 0.55, "crowd_pleaser_score": 0.55, "service_complexity": 0.05,
                "dietary_coverage": 1.0},
    ))
    groups.append(_override(
        ["tomato_juice"],
        tags={"juice", "non_alcoholic", "savory", "brunch"},
    ))
    groups.append(_override(
        ["apple_juice"],
        tags={"hydrating", "light_drink", "outdoor"},  # Schorlen-artige Zusatztags (§34)
    ))

    # ======================================================= SPIRIT (§35)
    groups.append(_override(
        ["vodka", "vodka_vanilla", "gin", "gin_london_dry", "gin_pink", "rum_white", "rum_dark",
         "rum_aged", "rum_spiced", "rum_overproof", "bourbon", "rye_whiskey", "scotch_whisky",
         "irish_whiskey", "tennessee_whiskey", "canadian_whisky", "tequila_blanco",
         "tequila_reposado", "tequila_anejo", "mezcal", "cachaca", "pisco", "cognac", "brandy",
         "calvados", "grappa", "korn", "doppelkorn", "obstler", "williams_birne", "kirschwasser",
         "ouzo", "raki", "aquavit", "absinthe"],
        tags={"spirit", "alcoholic", "strong_alcohol", "evening", "bar_style"},
        scores={"popularity_prior": 0.35, "crowd_pleaser_score": 0.35, "service_complexity": 0.1,
                "purchase_complexity": 0.35},
    ))

    # ================================================== FORTIFIED WINE
    groups.append(_override(
        ["dry_vermouth", "sweet_vermouth", "lillet_blanc", "sherry"],
        tags={"alcoholic", "bar_style", "evening", "elegant", "bitter"},
        scores={"popularity_prior": 0.25, "crowd_pleaser_score": 0.3},
    ))
    groups.append(_override(
        ["port_wine"],
        tags={"alcoholic", "evening", "elegant", "premium", "winter", "sweet"},
        scores={"popularity_prior": 0.25, "premium_score": 0.7},
    ))

    # ==================================================== LIQUEUR (§35)
    groups.append(_override(
        ["aperol", "campari", "cynar", "fernet", "ramazzotti", "averna", "amaro_generic"],
        tags={"spirit", "alcoholic", "bitter", "bar_style", "evening"},
        scores={"popularity_prior": 0.4, "crowd_pleaser_score": 0.4},
    ))
    groups.append(_override(
        ["jaegermeister", "sambuca"],
        tags={"spirit", "alcoholic", "herbal", "bar_style", "evening", "strong_alcohol", "shot"},
        scores={"popularity_prior": 0.45, "crowd_pleaser_score": 0.4},
        bonus=0.1, bonus_occasions=["house_party", "bachelor_party"],
    ))
    groups.append(_override(
        ["limoncello", "amaretto", "baileys", "coffee_liqueur", "triple_sec", "grand_marnier",
         "peach_liqueur", "maraschino", "blackberry_liqueur", "raspberry_liqueur",
         "passionfruit_liqueur", "elderflower_liqueur", "creme_de_cassis", "blue_curacao",
         "malibu", "drambuie", "creme_de_cacao", "melon_liqueur", "cherry_liqueur", "falernum",
         "licor_43", "chartreuse_green", "chartreuse_yellow", "galliano"],
        tags={"spirit", "alcoholic", "sweet", "bar_style", "evening"},
        scores={"popularity_prior": 0.3, "crowd_pleaser_score": 0.3},
    ))

    # ======================================================== COFFEE
    groups.append(_override(
        ["filter_coffee", "espresso", "cold_brew"],
        tags={"coffee", "caffeinated", "non_alcoholic", "hot_drink", "morning", "brunch"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.6, "service_complexity": 0.15},
    ))

    # ================================================== ENERGY DRINKS
    groups.append(_override(
        ["energy_drink_generic", "energy_drink_sugarfree", "energy_drink_tropical"],
        tags={"energy", "caffeinated", "non_alcoholic", "late_night", "house_party", "festival"},
        scores={"popularity_prior": 0.4, "crowd_pleaser_score": 0.35, "service_complexity": 0.05},
    ))

    # ======================================================= BREAD (§47)
    groups.append(_override(
        ["baguette", "ciabatta", "flatbread"],
        tags={"bread", "side", "shareable", "buffet_friendly", "grill"},
        scores={"popularity_prior": 0.65, "crowd_pleaser_score": 0.7, "service_complexity": 0.05},
    ))
    groups.append(_override(
        ["pretzel", "laugenstange"],
        tags={"bread", "comfort_food", "party_classic", "traditional"},
        scores={"popularity_prior": 0.55, "crowd_pleaser_score": 0.6},
    ))
    groups.append(_override(
        ["bread_roll", "white_bread", "toast_bread"],
        tags={"bread", "side", "shareable"},
    ))
    groups.append(_override(
        ["burger_bun", "hotdog_bun"],
        tags={"bread", "supporting_item"},
    ))

    # ======================================================== SNACKS (§48)
    groups.append(_override(
        ["potato_chips", "paprika_chips", "salt_vinegar_chips", "tortilla_chips",
         "pretzel_sticks", "crackers", "cheese_crackers", "rice_cakes", "grissini"],
        tags={"snack", "casual", "shareable", "easy_service", "party_classic"},
        scores={"popularity_prior": 0.75, "crowd_pleaser_score": 0.75, "service_complexity": 0.02,
                "prep_complexity": 0.02},
    ))
    groups.append(_override(
        ["popcorn_salty", "popcorn_sweet"],
        tags={"snack", "movie", "game", "low_mess", "casual", "shareable"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.65},
    ))
    groups.append(_override(
        ["peanuts", "cashews", "almonds", "nut_mix"],
        tags={"snack", "shareable", "premium"},
        scores={"premium_score": 0.55, "popularity_prior": 0.45},
    ))
    groups.append(_override(
        ["mini_salami", "beef_jerky", "snack_sausages"],
        tags={"snack", "meat", "meat_eater", "shareable"},
    ))
    groups.append(_override(
        ["grapes_snack"],
        tags={"fruit", "fresh", "snack", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"},
    ))
    groups.append(_override(
        ["olives"],
        tags={"vegetable", "snack", "fresh", "party_classic", "fingerfood_food", "vegan_friendly"},
    ))
    groups.append(_override(
        ["gemuesesticks"],
        tags={"vegetable", "snack", "fresh", "light_food", "vegan_friendly", "vegetarian_friendly"},
    ))
    groups.append(_override(
        ["watermelon", "strawberry", "mixed_berries"],
        tags={"fruit", "fresh", "dessert", "summer", "light_food", "high_dietary_coverage"},
        scores={"popularity_prior": 0.55, "crowd_pleaser_score": 0.6},
    ))
    groups.append(_override(
        ["cheese_cubes"],
        tags={"cheese", "snack", "fingerfood_food", "shareable", "vegetarian_friendly"},
    ))

    # ======================================================= SAUCES/DIPS (§49)
    groups.append(_override(
        ["guacamole", "salsa_mild", "salsa_hot"],
        tags={"dip", "sauce", "fresh", "party", "nachos", "taco", "shareable", "vegan_friendly"},
    ))
    groups.append(_override(
        ["hummus"],
        tags={"dip", "sauce", "fresh", "vegan_friendly", "vegetarian_friendly", "shareable"},
    ))
    groups.append(_override(
        ["tzatziki"],
        tags={"dip", "sauce", "grill", "summer", "fresh", "vegetarian_friendly"},
    ))
    groups.append(_override(
        ["bbq_sauce"],
        tags={"sauce", "grill", "bbq", "supporting_item"},
    ))
    groups.append(_override(
        ["sriracha", "hot_sauce", "tabasco", "sweet_chili_sauce"],
        tags={"sauce", "spicy_food", "supporting_item"},
    ))
    groups.append(_override(
        ["ketchup", "mayonnaise", "mustard", "sweet_mustard", "burger_sauce", "cocktail_sauce",
         "remoulade", "honey_mustard_sauce"],
        tags={"sauce", "dip", "supporting_item", "shareable"},
    ))
    groups.append(_override(
        ["curry_sauce", "teriyaki_sauce", "cheese_sauce", "chili_cheese_sauce",
         "herb_butter", "garlic_butter", "aioli", "garlic_dip", "herb_dip", "sour_cream"],
        tags={"sauce", "dip", "supporting_item", "shareable"},
    ))

    # ======================================================= COCKTAILS (§36)
    groups.append(_override(
        ["aperol_spritz", "campari_spritz", "limoncello_spritz", "hugo", "lillet_wild_berry",
         "negroni_sbagliato", "americano"],
        tags={"cocktail", "sparkling", "refreshing", "social", "garden", "summer", "daytime",
              "outdoor", "easy_service", "trendy"},
        scores={"popularity_prior": 0.78, "crowd_pleaser_score": 0.65, "service_complexity": 0.25,
                "prep_complexity": 0.2, "premium_score": 0.4},
        bonus=0.15, bonus_occasions=["garden_party", "summer_party", "daydrinking", "pool_party", "birthday", "wedding"],
    ))
    groups.append(_override(
        ["mimosa", "bellini", "kir", "kir_royal", "rossini", "sgroppino"],
        tags={"cocktail", "sparkling", "celebratory", "brunch", "daytime", "fruity"},
        scores={"popularity_prior": 0.45, "service_complexity": 0.2},
        bonus=0.15, bonus_occasions=["brunch", "wedding"],
    ))
    groups.append(_override(
        ["sangria_rot", "sangria_weiss", "tinto_de_verano"],
        tags={"cocktail", "wine", "refreshing", "social", "summer", "sharing", "fruity"},
        scores={"popularity_prior": 0.45, "batchability": 0.75, "large_group_score": 0.7},
        bonus=0.1, bonus_occasions=["garden_party", "summer_party"],
    ))
    groups.append(_override(
        ["moscow_mule", "mexican_mule", "whiskey_ginger", "gin_tonic", "vodka_tonic",
         "vodka_lemon", "rum_cola", "cuba_libre", "whiskey_cola"],
        tags={"longdrink", "cocktail", "social", "easy_service", "evening", "casual", "party_classic"},
        scores={"popularity_prior": 0.65, "crowd_pleaser_score": 0.6, "service_complexity": 0.2},
        bonus=0.12, bonus_occasions=["house_party", "birthday", "garden_party", "cocktail_party", "casual_get_together"],
    ))
    groups.append(_override(
        ["espresso_martini", "dry_martini", "vodka_martini", "porn_star_martini",
         "french_martini", "vesper", "cosmopolitan"],
        tags={"cocktail", "evening", "premium", "bar_style", "trendy"},
        scores={"popularity_prior": 0.55, "premium_score": 0.75, "service_complexity": 0.55},
        bonus=0.15, bonus_occasions=["cocktail_party"],
    ))
    groups.append(_override(
        ["espresso_martini"],
        tags={"coffee", "caffeinated", "late_night", "trendy", "premium"},
        scores={"service_complexity": 0.65, "popularity_prior": 0.7},
        bonus=0.1, bonus_occasions=["bachelor_party"],
    ))
    groups.append(_override(
        ["porn_star_martini"],
        tags={"fruity", "tropical", "trendy", "celebratory"},
        scores={"popularity_prior": 0.65},
    ))
    groups.append(_override(
        ["dry_martini", "vodka_martini"],
        tags={"dry", "elegant", "premium", "special_interest"},
        scores={"popularity_prior": 0.35},
    ))
    groups.append(_override(
        ["whiskey_sour", "amaretto_sour", "pisco_sour", "margarita", "daiquiri", "bees_knees"],
        tags={"cocktail", "citrus", "refreshing", "bar_style", "evening"},
        scores={"popularity_prior": 0.55, "service_complexity": 0.45},
        bonus=0.12, bonus_occasions=["cocktail_party", "birthday"],
    ))
    groups.append(_override(
        ["margarita"],
        tags={"party_classic", "trendy"},
        scores={"popularity_prior": 0.78, "crowd_pleaser_score": 0.65},
        bonus=0.1, bonus_occasions=["summer_party"],
    ))
    groups.append(_override(
        ["pina_colada", "mai_tai", "zombie", "hurricane", "painkiller", "bahama_mama",
         "blue_hawaiian", "rum_punch"],
        tags={"cocktail", "tropical", "fruity", "summer", "party", "special_interest"},
        scores={"popularity_prior": 0.5, "service_complexity": 0.45},
        bonus=0.15, bonus_occasions=["pool_party", "summer_party"],
    ))
    groups.append(_override(
        ["zombie"],
        tags={"strong_alcohol"},
        scores={"service_complexity": 0.75},
    ))
    groups.append(_override(
        ["negroni", "old_fashioned", "manhattan", "boulevardier", "sazerac", "godfather"],
        tags={"cocktail", "strong_alcohol", "premium", "evening", "bar_style", "special_interest"},
        scores={"popularity_prior": 0.4, "premium_score": 0.75, "service_complexity": 0.35,
                "crowd_pleaser_score": 0.35},
        bonus=0.12, bonus_occasions=["cocktail_party", "dinner_party", "winter_party"],
        penalty=-0.1, penalty_occasions=["daydrinking", "pool_party", "family_party"],
    ))
    groups.append(_override(
        ["mojito", "paloma", "tom_collins", "gin_fizz", "bramble", "gin_basil_smash", "caipirinha"],
        tags={"cocktail", "refreshing", "citrus", "summer", "social"},
        scores={"popularity_prior": 0.62, "service_complexity": 0.55},
        bonus=0.12, bonus_occasions=["summer_party", "garden_party", "pool_party", "cocktail_party", "birthday"],
    ))
    groups.append(_override(
        ["vodka_red_bull", "jaegerbomb", "jaegermeister_energy"],
        tags={"energy", "caffeinated", "alcoholic", "late_night", "house_party"},
        scores={"crowd_pleaser_score": 0.4, "popularity_prior": 0.45},
        penalty=-0.15, penalty_occasions=["family_party", "brunch", "dinner_party", "wedding"],
    ))
    groups.append(_override(
        ["long_island_iced_tea", "tokyo_iced_tea", "adios_motherfucker", "tiki_punch"],
        tags={"cocktail", "strong_alcohol", "special_interest"},
        scores={"service_complexity": 0.6, "popularity_prior": 0.45},
    ))
    groups.append(_override(
        ["ramos_gin_fizz"],
        tags={"cocktail", "special_interest", "premium"},
        scores={"service_complexity": 0.95, "popularity_prior": 0.15, "premium_score": 0.8},
    ))
    groups.append(_override(
        ["sazerac", "chartreuse_green", "chartreuse_yellow"],
        tags={"special_interest"},
        scores={"popularity_prior": 0.2},
    ))
    groups.append(_override(
        ["irish_coffee"],
        tags={"coffee", "caffeinated", "alcoholic", "hot_drink", "evening", "winter"},
        scores={"popularity_prior": 0.4},
        bonus=0.12, bonus_occasions=["winter_party", "christmas_party"],
    ))

    # ==================================================== GRILL FOOD (§37)
    groups.append(_override(
        ["rumpsteak", "ribeye", "entrecote", "nackensteak"],
        tags={"main", "meat", "beef", "meat_eater", "grilled_food", "grill", "filling", "premium", "outdoor"},
        scores={"popularity_prior": 0.55, "premium_score": 0.75, "service_complexity": 0.35,
                "dietary_coverage": 0.35},
    ))
    groups.append(_override(
        ["bratwurst", "rostbratwurst", "nuernberger", "thueringer", "rindswurst", "krakauer",
         "currywurst", "bratwurst_im_broetchen"],
        tags={"main", "meat", "pork", "meat_eater", "grilled_food", "grill", "casual",
              "party_classic", "crowd_pleaser", "easy_service"},
        scores={"popularity_prior": 0.85, "crowd_pleaser_score": 0.85, "service_complexity": 0.25,
                "dietary_coverage": 0.3},
    ))
    groups.append(_override(
        ["hotdog", "cheese_hotdog", "chili_cheese_hotdog"],
        tags={"main", "handheld", "casual", "easy_service", "party_classic", "crowd_pleaser",
              "festival", "sports"},
        scores={"popularity_prior": 0.65, "crowd_pleaser_score": 0.7, "service_complexity": 0.2},
        bonus=0.1, bonus_occasions=["house_party", "sports_night", "festival_outdoor", "birthday", "grill_party", "game_night"],
    ))
    groups.append(_override(
        ["haehnchenbrust", "haehnchenschenkel", "chicken_wings", "chicken_drumsticks",
         "chicken_spiesse", "pulled_chicken"],
        tags={"main", "meat", "poultry", "meat_eater", "grilled_food", "grill", "crowd_pleaser"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.65, "service_complexity": 0.3,
                "dietary_coverage": 0.45},
    ))
    groups.append(_override(
        ["schweinebauch", "schweinekotelett", "spareribs", "bbq_ribs", "pulled_pork"],
        tags={"main", "meat", "pork", "meat_eater", "bbq", "grilled_food", "grill", "rich", "filling"},
        scores={"popularity_prior": 0.5, "service_complexity": 0.5, "prep_complexity": 0.55,
                "dietary_coverage": 0.3},
    ))
    groups.append(_override(
        ["lachsfilet", "garnelenspiess", "dorade", "forelle", "thunfischsteak"],
        tags={"main", "fish", "meat_eater", "pescatarian_friendly", "grilled_food", "grill",
              "premium", "summer"},
        scores={"popularity_prior": 0.4, "premium_score": 0.7, "service_complexity": 0.4,
                "dietary_coverage": 0.45},
    ))
    groups.append(_override(
        ["schaschlik", "grillspiess", "cevapcici", "koefte", "frikadellen", "lammkotelett", "lammspiess"],
        tags={"main", "meat", "meat_eater", "grilled_food", "grill", "party_classic"},
        scores={"popularity_prior": 0.45, "service_complexity": 0.3},
    ))

    # ================================================ VEG/VEGAN GRILL (§40)
    groups.append(_override(
        ["halloumi_grilled", "grillkaese", "halloumi_spiess"],
        tags={"main", "vegetarian", "grill", "grilled_food", "vegetarian_friendly", "cheese"},
        scores={"popularity_prior": 0.5, "crowd_pleaser_score": 0.55, "dietary_coverage": 0.65},
        bonus=0.1, bonus_occasions=["grill_party", "garden_party", "summer_party", "family_party"],
    ))
    groups.append(_override(
        ["gemuesespiess", "portobello_grill", "maiskolben", "gegrillte_aubergine",
         "gegrillte_zucchini", "gegrillte_paprika", "gefuellte_paprika", "grillgemuese"],
        tags={"vegetarian", "vegan", "grill", "grilled_food", "fresh", "light_food",
              "high_dietary_coverage", "vegan_friendly", "vegetarian_friendly"},
        scores={"popularity_prior": 0.5, "dietary_coverage": 0.95},
        bonus=0.1, bonus_occasions=["grill_party", "garden_party", "summer_party", "family_party"],
    ))
    groups.append(_override(
        ["tofu_spiess", "marinierter_tofu", "tempeh_grill", "seitan_steak"],
        tags={"vegan", "vegetarian", "main", "grill", "grilled_food", "vegan_friendly",
              "vegetarian_friendly", "high_dietary_coverage"},
        scores={"popularity_prior": 0.35, "dietary_coverage": 0.9},
    ))
    groups.append(_override(
        ["veggie_bratwurst", "vegane_bratwurst"],
        tags={"vegan", "vegetarian", "main", "grill", "grilled_food", "vegan_friendly",
              "vegetarian_friendly", "high_dietary_coverage", "casual"},
        scores={"popularity_prior": 0.45, "dietary_coverage": 0.9},
    ))
    groups.append(_override(
        ["ofenkartoffel", "grillkartoffel", "suesskartoffel_grill"],
        tags={"vegan", "vegetarian", "side", "grill", "grilled_food", "potato",
              "vegan_friendly", "vegetarian_friendly"},
        scores={"dietary_coverage": 0.9},
    ))

    # ======================================================== BURGER (§38)
    groups.append(_override(
        ["classic_burger", "cheeseburger", "bacon_burger", "bacon_cheeseburger", "double_burger",
         "double_cheeseburger", "bbq_burger", "chili_cheese_burger", "jalapeno_burger",
         "pulled_pork_burger"],
        tags={"meat", "meat_eater"},
        scores={"popularity_prior": 0.75, "crowd_pleaser_score": 0.8, "service_complexity": 0.45},
        bonus=0.1, bonus_occasions=["grill_party", "garden_party", "house_party", "birthday",
                                     "sports_night", "festival_outdoor", "casual_get_together"],
    ))
    groups.append(_override(
        ["classic_burger", "cheeseburger", "bacon_burger", "bacon_cheeseburger", "double_burger",
         "double_cheeseburger", "bbq_burger", "chili_cheese_burger", "jalapeno_burger"],
        tags={"beef"},
    ))
    groups.append(_override(
        ["pulled_pork_burger"], tags={"pork"},
    ))
    groups.append(_override(
        ["chicken_burger", "crispy_chicken_burger"],
        tags={"poultry", "meat_eater"},
        scores={"popularity_prior": 0.55, "service_complexity": 0.45},
        bonus=0.1, bonus_occasions=["grill_party", "house_party", "birthday", "sports_night"],
    ))
    groups.append(_override(
        ["fish_burger"], tags={"fish", "meat_eater", "pescatarian_friendly"},
        scores={"popularity_prior": 0.35, "service_complexity": 0.45},
    ))
    groups.append(_override(
        ["veggie_burger"],
        tags={"vegetarian", "vegetarian_friendly", "high_dietary_coverage"},
        scores={"popularity_prior": 0.55, "dietary_coverage": 0.75, "service_complexity": 0.45},
        bonus=0.1, bonus_occasions=["grill_party", "garden_party", "family_party", "birthday"],
    ))
    groups.append(_override(
        ["vegan_burger"],
        tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"},
        scores={"popularity_prior": 0.5, "dietary_coverage": 0.9, "service_complexity": 0.45},
        bonus=0.1, bonus_occasions=["grill_party", "garden_party", "family_party", "birthday"],
    ))
    groups.append(_override(
        ["halloumi_burger"], tags={"vegetarian", "vegetarian_friendly", "cheese"},
        scores={"dietary_coverage": 0.65},
    ))
    groups.append(_override(
        ["portobello_burger"], tags={"vegetarian", "vegan", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"},
        scores={"dietary_coverage": 0.9},
    ))

    # ======================================================== PIZZA (§41)
    groups.append(_override(
        ["pizza_margherita", "pizza_salami", "pizza_schinken", "pizza_funghi",
         "pizza_vegetaria", "pizza_vegan", "flammkuchen_klassisch", "flammkuchen_vegetarisch"],
        tags={"main", "shareable", "crowd_pleaser", "party_classic", "casual", "easy_service", "comfort_food"},
        scores={"popularity_prior": 0.78, "crowd_pleaser_score": 0.85, "service_complexity": 0.35},
        bonus=0.1, bonus_occasions=["house_party", "game_night", "movie_night", "birthday", "sports_night", "casual_get_together"],
    ))
    groups.append(_override(
        ["pizza_vegetaria", "flammkuchen_vegetarisch"], tags={"vegetarian", "vegetarian_friendly"},
    ))
    groups.append(_override(
        ["pizza_vegan"], tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"},
        scores={"dietary_coverage": 0.9},
    ))

    # =============================================== PASTA / LASAGNA (§42)
    groups.append(_override(
        ["spaghetti_bolognese", "pasta_arrabbiata", "pasta_napoli", "mac_and_cheese",
         "chicken_alfredo", "carbonara", "pesto_pasta",
         "lasagne_bolognese", "gemueselasagne", "vegane_lasagne"],
        tags={"main", "pasta", "comfort_food", "filling", "shareable", "buffet_friendly", "indoor"},
        scores={"popularity_prior": 0.55, "service_complexity": 0.35},
        bonus=0.1, bonus_occasions=["family_party", "dinner_party", "winter_party", "birthday"],
        penalty=-0.1, penalty_occasions=["pool_party", "picnic"],
    ))
    groups.append(_override(["gemueselasagne"], tags={"vegetarian", "vegetarian_friendly"}))
    groups.append(_override(["vegane_lasagne"], tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"}))

    # ============================================= CHILI / SOUPS (§43)
    groups.append(_override(
        ["chili_con_carne", "chili_sin_carne"],
        tags={"main", "comfort_food", "batchable", "buffet_friendly", "large_group_friendly", "filling", "spicy_food"},
        scores={"popularity_prior": 0.5, "batchability": 0.85, "large_group_score": 0.75},
        bonus=0.1, bonus_occasions=["winter_party", "house_party", "birthday", "festival_outdoor"],
    ))
    groups.append(_override(["chili_sin_carne"], tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"}))
    groups.append(_override(
        ["gulasch", "gulaschsuppe", "kartoffelsuppe", "kaesesuppe", "tomatensuppe"],
        tags={"main", "winter", "cold_weather", "batchable", "buffet_friendly", "comfort_food"},
        scores={"popularity_prior": 0.4, "batchability": 0.8, "winter_score": 0.9, "summer_score": 0.15},
    ))

    # =================================================== TACOS/WRAPS (§44)
    groups.append(_override(
        ["taco_bar", "beef_tacos", "chicken_tacos", "veggie_tacos", "vegan_tacos", "burritos",
         "veggie_burritos", "wraps", "chicken_wraps", "veggie_wraps", "quesadillas"],
        tags={"main", "handheld", "interactive", "social", "casual", "shareable"},
        scores={"popularity_prior": 0.55, "service_complexity": 0.4},
        bonus=0.1, bonus_occasions=["birthday", "house_party", "garden_party", "casual_get_together"],
    ))
    groups.append(_override(
        ["taco_bar"], tags={"interactive", "buffet", "high_customizability"},
        scores={"service_complexity": 0.55},
    ))
    groups.append(_override(["veggie_tacos", "veggie_wraps", "veggie_burritos"], tags={"vegetarian", "vegetarian_friendly"}))
    groups.append(_override(["vegan_tacos"], tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"}))

    # ==================================================== LOADED SNACKS
    groups.append(_override(
        ["loaded_fries", "loaded_nachos"],
        tags={"main", "snack", "shareable", "comfort_food", "party_classic", "nachos"},
        scores={"popularity_prior": 0.55, "crowd_pleaser_score": 0.6},
        bonus=0.1, bonus_occasions=["game_night", "house_party", "sports_night"],
    ))

    # ===================================================== CURRY (extra)
    groups.append(_override(
        ["chicken_curry", "thai_curry", "veganes_curry", "butter_chicken", "chicken_tikka_masala"],
        tags={"main", "spicy_food", "comfort_food", "buffet_friendly", "indoor"},
        scores={"popularity_prior": 0.4, "service_complexity": 0.4},
    ))
    groups.append(_override(["veganes_curry"], tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "high_dietary_coverage"}))

    # ====================================================== FINGERFOOD (§45)
    groups.append(_override(
        ["chicken_nuggets", "mini_schnitzel", "mozzarella_sticks", "onion_rings",
         "fruehlingsrollen", "mini_fruehlingsrollen", "samosas", "jalapeno_poppers"],
        tags={"fried_food", "comfort_food"},
        scores={"service_complexity": 0.35},
    ))
    groups.append(_override(
        ["caprese_spiesse", "kaese_trauben_spiesse", "antipasti_spiesse", "gemuesesticks_dip",
         "crostini", "bruschetta"],
        tags={"fresh", "light_food", "summer", "garden"},
        scores={"service_complexity": 0.2},
    ))
    groups.append(_override(
        ["falafel"], tags={"vegan", "vegetarian", "vegan_friendly", "vegetarian_friendly", "fried_food", "high_dietary_coverage"},
    ))
    groups.append(_override(
        ["mini_pizzen", "pizzaschnecken", "blaetterteigschnecken", "kaesegebaeck", "mini_quiche"],
        tags={"baked_food", "party_classic"},
    ))
    groups.append(_override(
        ["mini_wraps", "sandwiches", "club_sandwiches"],
        tags={"handheld", "portable"},
    ))
    groups.append(_override(
        ["mini_frikadellen", "datteln_im_speckmantel", "chicken_satay"],
        tags={"meat", "meat_eater"},
    ))
    for gid_list, occs in [
        (["mini_pizzen", "mozzarella_sticks", "fruehlingsrollen", "mini_fruehlingsrollen",
          "chicken_nuggets", "onion_rings", "mini_wraps", "bruschetta", "antipasti_spiesse",
          "caprese_spiesse", "samosas", "falafel", "crostini"],
         ["cocktail_party", "house_party", "birthday", "new_years_eve", "wedding", "game_night"]),
    ]:
        groups.append(_override(gid_list, bonus=0.08, bonus_occasions=occs))

    # ========================================================= SALADS (§46)
    groups.append(_override(
        ["kartoffelsalat", "nudelsalat", "tortellinisalat", "mediterraner_nudelsalat"],
        tags={"grill", "party_classic", "filling", "vegetarian_friendly"},
        scores={"popularity_prior": 0.7, "crowd_pleaser_score": 0.7, "service_complexity": 0.15},
        bonus=0.1, bonus_occasions=["grill_party", "garden_party", "summer_party", "family_party", "picnic"],
    ))
    groups.append(_override(
        ["gruener_salat", "gemischter_salat", "gurkensalat", "tomatensalat", "tomate_mozzarella",
         "caprese", "coleslaw", "krautsalat", "griechischer_salat", "caesar_salad", "rucolasalat",
         "farmersalat", "avocadosalat", "brotsalat"],
        tags={"fresh", "light_food", "summer", "high_dietary_coverage"},
        scores={"popularity_prior": 0.5, "service_complexity": 0.15},
        bonus=0.08, bonus_occasions=["grill_party", "garden_party", "summer_party", "family_party", "picnic"],
    ))
    groups.append(_override(
        ["couscoussalat", "bulgursalat", "taboule", "bohnensalat", "reissalat", "maissalat",
         "linsensalat", "kichererbsensalat"],
        tags={"modern", "buffet", "vegetarian", "vegetarian_friendly"},
        scores={"popularity_prior": 0.4},
    ))

    # ========================================================= SIDES
    groups.append(_override(
        ["pommes", "suesskartoffelpommes", "kartoffelwedges", "country_potatoes", "bratkartoffeln", "kartoffelpueree"],
        tags={"side", "potato", "fried_food", "casual", "grill", "vegan_friendly"},
        scores={"popularity_prior": 0.65, "crowd_pleaser_score": 0.7, "service_complexity": 0.2},
    ))
    groups.append(_override(
        ["reis", "basmati_reis", "couscous_side", "bulgur_side", "quinoa_side"],
        tags={"side", "grain", "modern", "vegan_friendly"},
        scores={"popularity_prior": 0.4, "service_complexity": 0.15},
    ))
    groups.append(_override(
        ["ratatouille", "bohnen", "baked_beans"],
        tags={"side", "vegetable", "vegan_friendly", "vegetarian_friendly"},
        scores={"popularity_prior": 0.35, "service_complexity": 0.2},
    ))
    groups.append(_override(
        ["knoblauchbrot"],
        tags={"bread", "comfort_food", "party_classic", "side"},
        scores={"popularity_prior": 0.55, "service_complexity": 0.2},
    ))

    # ======================================================== DESSERTS (§50)
    groups.append(_override(
        ["brownies", "blondies", "muffins", "schokomuffins", "blaubeermuffins", "cookies",
         "chocolate_chip_cookies", "donuts", "cupcakes"],
        tags={"dessert", "sweet_food", "shareable", "casual", "party_classic"},
        scores={"popularity_prior": 0.6, "crowd_pleaser_score": 0.65, "service_complexity": 0.4},
    ))
    groups.append(_override(
        ["kaesekuchen", "schokokuchen", "marmorkuchen", "apfelkuchen", "zitronenkuchen", "blechkuchen"],
        tags={"dessert", "celebratory", "shareable"},
        scores={"popularity_prior": 0.55, "crowd_pleaser_score": 0.6, "service_complexity": 0.4},
        bonus=0.1, bonus_occasions=["birthday"],
    ))
    groups.append(_override(
        ["tiramisu", "panna_cotta", "mousse_au_chocolat", "cheesecake_im_glas", "dessert_im_glas"],
        tags={"dessert", "premium", "elegant", "evening"},
        scores={"popularity_prior": 0.45, "premium_score": 0.7, "service_complexity": 0.55},
        bonus=0.1, bonus_occasions=["dinner_party"],
    ))
    groups.append(_override(
        ["vanillepudding_dessert", "schokopudding_dessert"],
        tags={"dessert", "comfort_food", "sweet_food"},
        scores={"popularity_prior": 0.45},
    ))
    groups.append(_override(
        ["obstsalat", "obstplatte"],
        tags={"dessert", "fresh", "summer", "light_food", "high_dietary_coverage", "vegan_friendly"},
        scores={"popularity_prior": 0.5, "dietary_coverage": 0.95, "service_complexity": 0.15},
    ))

    return _merge_overrides(*groups)


EXPLICIT_ITEM_OVERRIDES: dict[str, dict] = _build_explicit_overrides()


# ---------------------------------------------------------------------------
# Score-Ableitung (§53-57, §81): tag-basierte generische Heuristik
# ---------------------------------------------------------------------------
# Jeder Tag trägt (additiv) zu bestimmten Score-Feldern bei. Startwert für
# alle Felder ist 0.5 (Spec-Default), danach werden Deltas aus den final
# gemergten Tags aufaddiert und auf [0,1] geclamped. Das vermeidet eine
# hartcodierte Item->Occasion-Matrix (§1) und bleibt trotzdem konkret genug,
# um die Bandbreiten aus §53-57 sinnvoll zu treffen. Für die in der Spec
# namentlich genannten Beispiele (water, beer, gin_tonic, aperol_spritz, ...)
# werden zusätzlich exakte Werte über EXPLICIT_ITEM_OVERRIDES["scores"] gesetzt.

TAG_SCORE_DELTAS: dict[str, dict[str, float]] = {
    "water": {"popularity_prior": 0.4, "crowd_pleaser_score": 0.4, "service_complexity": -0.42,
              "prep_complexity": -0.42, "purchase_complexity": -0.3, "dietary_coverage": 0.5,
              "batchability": 0.3, "large_group_score": 0.35, "small_group_score": 0.15},
    "beer": {"popularity_prior": 0.3, "crowd_pleaser_score": 0.3, "service_complexity": -0.4,
             "prep_complexity": -0.4, "dietary_coverage": 0.1, "outdoor_score": 0.2, "large_group_score": 0.25},
    "softdrink": {"popularity_prior": 0.25, "crowd_pleaser_score": 0.3, "service_complexity": -0.4,
                  "dietary_coverage": 0.4, "large_group_score": 0.25},
    "wine": {"popularity_prior": 0.1, "crowd_pleaser_score": 0.08, "premium_score": 0.12,
             "evening_score": 0.2, "service_complexity": -0.35},
    "sparkling": {"premium_score": 0.2, "evening_score": 0.1, "service_complexity": -0.3, "novelty_score": 0.05},
    "spirit": {"premium_score": 0.05, "evening_score": 0.2, "service_complexity": -0.25},
    "strong_alcohol": {"service_complexity": 0.15, "late_night_score": 0.1, "small_group_score": 0.1},
    "cocktail": {"service_complexity": 0.15, "evening_score": 0.2, "premium_score": 0.1, "novelty_score": 0.1},
    "longdrink": {"service_complexity": 0.05, "evening_score": 0.15},
    "bar_style": {"service_complexity": 0.1, "premium_score": 0.1},
    "shaken": {"service_complexity": 0.25, "prep_complexity": 0.2},
    "stirred": {"service_complexity": 0.15, "prep_complexity": 0.1},
    "blended": {"service_complexity": 0.25, "messiness": 0.1},
    "premium": {"premium_score": 0.3, "purchase_complexity": 0.1},
    "elegant": {"premium_score": 0.25, "evening_score": 0.1},
    "crowd_pleaser": {"crowd_pleaser_score": 0.3},
    "casual": {"crowd_pleaser_score": 0.1, "indoor_score": 0.05},
    "fried_food": {"messiness": 0.2, "service_complexity": 0.1},
    "grilled_food": {"outdoor_score": 0.3, "summer_score": 0.15, "service_complexity": 0.1},
    "grill": {"outdoor_score": 0.3, "summer_score": 0.1},
    "fingerfood": {"shareability": 0.3, "portability": 0.2},
    "fingerfood_food": {"shareability": 0.25},
    "shareable": {"shareability": 0.35},
    "handheld": {"portability": 0.3, "messiness": -0.1},
    "portable": {"portability": 0.35},
    "buffet_friendly": {"shareability": 0.2, "large_group_score": 0.25, "batchability": 0.15},
    "batchable": {"batchability": 0.35, "large_group_score": 0.2},
    "easy_service": {"service_complexity": -0.2, "purchase_complexity": -0.05},
    "self_service": {"service_complexity": -0.15},
    "fresh_to_order": {"service_complexity": 0.25, "small_group_score": 0.15, "large_group_score": -0.15},
    "large_group_friendly": {"large_group_score": 0.35},
    "small_group_friendly": {"small_group_score": 0.35},
    "high_mess": {"messiness": 0.35},
    "low_mess": {"messiness": -0.25},
    "outdoor": {"outdoor_score": 0.35, "indoor_score": -0.1},
    "indoor": {"indoor_score": 0.35, "outdoor_score": -0.1},
    "garden": {"outdoor_score": 0.25, "summer_score": 0.15},
    "terrace": {"outdoor_score": 0.2},
    "poolside": {"outdoor_score": 0.25, "summer_score": 0.2},
    "picnic": {"outdoor_score": 0.2, "portability": 0.2},
    "festival": {"outdoor_score": 0.2, "large_group_score": 0.15},
    "daytime": {"daytime_score": 0.3},
    "brunch": {"daytime_score": 0.25, "evening_score": -0.1},
    "morning": {"daytime_score": 0.3, "evening_score": -0.15},
    "afternoon": {"daytime_score": 0.2},
    "evening": {"evening_score": 0.35},
    "late_night": {"late_night_score": 0.4, "evening_score": 0.1},
    "all_day": {"daytime_score": 0.15, "evening_score": 0.15},
    "summer": {"summer_score": 0.35},
    "hot_weather": {"summer_score": 0.3},
    "winter": {"winter_score": 0.35},
    "cold_weather": {"winter_score": 0.3},
    "spring": {"spring_score": 0.35},
    "autumn": {"autumn_score": 0.3},
    "refreshing": {"summer_score": 0.2, "daytime_score": 0.1},
    "hydrating": {"summer_score": 0.15},
    "comfort_food": {"winter_score": 0.2, "autumn_score": 0.1},
    "rich": {"winter_score": 0.15},
    "caffeinated": {"late_night_score": 0.1},
    "coffee": {"daytime_score": 0.1},
    "energy": {"late_night_score": 0.25, "crowd_pleaser_score": -0.05},
    "trendy": {"novelty_score": 0.25},
    "modern": {"novelty_score": 0.2},
    "traditional": {"novelty_score": -0.15, "crowd_pleaser_score": 0.1},
    "nostalgic": {"novelty_score": -0.1},
    "party_classic": {"novelty_score": -0.1, "crowd_pleaser_score": 0.1},
    "special_interest": {"novelty_score": 0.2, "crowd_pleaser_score": -0.1, "popularity_prior": -0.1},
    "dessert": {"evening_score": 0.05},
    "main": {"large_group_score": 0.05},
    "sharing": {"shareability": 0.3},
    "social": {"crowd_pleaser_score": 0.05},
    "interactive": {"novelty_score": 0.1},
    "celebratory": {"premium_score": 0.05},
    "festive": {"premium_score": 0.05},
}


# Kategoriebasis für popularity_prior/crowd_pleaser_score/service_complexity,
# damit auch Items ohne markante Tags nicht bei 0.5 verharren (§55-56).
_CATEGORY_POPULARITY_BASE: dict[str, float] = {
    "water": 0.6, "beer": 0.55, "softdrink": 0.5, "wine": 0.45, "sparkling_wine": 0.4,
    "juice": 0.4, "spirit": 0.3, "liqueur": 0.28, "fortified_wine": 0.22, "energy": 0.35,
    "coffee": 0.4, "burger": 0.55, "grill": 0.5, "veg_grill": 0.35, "salad": 0.45,
    "side": 0.4, "fingerfood": 0.4, "dessert": 0.4, "main_dish": 0.4, "snack": 0.5,
    "sauce": 0.3, "bread": 0.4, "cheese": 0.35, "vegetable": 0.35, "fruit": 0.4,
    "cocktail_vodka": 0.35, "cocktail_gin": 0.35, "cocktail_rum": 0.35, "cocktail_tequila": 0.35,
    "cocktail_whiskey": 0.3, "cocktail_brandy": 0.22, "cocktail_spritz": 0.45,
    "cocktail_longdrink": 0.3, "cocktail_complex": 0.2, "softdrink_mix": 0.4,
}


def _baseline_scores(item, tags: set[str], category: str, is_recipe: bool, is_dc: bool,
                      diet_alcohol_info) -> dict[str, float]:
    is_vegan, is_vegetarian, is_meat, is_fish, contains_alcohol, abv, contains_caffeine = diet_alcohol_info

    fields = [
        "popularity_prior", "crowd_pleaser_score", "novelty_score", "premium_score",
        "prep_complexity", "service_complexity", "purchase_complexity", "batchability",
        "shareability", "portability", "messiness", "indoor_score", "outdoor_score",
        "daytime_score", "evening_score", "late_night_score", "spring_score", "summer_score",
        "autumn_score", "winter_score", "small_group_score", "large_group_score", "dietary_coverage",
    ]
    acc = {f: 0.5 for f in fields}

    base_pop = _CATEGORY_POPULARITY_BASE.get(category)
    if base_pop is not None:
        acc["popularity_prior"] = base_pop
        acc["crowd_pleaser_score"] = base_pop

    if getattr(item, "popular", False):
        acc["popularity_prior"] = max(acc["popularity_prior"], 0.7)
        acc["crowd_pleaser_score"] = max(acc["crowd_pleaser_score"], 0.65)

    for tag in tags:
        deltas = TAG_SCORE_DELTAS.get(tag)
        if not deltas:
            continue
        for field, delta in deltas.items():
            acc[field] = acc.get(field, 0.5) + delta

    # --- Rezept-spezifische Komplexität (§53/§54) ---------------------------
    if is_recipe:
        components = getattr(item, "components", [])
        n_components = len(components)
        distinct_ids = len({_get(c, "ingredient_id") for c in components})
        acc["service_complexity"] = _clamp01(acc["service_complexity"] + 0.03 * n_components)
        acc["prep_complexity"] = _clamp01(acc["service_complexity"] * 0.9)
        acc["purchase_complexity"] = _clamp01(0.15 + 0.05 * distinct_ids)
        satiety = getattr(item, "satiety_factor", 1.0)
        if satiety and satiety > 1.1:
            acc["large_group_score"] = _clamp01(acc["large_group_score"] + 0.05)

    if is_dc:
        acc["service_complexity"] = _clamp01(min(acc["service_complexity"], 0.3))
        acc["prep_complexity"] = acc["service_complexity"]
        acc["purchase_complexity"] = _clamp01(acc.get("purchase_complexity", 0.3))

    # --- Alkohol/Koffein-Feineinstellung ------------------------------------
    if contains_alcohol and abv and abv >= 30:
        acc["small_group_score"] = _clamp01(acc["small_group_score"] + 0.05)
    if contains_caffeine:
        acc["late_night_score"] = _clamp01(acc["late_night_score"] + 0.05)

    # --- Dietary Coverage (§57): explizite Fleisch/Fisch/Vegan-Bandbreiten ---
    if is_vegan:
        acc["dietary_coverage"] = max(acc["dietary_coverage"], 0.9)
    elif is_vegetarian and not is_meat and not is_fish:
        acc["dietary_coverage"] = max(acc["dietary_coverage"], 0.7)
    elif is_fish:
        acc["dietary_coverage"] = min(max(acc["dietary_coverage"], 0.3), 0.45)
    elif "beef" in tags:
        acc["dietary_coverage"] = min(acc["dietary_coverage"], 0.4)
    elif "pork" in tags:
        acc["dietary_coverage"] = min(acc["dietary_coverage"], 0.3)
    elif "poultry" in tags:
        acc["dietary_coverage"] = min(max(acc["dietary_coverage"], 0.3), 0.45)

    return {f: _clamp01(v) for f, v in acc.items()}


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------


def _base_tags_for_item(item, catalog) -> set[str]:
    """Layer 1 + Layer 2: Family Defaults + Category Defaults."""
    tags: set[str] = set()
    cls_name = type(item).__name__

    if cls_name == "Ingredient":
        tags |= FAMILY_TAG_DEFAULTS.get(item.family, set(_FAMILY_FALLBACK_TAGS))

    category = getattr(item, "category", "")
    if cls_name == "DirectConsumable":
        # Für DirectConsumables gilt zunächst die Ingredient-Family (meist ==
        # category) als Layer 1, danach die (i.d.R. identische, aber ggf.
        # spezifischere) Category-Ebene als Layer 2.
        ing = catalog.ingredients.get(item.ingredient_id) if catalog else None
        if ing is not None:
            tags |= FAMILY_TAG_DEFAULTS.get(ing.family, set())
    tags |= CATEGORY_TAG_DEFAULTS.get(category, set() if cls_name != "Recipe" else set(_CATEGORY_FALLBACK_TAGS))

    if not tags:
        tags |= set(_CATEGORY_FALLBACK_TAGS)

    return tags


def _apply_alcohol_caffeine_correction(tags: set[str], contains_alcohol: bool, abv: float,
                                        contains_caffeine: bool) -> set[str]:
    tags = set(tags)
    if contains_alcohol:
        tags.discard("non_alcoholic")
        tags.add("alcoholic")
        if abv and 0 < abv <= 3.5:
            tags.add("low_alcohol")
    else:
        tags.discard("alcoholic")
        tags.discard("strong_alcohol")
        tags.add("non_alcoholic")
    if contains_caffeine:
        tags.add("caffeinated")
    return tags


def derive_recommendation_metadata(item, catalog=None) -> RecommendationMetadata:
    """§81 Fallback-Ableitung: Layer 1-3 (Family/Category/Recipe-Component),
    OHNE EXPLICIT_ITEM_OVERRIDES. Wird auch von party_engine/catalog.py als
    Defensive-Fallback für Items ohne persistierte recommendation-Daten genutzt."""
    cls_name = type(item).__name__
    category = getattr(item, "category", "")

    tags = _base_tags_for_item(item, catalog)

    if cls_name == "Recipe" and catalog is not None:
        tags |= derive_tags_from_recipe(item, catalog.ingredients)
    elif cls_name == "Recipe":
        tags |= derive_tags_from_recipe(item, {})

    diet_alcohol_info = _resolve_diet_and_alcohol(item, catalog)
    is_vegan, is_vegetarian, is_meat, is_fish, contains_alcohol, abv, contains_caffeine = diet_alcohol_info

    tags = _apply_alcohol_caffeine_correction(tags, contains_alcohol, abv, contains_caffeine)

    # Explizite CatalogItem-Tags (Layer 5, bereits in build_catalog.py gepflegt,
    # z.B. "beef"/"pork"/"poultry"/"fish" für Ingredients).
    explicit_item_tags = getattr(item, "tags", None)
    if explicit_item_tags:
        tags |= set(explicit_item_tags)

    if len(tags) < 2:
        tags |= set(_CATEGORY_FALLBACK_TAGS)

    scores = _baseline_scores(
        item, tags, category,
        is_recipe=(cls_name == "Recipe"),
        is_dc=(cls_name == "DirectConsumable"),
        diet_alcohol_info=diet_alcohol_info,
    )

    return RecommendationMetadata(tags=tags, **scores)


def apply_recommendation_metadata(item, catalog=None) -> RecommendationMetadata:
    """§4 vollständige Vererbungskette inkl. Layer 6 (EXPLICIT_ITEM_OVERRIDES).
    Dies ist der Haupt-Einstiegspunkt, der von build_catalog.py für jedes
    Ingredient/DirectConsumable/Recipe aufgerufen wird."""
    meta = derive_recommendation_metadata(item, catalog)

    override = EXPLICIT_ITEM_OVERRIDES.get(item.id)
    if override:
        if override.get("tags"):
            meta.tags = set(meta.tags) | set(override["tags"])
        if override.get("scores"):
            for field, value in override["scores"].items():
                setattr(meta, field, _clamp01(value))
        if override.get("occasion_affinity_overrides"):
            meta.occasion_affinity_overrides = dict(meta.occasion_affinity_overrides)
            meta.occasion_affinity_overrides.update(override["occasion_affinity_overrides"])

    return meta
