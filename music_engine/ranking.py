"""
TrackRanker Protocol + RuleBasedTrackRanker (Spec §49/§55-59/§70/§83-88).
=============================================================================

Transparentes, additiv gewichtetes Scoring (Spec §49):

    score = guest_preference_weight
          + 0.20 * occasion_fit
          + 0.20 * group_taste_fit
          + 0.15 * phase_fit
          + 0.10 * familiarity_fit
          + 0.10 * diversity_fit
          + 0.05 * admin_fit

``guest_preference_weight`` nutzt bewusst dieselbe Größenordnung wie
``resolver.SOURCE_WEIGHT`` (bis 10.0), damit angefragte Tracks im Score
deutlich dominieren können (Spec §49 Schlusssatz), während die übrigen
Komponenten in [0, 1] normiert sind und in Summe max. ~0.80 beitragen.

``TrackRanker`` ist als ``Protocol`` definiert, damit spätere Ranker
(``LearnedTrackRanker``, ``LLMReranker``, ``HybridTrackRanker`` - Spec
§83-88) dieselbe Pipeline nutzen können, ohne Candidate-Generation/Duration-/
Sequence-Optimizer anzufassen (Spec §83 "ohne die Kernarchitektur umbauen zu
müssen").
"""

from __future__ import annotations

from typing import Protocol

from music_engine.domain import (
    AdminArtistOverride,
    AdminMusicSettings,
    AdminTrackOverride,
    GroupMusicProfile,
    MusicCatalog,
    MusicOccasionProfile,
    MusicPhase,
    MusicTrack,
    TrackCandidate,
    TrackScore,
)
from music_engine.resolver import SOURCE_WEIGHT

# Spec §49: zentral konfigurierbare Gewichte.
SCORE_WEIGHTS: dict[str, float] = {
    "occasion_fit": 0.20,
    "group_taste_fit": 0.20,
    "phase_fit": 0.15,
    "familiarity_fit": 0.10,
    "diversity_fit": 0.10,
    "admin_fit": 0.05,
}

# Spec §55: Artist-Fairness-Defaults.
MAX_TRACKS_PER_ARTIST_AUTO = 3
MAX_CONSECUTIVE_SAME_ARTIST = 1
MIN_TRACK_DISTANCE_SAME_ARTIST = 10

# Spec §56/§57: Genre-/Era-Diversity-Defaults für allgemeine Partys.
MAX_DOMINANT_GENRE_SHARE = 0.40
MAX_DOMINANT_ERA_SHARE = 0.60

_REQUEST_SOURCES = {"guest_request", "multi_guest_request", "admin_must_play"}


def _simple_overlap(track_values: set[str], weighted: dict[str, float]) -> float:
    """Durchschnittsgewicht der übereinstimmenden Keys, geklemmt auf [0, 1].
    Einfacher, gut erklärbarer Overlap-Score (kein TF-IDF o.ä. nötig bei
    kleinen kontrollierten Vokabularen)."""
    if not track_values or not weighted:
        return 0.0
    matches = [weighted.get(v, 0.0) for v in track_values]
    matches = [m for m in matches if m > 0]
    if not matches:
        return 0.0
    return min(1.0, sum(matches) / len(matches))


def compute_occasion_fit(track: MusicTrack, occasion_profile: MusicOccasionProfile) -> float:
    genre_score = _simple_overlap(track.genres, occasion_profile.preferred_genres)
    era_score = _simple_overlap(track.eras, occasion_profile.preferred_eras)
    mood_score = _simple_overlap(track.moods, occasion_profile.preferred_moods)
    tag_score = _simple_overlap(track.tags, occasion_profile.preferred_tags)

    discouraged_genre_hit = bool(track.genres & set(occasion_profile.discouraged_genres))
    discouraged_tag_hit = bool(track.tags & set(occasion_profile.discouraged_tags))

    base = (genre_score * 0.35) + (era_score * 0.20) + (mood_score * 0.15) + (tag_score * 0.30)
    if discouraged_genre_hit:
        base *= 0.4
    if discouraged_tag_hit:
        base *= 0.6
    return round(min(1.0, base), 4)


