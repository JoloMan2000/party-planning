"""Tests für party_engine/recommendation.py.

Deckt die in der Aufgabenstellung geforderten Punkte ab (siehe Claude-Code-
Memory, recommendation_engine_full_spec.txt):
    §71 Occasion Coverage Validation
    §72 Category Coverage Test
    §73 Recommendation Snapshot Tests
    Gast-Diät-Sicherheit (§61/§78)
    Diversity Enforcement (§64/§65)

Nutzt den ECHTEN Katalog (kein Mocking, siehe conftest.py / AUFGABE §43).
"""

from __future__ import annotations

import pytest

from party_engine.domain import CatalogItem, DietaryProfile, GuestResponse, Recipe
from party_engine.occasions import load_all_occasions
from party_engine.recommendation_domain import PartyContext
from party_engine.recommendation import (
    apply_diversity_constraints,
    apply_exposure_shrinkage,
    compute_group_signal_score,
    ensure_required_coverage,
    format_score_explanation,
    recommend_for_admin,
    recommend_for_guest,
    resolve_occasion_for_scoring,
    score_item_for_occasion,
)
from party_engine.recommendation_domain import GroupSignal, RecommendationExposure


@pytest.fixture(scope="session")
def occasions():
    return load_all_occasions()


def _beverage_items(catalog):
    return [it for it in catalog.all_selectable_items() if "beverage" in it.demand_group or it.demand_group == "energy"]


def _food_items(catalog):
    return [
        it
        for it in catalog.all_selectable_items()
        if it not in _beverage_items(catalog)
    ]


# ---------------------------------------------------------------------------
# §71 — Occasion Coverage Validation
# ---------------------------------------------------------------------------

_MAJOR_OCCASIONS = ["grill_party", "cocktail_party", "summer_party", "birthday", "house_party"]

_ALL_OCCASION_IDS = [
    "bachelor_party", "birthday", "brunch", "casual_get_together", "christmas_party",
    "cocktail_party", "daydrinking", "dinner_party", "engagement_party", "family_party",
    "festival_outdoor", "game_night", "garden_party", "grill_party", "house_party",
    "movie_night", "new_years_eve", "picnic", "pool_party", "sports_night",
    "summer_party", "wedding", "winter_party",
]


def test_occasion_coverage_underlying_pool_is_large(catalog, occasions):
    """§71: der Kandidatenpool je Domain muss ausreichend gross sein, damit
    top_n-Trunkierung sinnvolle Auswahl ermöglicht."""
    beverages = _beverage_items(catalog)
    food = _food_items(catalog)
    assert len(beverages) >= 15
    assert len(food) >= 15


def test_recommend_for_admin_nonempty_for_all_23_occasions(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=19, guest_count=20)
    assert len(occasions) == 23
    for occasion_id in _ALL_OCCASION_IDS:
        profile = occasions[occasion_id]
        result = recommend_for_admin(catalog, profile, ctx, top_n=20)
        assert isinstance(result, list)
        assert len(result) > 0
        for item, score in result:
            assert isinstance(item, CatalogItem)
            assert hasattr(score, "total_score")


def test_recommend_for_guest_nonempty_for_major_occasions(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=19, guest_count=20)
    guest = GuestResponse(guest_name="Test Guest", start_time="18:00")
    for occasion_id in _MAJOR_OCCASIONS:
        profile = occasions[occasion_id]
        result = recommend_for_guest(catalog, profile, ctx, guest, top_n=12)
        assert isinstance(result, list)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# §72 — Category Coverage Test
# ---------------------------------------------------------------------------

_CATEGORY_EXAMPLES = {
    "beer_pils": "beer",
    "red_wine": "wine",
    "cola": "softdrink",
    "energy_drink_generic": "caffeinated",
    "orange_juice": "juice",
    "vodka": "spirit",
    "espresso_martini": "cocktail",
    "bratwurst": "grilled_food",
    "veggie_bratwurst": "vegan",
    "pulled_pork_burger": "main",
    "pizza_margherita": "vegetarian",
    "lasagne_bolognese": "pasta",
    "mini_frikadellen": "fingerfood",
    "kartoffelsalat": "salad",
    "pommes": "side",
    "potato_chips": "snack",
    "brownies": "dessert",
}


