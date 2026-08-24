"""
Context-Fit-Scoring pro Item (Spec §12-§14/§42/§43).
=======================================================

Hybrid-Strategie (mirrors das etablierte "kuratierte Teilmenge + Fallback"-
Muster von ``recommendation_tagging.py``): für die wenigen im Spec explizit
ausgearbeiteten Iconic-Items (Aperol Spritz §13, Bratwurst §14) wird eine
handkuratierte ``ContextAffinity`` verwendet. Für alle übrigen ~600
Katalog-Items wird eine äquivalente Affinität automatisch aus den bereits
vorhandenen (bisher toten) ``RecommendationMetadata``-Feldern
(``spring_score``/``indoor_score``/... ) sowie aus Tag-Überlappung mit dem
aktiven ``LocationProfile`` synthetisiert - kein neuer 600-Item-Datenpflege-
Aufwand nötig.

WICHTIG (§78): ``calculate_context_fit()`` ist eine EIGENE Scoring-Schicht,
unabhängig von ``party_engine.recommendation.score_item_for_occasion()``. Sie
wird additiv in ``recommend_for_admin()``/``recommend_for_guest()`` eingebunden
(siehe party_engine/recommendation.py), nicht in die bestehende Formel
gemischt."""

from __future__ import annotations

from party_context import config
from party_context.domain import ContextAffinity, ContextFitScore, DerivedPartyContext
from party_context.locations import get_location_profile

# Tag-Namen, die 1:1 einer Infrastruktur-Capability entsprechen (§17) - werden
# für synthetisierte (nicht-kuratierte) Items als ``preferred_capabilities``-
# Heuristik verwendet, falls das Item diesen Tag trägt.
_KNOWN_CAPABILITY_TAGS = {
    "grill", "kitchen", "fridge", "freezer", "ice", "bar_setup",
    "espresso", "power", "running_water", "dancefloor",
}

# §13: Aperol Spritz
_APEROL_SPRITZ_AFFINITY = ContextAffinity(
    seasons={"spring": 0.75, "summer": 1.00, "autumn": 0.45, "winter": 0.20},
    locations={"garden": 0.95, "terrace": 1.00, "rooftop": 0.95, "pool": 0.90, "private_home": 0.60, "event_hall": 0.55},
    indoor_outdoor={"outdoor": 0.95, "mixed": 0.85, "indoor": 0.55},
    dayparts={"daytime": 0.85, "afternoon": 1.00, "evening": 0.80, "late_night": 0.45},
    weather_conditions={"sunny": 0.95, "rain": 0.35},
)

# §14: Bratwurst
_BRATWURST_AFFINITY = ContextAffinity(
    seasons={"spring": 0.80, "summer": 1.00, "autumn": 0.75, "winter": 0.45},
    locations={"garden": 1.00, "park": 0.80, "festival_ground": 0.95, "campsite": 0.90, "private_home": 0.45, "restaurant": 0.20},
    indoor_outdoor={"outdoor": 1.00, "mixed": 0.80, "indoor": 0.35},
    dayparts={},
    weather_conditions={},
    required_capabilities={"grill_or_equivalent"},
)

CURATED_CONTEXT_AFFINITIES: dict[str, ContextAffinity] = {
    "aperol_spritz": _APEROL_SPRITZ_AFFINITY,
    "bratwurst": _BRATWURST_AFFINITY,
}


def _recommendation_tags(item: object) -> set[str]:
    """Liest die tatsächlich befüllten Item-Tags. Katalog-Items führen ihre
    Tags in ``item.recommendation.tags`` (``RecommendationMetadata``), nicht
    im schlanken ``CatalogItem.tags`` (das im Katalog i.d.R. leer bleibt,
    siehe recommendation_tagging.py)."""
    meta = getattr(item, "recommendation", None)
    if meta is not None:
        meta_tags = getattr(meta, "tags", None)
        if meta_tags:
            return set(meta_tags)
    return set(getattr(item, "tags", []) or [])