def compute_group_taste_fit(track: MusicTrack, group_profile: GroupMusicProfile) -> float:
    if group_profile.confidence <= 0:
        return 0.0
    genre_score = _simple_overlap(track.genres, group_profile.genre_weights)
    era_score = _simple_overlap(track.eras, group_profile.era_weights)
    mood_score = _simple_overlap(track.moods, group_profile.mood_weights)
    artist_score = group_profile.artist_weights.get(track.artist, 0.0)

    base = (genre_score * 0.35) + (era_score * 0.25) + (mood_score * 0.15) + (artist_score * 0.25)
    # Spec §50: Vertrauen ins Gruppenprofil skaliert mit dessen confidence
    # (wenige Datenpunkte -> group_taste_fit bleibt gedämpft).
    return round(min(1.0, base) * group_profile.confidence, 4)


def compute_phase_fit(track: MusicTrack, phase: MusicPhase | None) -> float:
    if phase is None:
        return 0.5  # neutral, falls (noch) keiner Phase zugeordnet
    energy = track.energy_score if track.energy_score is not None else 0.5
    danceability = track.danceability_score if track.danceability_score is not None else 0.5

    energy_distance = abs(energy - phase.target_energy)
    danceability_distance = abs(danceability - phase.target_danceability)
    numeric_fit = 1.0 - min(1.0, (energy_distance * 0.6 + danceability_distance * 0.4))

    tag_fit = _simple_overlap(track.tags, phase.preferred_tags)
    return round(min(1.0, numeric_fit * 0.7 + tag_fit * 0.3), 4)


def compute_familiarity_fit(track: MusicTrack, admin_settings: AdminMusicSettings) -> float:
    # Spec §58 Admin-Slider "Bekannte Hits <-> Mehr Entdeckungen": hoher
    # mainstream_discovery-Wert = mehr Entdeckungen gewünscht -> niedrigeres
    # Ziel-familiarity_prior.
    target_familiarity = 1.0 - admin_settings.mainstream_discovery
    distance = abs(track.familiarity_prior - target_familiarity)
    return round(max(0.0, 1.0 - distance), 4)


def compute_admin_fit(
    track_id: str,
    artist: str,
    admin_track_overrides: dict[str, AdminTrackOverride],
    admin_artist_overrides: dict[str, AdminArtistOverride],
) -> float:
    track_override = admin_track_overrides.get(track_id)
    if track_override:
        if track_override.status == "must_play":
            return 1.0
        if track_override.status == "preferred":
            return 0.85
        if track_override.status in ("banned", "avoid"):
            return 0.0

    artist_override = admin_artist_overrides.get(artist.strip().lower())
    if artist_override:
        if artist_override.status in ("must_play", "preferred"):
            return 0.75
        if artist_override.status in ("banned", "avoid"):
            return 0.0

    return 0.5


def is_hard_excluded(
    track: MusicTrack,
    admin_settings: AdminMusicSettings,
    admin_track_overrides: dict[str, AdminTrackOverride],
    admin_artist_overrides: dict[str, AdminArtistOverride],
) -> bool:
    """Harte Ausschlüsse (kein Score-Malus, sondern kompletter Ausschluss):
    gebannte Genres, gebannte/"avoid"-Tracks/Artists, nicht erlaubte
    Explicit-Inhalte."""
    if track.genres & set(admin_settings.banned_genres):
        return True
    if admin_settings.explicit_allowed is False and track.explicit:
        return True

    track_override = admin_track_overrides.get(track.id)
    if track_override and track_override.status in ("banned", "avoid"):
        return True

    artist_override = admin_artist_overrides.get(track.artist.strip().lower())
    if artist_override and artist_override.status in ("banned", "avoid"):
        return True

    return False