def test_category_coverage_examples_have_recommendation_tags(catalog):
    """§72: exemplarische Items aus jeder grossen Katalog-Familie besitzen
    >= 2 Tags sowie mindestens den erwarteten Signal-Tag."""
    for item_id, expected_tag in _CATEGORY_EXAMPLES.items():
        item = catalog.get_item(item_id)
        assert item is not None, f"missing catalog item: {item_id}"
        assert len(item.recommendation.tags) >= 2, f"{item_id} has too few tags"
        assert expected_tag in item.recommendation.tags, (
            f"{item_id} expected tag '{expected_tag}', got {sorted(item.recommendation.tags)}"
        )


def test_full_catalog_coverage_rule(catalog):
    """§70: JEDES empfehlbare Item hat vollständige RecommendationMetadata
    mit >= 2 Tags."""
    for item in catalog.all_selectable_items():
        assert item.recommendation is not None
        assert len(item.recommendation.tags) >= 2, f"{item.id} has < 2 tags"


# ---------------------------------------------------------------------------
# §73 — Recommendation Snapshot Tests
# ---------------------------------------------------------------------------


def test_grill_party_snapshot_quality(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=17, guest_count=25)
    result = recommend_for_admin(catalog, occasions["grill_party"], ctx, top_n=20)
    top10 = result[:10]

    grill_relevant_tags = {"beer", "grill", "grilled_food", "salad", "bread"}
    relevant_count = sum(
        1 for item, _ in top10 if item.recommendation.tags & grill_relevant_tags
    )
    assert relevant_count >= 6, (
        f"expected >=6 of top10 grill_party candidates to be grill-relevant, got {relevant_count}: "
        f"{[i.name for i, _ in top10]}"
    )

    # Nicht dominiert von hoch-spirituosigen premium/bar_style Items ohne
    # jeglichen Grill-Bezug (qualitative/lockere Prüfung, siehe Aufgabe §73).
    bar_dominant = [
        item
        for item, _ in top10
        if {"premium", "bar_style", "strong_alcohol"} <= item.recommendation.tags
        and not (item.recommendation.tags & grill_relevant_tags)
    ]
    assert len(bar_dominant) <= 2


def test_cocktail_party_snapshot_quality(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=21, guest_count=15)
    result = recommend_for_admin(catalog, occasions["cocktail_party"], ctx, top_n=20)
    top10 = result[:10]
    cocktail_count = sum(1 for item, _ in top10 if "cocktail" in item.recommendation.tags)
    assert cocktail_count >= 3, (
        f"expected several cocktail-tagged items in cocktail_party top10, got {cocktail_count}: "
        f"{[i.name for i, _ in top10]}"
    )


def test_movie_night_snapshot_quality(catalog, occasions):
    ctx = PartyContext(season="winter", hour_of_day=21, guest_count=8)
    result = recommend_for_admin(catalog, occasions["movie_night"], ctx, top_n=20)
    top10 = result[:10]
    snack_comfort_count = sum(
        1 for item, _ in top10 if item.recommendation.tags & {"snack", "comfort_food"}
    )
    assert snack_comfort_count >= 4, (
        f"expected several snack/comfort_food items in movie_night top10, got {snack_comfort_count}: "
        f"{[i.name for i, _ in top10]}"
    )


# ---------------------------------------------------------------------------
# Gast-Diät-Sicherheit (§61/§78)
# ---------------------------------------------------------------------------

_NON_VEGAN_TAGS = {"meat", "beef", "pork", "poultry", "fish", "seafood"}