def _synthesize_affinity(item: object) -> ContextAffinity:
    """Leitet eine ``ContextAffinity`` aus den (bislang ungenutzten)
    ``RecommendationMetadata``-Score-Feldern eines Items ab - Fallback für
    alle nicht kuratierten Items."""
    meta = getattr(item, "recommendation", None)
    if meta is None:
        return ContextAffinity()

    seasons = {
        "spring": meta.spring_score, "summer": meta.summer_score,
        "autumn": meta.autumn_score, "winter": meta.winter_score,
    }
    indoor_outdoor = {
        "indoor": meta.indoor_score, "outdoor": meta.outdoor_score,
        "mixed": round((meta.indoor_score + meta.outdoor_score) / 2, 4),
    }
    # RecommendationMetadata kennt nur 3 grobe Tageszeit-Buckets; auf die 6
    # zentralen Dayparts (§6) gemappt.
    dayparts = {
        "morning": meta.daytime_score, "brunch": meta.daytime_score,
        "daytime": meta.daytime_score, "afternoon": meta.daytime_score,
        "evening": meta.evening_score, "late_night": meta.late_night_score,
    }
    item_tags = _recommendation_tags(item)
    preferred_capabilities = item_tags & _KNOWN_CAPABILITY_TAGS

    return ContextAffinity(
        seasons=seasons,
        locations={},  # kein Location-Signal in RecommendationMetadata -> Tag-Overlap-Fallback (siehe _location_score)
        indoor_outdoor=indoor_outdoor,
        dayparts=dayparts,
        weather_conditions={},
        preferred_capabilities=preferred_capabilities,
    )


def get_context_affinity(item: object) -> ContextAffinity:
    """Liefert die ``ContextAffinity`` eines Items - kuratiert falls
    vorhanden, sonst automatisch aus ``RecommendationMetadata`` synthetisiert."""
    item_id = getattr(item, "id", None)
    if item_id in CURATED_CONTEXT_AFFINITIES:
        return CURATED_CONTEXT_AFFINITIES[item_id]
    return _synthesize_affinity(item)


def _location_score(item: object, derived_context: DerivedPartyContext, affinity: ContextAffinity) -> float:
    if derived_context.location_type in affinity.locations:
        return affinity.locations[derived_context.location_type]
    # Fallback: Tag-Overlap mit dem aktiven LocationProfile (§51).
    profile = get_location_profile(derived_context.location_type)
    item_tags = _recommendation_tags(item)
    preferred_hits = [w for t, w in profile.preferred_tags.items() if t in item_tags]
    discouraged_hits = [w for t, w in profile.discouraged_tags.items() if t in item_tags]
    if not preferred_hits and not discouraged_hits:
        return 0.5
    denom = max(1, len(preferred_hits) + len(discouraged_hits))
    score = 0.5 + 0.5 * (sum(preferred_hits) - sum(discouraged_hits)) / denom
    return max(0.0, min(1.0, score))


def calculate_context_fit(item: object, derived_context: DerivedPartyContext) -> ContextFitScore:
    """Berechnet den erklärbaren Context-Fit eines einzelnen Items (§42/§43).
    Hard Constraints (fehlende ``required_capabilities``) dominieren den
    Gesamtscore (§11) - das Item bleibt technisch wählbar, wird aber massiv
    heruntergestuft statt komplett entfernt."""
    affinity = get_context_affinity(item)
    reasons: list[str] = []
    penalties: list[str] = []

    season_score = affinity.seasons.get(derived_context.season, 0.5)
    if season_score >= 0.8:
        reasons.append(f"hoher Saison-Fit ('{derived_context.season}')")
    elif season_score <= 0.3:
        penalties.append(f"schwacher Saison-Fit ('{derived_context.season}')")

    location_score = _location_score(item, derived_context, affinity)
    if location_score >= 0.8:
        reasons.append(f"sehr passend zur Location '{derived_context.location_type}'")
    elif location_score <= 0.3:
        penalties.append(f"wenig passend zur Location '{derived_context.location_type}'")

    indoor_outdoor_score = affinity.indoor_outdoor.get(derived_context.indoor_outdoor, 0.5)
    if indoor_outdoor_score >= 0.8:
        reasons.append(f"gut für {derived_context.indoor_outdoor}")

    if derived_context.daypart_weights:
        daypart_score = sum(
            weight * affinity.dayparts.get(name, 0.5) for name, weight in derived_context.daypart_weights.items()
        )
    else:
        daypart_score = affinity.dayparts.get(derived_context.daypart_primary, 0.5)
    if daypart_score >= 0.8:
        reasons.append(f"passend zur Tageszeit ('{derived_context.daypart_primary}')")

    weather_score = 0.5
    if derived_context.weather_condition and affinity.weather_conditions:
        weather_score = affinity.weather_conditions.get(derived_context.weather_condition, 0.5)
    if derived_context.temperature_c is not None:
        if affinity.min_temperature_c is not None and derived_context.temperature_c < affinity.min_temperature_c:
            weather_score = min(weather_score, 0.25)
            penalties.append("unterhalb der bevorzugten Mindesttemperatur")
        if affinity.max_temperature_c is not None and derived_context.temperature_c > affinity.max_temperature_c:
            weather_score = min(weather_score, 0.25)
            penalties.append("oberhalb der bevorzugten Höchsttemperatur")

    infrastructure_score = 0.5
    missing_required = affinity.required_capabilities - derived_context.available_capabilities
    if affinity.required_capabilities:
        if missing_required:
            infrastructure_score = 0.05
            penalties.append(f"fehlende Infrastruktur: {', '.join(sorted(missing_required))}")
        else:
            infrastructure_score = 0.9
            reasons.append("vorhandene Kühlung/Infrastruktur")
    matched_preferred = affinity.preferred_capabilities & derived_context.available_capabilities
    if matched_preferred:
        infrastructure_score = min(1.0, infrastructure_score + 0.1 * len(matched_preferred))
        reasons.append("passende Infrastruktur vorhanden")
    elif affinity.preferred_capabilities and not affinity.required_capabilities:
        penalties.append("etwas Serviceaufwand ohne passende Infrastruktur")

    weights = config.CONTEXT_FIT_SUBSCORE_WEIGHTS
    total_score = (
        weights["season_score"] * season_score
        + weights["location_score"] * location_score
        + weights["indoor_outdoor_score"] * indoor_outdoor_score
        + weights["daypart_score"] * daypart_score
        + weights["weather_score"] * weather_score
        + weights["infrastructure_score"] * infrastructure_score
    )
    if missing_required:
        # Hard Constraint (§11) dominiert - Item bleibt wählbar, aber deutlich zurückgestuft.
        total_score = min(total_score, 0.15)

    return ContextFitScore(
        total_score=round(total_score, 4),
        season_score=round(season_score, 4),
        location_score=round(location_score, 4),
        indoor_outdoor_score=round(indoor_outdoor_score, 4),
        daypart_score=round(daypart_score, 4),
        weather_score=round(weather_score, 4),
        infrastructure_score=round(infrastructure_score, 4),
        penalties=penalties,
        reasons=reasons,
    )