def score_track(
    candidate: TrackCandidate,
    track: MusicTrack,
    occasion_profile: MusicOccasionProfile,
    group_profile: GroupMusicProfile,
    phase: MusicPhase | None,
    admin_settings: AdminMusicSettings,
    admin_track_overrides: dict[str, AdminTrackOverride] | None = None,
    admin_artist_overrides: dict[str, AdminArtistOverride] | None = None,
) -> TrackScore:
    admin_track_overrides = admin_track_overrides or {}
    admin_artist_overrides = admin_artist_overrides or {}

    guest_preference_weight = SOURCE_WEIGHT.get(candidate.source, SOURCE_WEIGHT["exploration"])
    occasion_fit = compute_occasion_fit(track, occasion_profile)
    group_taste_fit = compute_group_taste_fit(track, group_profile)
    phase_fit = compute_phase_fit(track, phase)
    familiarity_fit = compute_familiarity_fit(track, admin_settings)
    # diversity_fit: statischer neutraler Baseline-Wert auf Track-Score-Ebene
    # (echte Diversitäts-DURCHSETZUNG passiert kontext-abhängig, erst beim
    # greedy apply_diversity_constraints() über die bereits gewählten Tracks -
    # ein einzelner Track hat für sich genommen keinen "Diversity-Wert").
    diversity_fit = 0.5
    admin_fit = compute_admin_fit(track.id, track.artist, admin_track_overrides, admin_artist_overrides)

    total = (
        guest_preference_weight
        + SCORE_WEIGHTS["occasion_fit"] * occasion_fit
        + SCORE_WEIGHTS["group_taste_fit"] * group_taste_fit
        + SCORE_WEIGHTS["phase_fit"] * phase_fit
        + SCORE_WEIGHTS["familiarity_fit"] * familiarity_fit
        + SCORE_WEIGHTS["diversity_fit"] * diversity_fit
        + SCORE_WEIGHTS["admin_fit"] * admin_fit
    )

    reasons = _build_reasons(
        candidate, track, occasion_fit, group_taste_fit, phase_fit, phase, occasion_profile
    )

    return TrackScore(
        track_id=track.id,
        total_score=round(total, 4),
        guest_preference_weight=round(guest_preference_weight, 4),
        occasion_fit=occasion_fit,
        group_taste_fit=group_taste_fit,
        phase_fit=phase_fit,
        familiarity_fit=familiarity_fit,
        diversity_fit=diversity_fit,
        admin_fit=admin_fit,
        reasons=reasons,
        source=candidate.source,
        supporting_guests=set(candidate.supporting_guests),
    )


# --- Explainability (Spec §70) ------------------------------------------------

_DE_REASON_LABELS = {
    "multi_guest_request": "Von mehreren Gästen gewünscht.",
    "guest_request": "Von einem Gast gewünscht.",
    "admin_must_play": "Admin Must-Play.",
    "admin_preferred": "Vom Admin bevorzugt.",
    "occasion_fit": "Passt zum {occasion}-Profil.",
    "group_taste_fit": "Ähnliches Genre/Era wie eure häufig gewünschten Songs.",
    "phase_fit": "Geeignet für die {phase}-Phase.",
}


def _build_reasons(
    candidate: TrackCandidate,
    track: MusicTrack,
    occasion_fit: float,
    group_taste_fit: float,
    phase_fit: float,
    phase: MusicPhase | None,
    occasion_profile: MusicOccasionProfile,
) -> list[str]:
    reasons: list[str] = []
    if candidate.source in ("multi_guest_request", "guest_request", "admin_must_play", "admin_preferred"):
        reasons.append(_DE_REASON_LABELS[candidate.source])
    if occasion_fit >= 0.5:
        reasons.append(_DE_REASON_LABELS["occasion_fit"].format(occasion=occasion_profile.occasion_id))
    if group_taste_fit >= 0.5:
        reasons.append(_DE_REASON_LABELS["group_taste_fit"])
    if phase is not None and phase_fit >= 0.6:
        reasons.append(_DE_REASON_LABELS["phase_fit"].format(phase=phase.id))
    if not reasons:
        reasons.append("Passt allgemein zum Musikprofil der Party.")
    return reasons


# --- Diversity Constraints (Spec §55-57) --------------------------------------


def apply_diversity_constraints(
    scored: list[TrackScore],
    catalog: MusicCatalog,
    max_tracks_per_artist: int = MAX_TRACKS_PER_ARTIST_AUTO,
    max_dominant_genre_share: float = MAX_DOMINANT_GENRE_SHARE,
    max_dominant_era_share: float = MAX_DOMINANT_ERA_SHARE,
) -> list[TrackScore]:
    """Greedy Auswahl entlang der Score-Reihenfolge (Spec §55-57): setzt
    Artist-/Genre-/Era-Obergrenzen durch. Gästewünsche (``_REQUEST_SOURCES``)
    dürfen die Artist-Grenze überschreiten (Spec §55: "Guest Requests können
    Limits teilweise überschreiten"), automatisch ergänzte Songs halten sie
    strikt ein."""
    ordered = sorted(scored, key=lambda s: s.total_score, reverse=True)

    artist_counts: dict[str, int] = {}
    genre_counts: dict[str, int] = {}
    era_counts: dict[str, int] = {}
    admitted: list[TrackScore] = []

    for score in ordered:
        track = catalog.get_track(score.track_id)
        if track is None:
            continue

        is_request = score.source in _REQUEST_SOURCES
        total_admitted = len(admitted)

        if not is_request and artist_counts.get(track.artist, 0) >= max_tracks_per_artist:
            continue

        if not is_request and total_admitted >= 10:
            dominant_genre_violation = any(
                genre_counts.get(g, 0) + 1 > max_dominant_genre_share * (total_admitted + 1)
                for g in track.genres
            )
            if dominant_genre_violation:
                continue
            dominant_era_violation = any(
                era_counts.get(e, 0) + 1 > max_dominant_era_share * (total_admitted + 1) for e in track.eras
            )
            if dominant_era_violation:
                continue

        admitted.append(score)
        artist_counts[track.artist] = artist_counts.get(track.artist, 0) + 1
        for genre in track.genres:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
        for era in track.eras:
            era_counts[era] = era_counts.get(era, 0) + 1

    return admitted