def test_vegan_guest_never_gets_structurally_non_vegan_item(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=19, guest_count=20)
    guest = GuestResponse(
        guest_name="Vegan Guest",
        start_time="18:00",
        dietary=DietaryProfile(vegan=True),
    )
    for occasion_id in _MAJOR_OCCASIONS:
        profile = occasions[occasion_id]
        result = recommend_for_guest(catalog, profile, ctx, guest, top_n=12)
        for item, score in result:
            assert not (item.recommendation.tags & _NON_VEGAN_TAGS), (
                f"vegan guest got non-vegan item {item.id} in {occasion_id}: "
                f"{sorted(item.recommendation.tags)}"
            )
            if isinstance(item, Recipe):
                assert item.is_vegan, f"vegan guest got Recipe.is_vegan=False item {item.id}"


def test_dietary_hard_violation_scores_zero_directly():
    from party_engine.recommendation_domain import OccasionProfile
    from party_engine.domain import Recipe as RecipeCls

    meat_recipe = RecipeCls(
        id="test_meat_dish",
        name="Test Meat Dish",
        category="main_dish",
        demand_group="main",
        is_vegan=False,
        is_vegetarian=False,
    )
    meat_recipe.recommendation.tags = {"meat", "beef", "main"}

    profile = OccasionProfile(id="test_occasion", label_de="Test", label_en="Test")
    ctx = PartyContext()
    guest = GuestResponse(guest_name="Vegan", start_time="18:00", dietary=DietaryProfile(vegan=True))

    score = score_item_for_occasion(meat_recipe, profile, ctx, guest=guest)
    assert score.total_score == 0.0
    assert "dietary_hard_constraint" in score.penalties
    assert score.reasons


# ---------------------------------------------------------------------------
# Diversity Enforcement (§64/§65)
# ---------------------------------------------------------------------------


def test_apply_diversity_constraints_caps_repeated_category(catalog, occasions):
    """cocktail_party sollte ohne Diversity-Constraint von vielen Items
    derselben Kategorie (z.B. cocktail_vodka) dominiert werden können -
    nach apply_diversity_constraints darf keine Kategorie den Cap
    überschreiten."""
    ctx = PartyContext(season="summer", hour_of_day=21, guest_count=15)
    profile = occasions["cocktail_party"]

    scored = []
    for item in catalog.all_selectable_items():
        if item.demand_group != "alcoholic_beverage":
            continue
        score = score_item_for_occasion(item, profile, ctx)
        scored.append((item, score))

    # Ohne Constraint: mind. eine Kategorie muss mit vielen Items vertreten
    # sein (Voraussetzung dafür, dass der Test überhaupt etwas prüft und
    # nicht tautologisch ist).
    scored.sort(key=lambda pair: pair[1].total_score, reverse=True)
    from collections import Counter

    top20_categories = Counter(item.category for item, _ in scored[:20])
    assert max(top20_categories.values()) > 2, "fixture assumption violated: need category repetition in raw ranking"

    max_cap = 2
    admitted = apply_diversity_constraints(scored, max_same_subcategory=max_cap)
    admitted_categories = Counter(item.category for item, _ in admitted)
    for category, count in admitted_categories.items():
        assert count <= max_cap, f"category {category} appears {count} times, exceeds cap {max_cap}"

    # Score-absteigende Reihenfolge unter den zugelassenen Items bleibt erhalten.
    scores_in_order = [score.total_score for _, score in admitted]
    assert scores_in_order == sorted(scores_in_order, reverse=True)


def test_ensure_required_coverage_backfills_non_alcoholic(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=21, guest_count=15)
    profile = occasions["cocktail_party"]

    scored = []
    for item in catalog.all_selectable_items():
        if "beverage" not in item.demand_group and item.demand_group != "energy":
            continue
        score = score_item_for_occasion(item, profile, ctx)
        scored.append((item, score))

    scored.sort(key=lambda pair: pair[1].total_score, reverse=True)
    # Nur die absoluten Top-3 (überwiegend Cocktails) als "admitted" Basis,
    # damit ein Backfill tatsächlich nötig ist.
    admitted = scored[:3]
    covered = ensure_required_coverage(admitted, scored, domain="beverage")

    non_alcoholic_count = sum(1 for item, _ in covered if "non_alcoholic" in item.recommendation.tags)
    assert non_alcoholic_count >= 2