if __name__ == "__main__":
    from dataclasses import dataclass, field as dc_field

    from party_context.engine import PartyContextEngine
    from party_context.domain import PartyContext

    @dataclass
    class _FakeMeta:
        spring_score: float = 0.5
        summer_score: float = 0.5
        autumn_score: float = 0.5
        winter_score: float = 0.5
        indoor_score: float = 0.5
        outdoor_score: float = 0.5
        daytime_score: float = 0.5
        evening_score: float = 0.5
        late_night_score: float = 0.5

    @dataclass
    class _FakeItem:
        id: str
        tags: list = dc_field(default_factory=list)
        recommendation: _FakeMeta = dc_field(default_factory=_FakeMeta)

    engine = PartyContextEngine()
    summer_garden = engine.derive_context(
        PartyContext(
            location_type="garden", indoor_outdoor="outdoor", has_grill=True, has_bar=False,
            expected_temperature_c=29.0, weather_condition="sunny",
        )
    )

    aperol = _FakeItem(id="aperol_spritz")
    fit = calculate_context_fit(aperol, summer_garden)
    assert fit.total_score > 0.7, fit
    assert any("Saison-Fit" in r for r in fit.reasons)

    bratwurst_with_grill = _FakeItem(id="bratwurst")
    fit_with_grill = calculate_context_fit(bratwurst_with_grill, summer_garden)
    assert fit_with_grill.infrastructure_score > 0.8
    assert not fit_with_grill.penalties or "fehlende Infrastruktur" not in " ".join(fit_with_grill.penalties)

    no_grill_ctx = engine.derive_context(PartyContext(location_type="garden", indoor_outdoor="outdoor", has_grill=False))
    fit_no_grill = calculate_context_fit(bratwurst_with_grill, no_grill_ctx)
    assert fit_no_grill.total_score < fit_with_grill.total_score
    assert "fehlende Infrastruktur: grill_or_equivalent" in fit_no_grill.penalties
    assert fit_no_grill.total_score <= 0.15

    # Synthetisiertes Item ohne Kuration - darf nicht crashen, liefert neutrale Werte.
    generic_item = _FakeItem(id="some_unknown_item", tags=["grill"])
    generic_fit = calculate_context_fit(generic_item, summer_garden)
    assert 0.0 <= generic_fit.total_score <= 1.0

    print(f"Aperol Spritz fit (summer garden) -> {fit}")
    print(f"Bratwurst fit (no grill) -> {fit_no_grill}")
    print("party_context/context_fit.py sanity check OK.")