class TrackRanker(Protocol):
    """Spec §83-88: austauschbares Ranking-Interface, damit später ein
    ``LearnedTrackRanker`` oder ``LLMReranker`` dieselbe Pipeline nutzen
    kann."""

    def rank(
        self,
        candidates: dict[str, TrackCandidate],
        catalog: MusicCatalog,
        occasion_profile: MusicOccasionProfile,
        group_profile: GroupMusicProfile,
        admin_settings: AdminMusicSettings,
        phase: MusicPhase | None = None,
        admin_track_overrides: dict[str, AdminTrackOverride] | None = None,
        admin_artist_overrides: dict[str, AdminArtistOverride] | None = None,
    ) -> list[TrackScore]:
        ...


class RuleBasedTrackRanker:
    """Referenzimplementierung: additiv gewichtetes, vollständig transparentes
    Scoring (Spec §49) ohne ML/LLM-Abhängigkeit."""

    def rank(
        self,
        candidates: dict[str, TrackCandidate],
        catalog: MusicCatalog,
        occasion_profile: MusicOccasionProfile,
        group_profile: GroupMusicProfile,
        admin_settings: AdminMusicSettings,
        phase: MusicPhase | None = None,
        admin_track_overrides: dict[str, AdminTrackOverride] | None = None,
        admin_artist_overrides: dict[str, AdminArtistOverride] | None = None,
    ) -> list[TrackScore]:
        admin_track_overrides = admin_track_overrides or {}
        admin_artist_overrides = admin_artist_overrides or {}

        scores: list[TrackScore] = []
        for track_id, candidate in candidates.items():
            track = catalog.get_track(track_id)
            if track is None:
                continue
            if is_hard_excluded(track, admin_settings, admin_track_overrides, admin_artist_overrides):
                continue
            scores.append(
                score_track(
                    candidate,
                    track,
                    occasion_profile,
                    group_profile,
                    phase,
                    admin_settings,
                    admin_track_overrides,
                    admin_artist_overrides,
                )
            )

        return sorted(scores, key=lambda s: s.total_score, reverse=True)


if __name__ == "__main__":
    from music_engine.catalog import load_music_catalog
    from music_engine.candidates import CandidateContext, generate_all_candidates
    from music_engine.domain import AdminMusicSettings, GroupMusicProfile, MusicStrategy
    from music_engine.occasions import get_music_occasion, load_all_music_occasions

    _catalog = load_music_catalog()
    _occasions = load_all_music_occasions()
    _grill = get_music_occasion("grill_party", _occasions)
    _strategy = MusicStrategy(
        occasion_id="grill_party",
        genre_weights=_grill.preferred_genres,
        era_weights=_grill.preferred_eras,
        tag_weights=_grill.preferred_tags,
    )
    _ctx = CandidateContext(catalog=_catalog, strategy=_strategy, admin_settings=AdminMusicSettings())
    _candidates = generate_all_candidates(_ctx)

    _ranker = RuleBasedTrackRanker()
    _scored = _ranker.rank(
        _candidates,
        _catalog,
        _grill,
        GroupMusicProfile(),
        AdminMusicSettings(),
    )
    print(f"Scored {len(_scored)} candidates. Top 5:")
    for s in _scored[:5]:
        track = _catalog.get_track(s.track_id)
        print(f"  {track.artist} - {track.title}: {s.total_score} ({s.source}) reasons={s.reasons}")

    _diverse = apply_diversity_constraints(_scored, _catalog)
    print(f"After diversity constraints: {len(_diverse)} tracks")
    assert len(_diverse) <= len(_scored)

    print("music_engine/ranking.py sanity check OK.")