# ---------------------------------------------------------------------------
# §62 — Adaptiver Gruppen-Score (Bayesian Shrinkage)
# ---------------------------------------------------------------------------


def test_compute_group_signal_score_no_data_returns_prior():
    signal = GroupSignal(item_id="x", supporting_guests=0, eligible_response_count=0)
    assert compute_group_signal_score(signal, occasion_prior=0.42) == 0.42


def test_compute_group_signal_score_formula():
    signal = GroupSignal(item_id="x", supporting_guests=8, eligible_response_count=10)
    result = compute_group_signal_score(signal, occasion_prior=0.5, prior_strength=10.0)
    expected = (8 + 10 * 0.5) / (10 + 10)
    assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# §63 — Exposure Correction
# ---------------------------------------------------------------------------


def test_apply_exposure_shrinkage_zero_shown_returns_prior():
    exposure = RecommendationExposure(item_id="x", shown_count=0, selected_count=0)
    assert apply_exposure_shrinkage(exposure, prior=0.3) == 0.3


def test_apply_exposure_shrinkage_low_sample_shrinks_strongly():
    exposure = RecommendationExposure(item_id="x", shown_count=1, selected_count=1)
    result = apply_exposure_shrinkage(exposure, prior=0.3, min_sample_size=20)
    # 1 shown / 1 selected -> selection_rate = 1.0, but weight = 1/20 = 0.05
    # -> result should stay very close to the prior, not jump to 1.0.
    assert result == pytest.approx(0.05 * 1.0 + 0.95 * 0.3)
    assert result < 0.4


def test_apply_exposure_shrinkage_large_sample_trusts_empirical_rate():
    exposure = RecommendationExposure(item_id="x", shown_count=100, selected_count=80)
    result = apply_exposure_shrinkage(exposure, prior=0.3, min_sample_size=20)
    assert result == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# §68/§69 — Fallback / Multi-Occasion
# ---------------------------------------------------------------------------


def test_resolve_occasion_for_scoring_fallback(occasions):
    profile = resolve_occasion_for_scoring(None, occasions)
    assert profile.id == "casual_get_together"

    profile2 = resolve_occasion_for_scoring([], occasions)
    assert profile2.id == "casual_get_together"

    profile3 = resolve_occasion_for_scoring(["some_unknown_future_occasion"], occasions)
    assert profile3.id == "casual_get_together"


def test_resolve_occasion_for_scoring_multi_occasion(occasions):
    profile = resolve_occasion_for_scoring(["birthday", "garden_party"], occasions)
    assert profile.id == "birthday+garden_party"
    assert profile.preferred_tags


# ---------------------------------------------------------------------------
# §83 — Explainability
# ---------------------------------------------------------------------------


def test_format_score_explanation_contains_reasons(catalog, occasions):
    ctx = PartyContext(season="summer", hour_of_day=17, guest_count=25)
    item = catalog.get_item("beer_pils")
    score = score_item_for_occasion(item, occasions["grill_party"], ctx)
    text = format_score_explanation(score, lang="de")
    assert "Gesamt-Score" in text
    assert isinstance(text, str)
    assert len(text) > 0

    text_en = format_score_explanation(score, lang="en")
    assert "Total score" in text_en


# ---------------------------------------------------------------------------
# §78 invariant sanity check: this module never touches the demand pipeline
# ---------------------------------------------------------------------------


def test_recommendation_module_does_not_import_demand_pipeline():
    import party_engine.recommendation as rec_module

    forbidden = {"party_engine.engine", "party_engine.allocation", "party_engine.bom", "party_engine.substitution", "party_engine.purchasing"}
    module_globals = vars(rec_module)
    imported_modules = {
        getattr(v, "__name__", None) for v in module_globals.values() if hasattr(v, "__name__")
    }
    assert not (forbidden & imported_modules)
