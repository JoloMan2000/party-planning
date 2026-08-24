"""
Zentrale Tag-Taxonomie-Registry (§3 der Recommendation-Spec).
================================================================

Alle Tags, die irgendwo im Recommendation-System verwendet werden (in
RecommendationMetadata.tags, OccasionProfile.preferred_tags/discouraged_tags,
etc.), MUESSEN aus dieser Registry stammen. Das verhindert Tippfehler-Varianten
("outdoor" vs. "out_door") und stellt sicher, dass Tag-Vererbung (Ingredient ->
Recipe -> CatalogItem) und Occasion-Matching konsistent auf demselben
Vokabular arbeiten.

Diese Datei enthaelt bewusst KEINE Zuordnung "welches Item hat welchen Tag"
(das lebt in build_catalog.py/recommendation_tagging.py) und KEINE
Occasion-Gewichte (das lebt in catalog/occasions/*.json) — nur das erlaubte
Vokabular selbst (§76: Tags leben beim Item, Occasion-Gewichtung beim Profil).
"""

from __future__ import annotations

SOCIAL_PARTY_STYLE_TAGS: frozenset[str] = frozenset({
    "casual", "social", "crowd_pleaser", "premium", "elegant", "celebratory",
    "festive", "traditional", "modern", "trendy", "nostalgic", "interactive",
    "sharing", "comfort_food", "party_classic", "special_interest",
})

LOCATION_SETTING_TAGS: frozenset[str] = frozenset({
    "indoor", "outdoor", "garden", "terrace", "poolside", "picnic", "festival",
    "bar_style", "table_service", "buffet", "grill", "kitchen_required",
    "minimal_equipment",
})

TIME_TAGS: frozenset[str] = frozenset({
    "morning", "brunch", "daytime", "afternoon", "evening", "late_night",
    "all_day",
})

SEASON_TAGS: frozenset[str] = frozenset({
    "spring", "summer", "autumn", "winter", "hot_weather", "cold_weather",
})

SERVICE_OPERATION_TAGS: frozenset[str] = frozenset({
    "easy_service", "fast_service", "self_service", "batchable", "make_ahead",
    "fresh_to_order", "bar_required", "shaken", "stirred", "blended",
    "grilled", "fried", "baked", "cooked", "no_cook", "fingerfood", "handheld",
    "low_mess", "high_mess", "portable", "shareable", "buffet_friendly",
    "large_group_friendly", "small_group_friendly",
})

DRINK_CHARACTER_TAGS: frozenset[str] = frozenset({
    "hydrating", "non_alcoholic", "alcoholic", "low_alcohol", "strong_alcohol",
    "beer", "wine", "sparkling", "spirit", "longdrink", "cocktail", "shot",
    "energy", "caffeinated", "softdrink", "juice", "water", "hot_drink",
    "refreshing", "fruity", "citrus", "sweet", "dry", "bitter", "herbal",
    "creamy", "coffee", "tea", "tropical", "spicy", "smoky", "light_drink",
    "heavy_drink", "mixer",
})

FOOD_ROLE_TAGS: frozenset[str] = frozenset({
    "main", "side", "salad", "bread", "snack", "fingerfood_food", "dessert",
    "dip", "sauce", "topping", "late_night_food",
})

FOOD_CHARACTER_TAGS: frozenset[str] = frozenset({
    "meat", "beef", "pork", "poultry", "fish", "seafood", "vegetarian",
    "vegan", "cheese", "potato", "pasta", "rice", "grain", "vegetable",
    "fruit", "fresh", "fried_food", "grilled_food", "baked_food",
    "spicy_food", "savory", "sweet_food", "rich", "light_food", "filling",
    "refreshing_food", "bbq",
})

DIET_COVERAGE_TAGS: frozenset[str] = frozenset({
    "vegetarian_friendly", "vegan_friendly", "pescatarian_friendly",
    "meat_eater", "potential_gluten_free", "potential_lactose_free",
    "high_dietary_coverage",
})

# Zusätzliche operative/strukturelle Tags, die in der Spec an einzelnen
# Stellen auftauchen (§45/48/58/64/etc.), aber keiner der Kern-Gruppen oben
# eindeutig zugeordnet sind. Ebenfalls Teil des erlaubten Vokabulars.
MISC_TAGS: frozenset[str] = frozenset({
    "party", "sports", "movie", "game", "house_party", "supporting_item",
    "nachos", "taco", "high_customizability",
})

ALL_TAGS: frozenset[str] = (
    SOCIAL_PARTY_STYLE_TAGS
    | LOCATION_SETTING_TAGS
    | TIME_TAGS
    | SEASON_TAGS
    | SERVICE_OPERATION_TAGS
    | DRINK_CHARACTER_TAGS
    | FOOD_ROLE_TAGS
    | FOOD_CHARACTER_TAGS
    | DIET_COVERAGE_TAGS
    | MISC_TAGS
)


def validate_tags(tags) -> list[str]:
    """Gibt alle Tags zurück, die NICHT Teil der zentralen Registry sind.
    Leere Liste == vollständig valide. Wird von tests/test_recommendation*.py
    und optional von build_catalog.py._validate_catalog() genutzt."""
    return sorted(t for t in tags if t not in ALL_TAGS)
