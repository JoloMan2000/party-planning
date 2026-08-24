"""
Music Director / Core Orchestration API (Spec §50/§90-92).
=================================================================

``plan_party_music()`` ist der einzige Einstiegspunkt, den "Party Planning.py"
aufrufen muss, um aus Songwünschen + Anlass + Partydauer + Admin-Settings eine
vollständige, sequenzierte Playlist zu erzeugen. Orchestriert exakt die in
Spec §92 vorgegebene interne Pipeline:

    resolve_song_requests()      -> resolver.py
    deduplicate_requests()       -> resolver.py (liefert zugleich die
                                     TrackPreferences, Spec-Schritt
                                     "build_track_preferences()" ist hier
                                     bereits im selben Aufruf enthalten)
    build_group_music_profile()  -> group_profile.py
    build_music_strategy()       -> dieses Modul (Bayesian-Blend Occasion x
                                     Gruppe, Spec §50)
    generate_candidates()        -> candidates.py (generate_all_candidates)
    score_candidates()           -> ranking.py (TrackRanker.rank)
    apply_guest_fairness()       -> fairness.py (wird von select_tracks_for_
                                     duration() intern aufgerufen, siehe
                                     duration.py Docstring - kein separater
                                     Schritt hier nötig)
    select_tracks_for_duration() -> duration.py
    assign_tracks_to_phases()    -> sequence.py (Teil von optimize_sequence())
    optimize_sequence()          -> sequence.py
    validate_playlist()          -> dieses Modul
    resolve_spotify_tracks()     -> BEWUSST NICHT hier: Spec §3/§13/§119
                                     ("Spotify lediglich als Resolver-/
                                     Export-Layer behandeln") - das interne
                                     PlaylistPlan/MusicPlanningResult bleibt
                                     rein auf ``track_id`` basiert. Die
                                     Spotify-Auflösung passiert erst im
                                     separaten Export-Schritt
                                     (music_engine/spotify_adapter.py), NICHT
                                     als Teil der Kernplanung - damit bleibt
                                     die Engine unabhängig von Spotify
                                     testbar/nutzbar (Spec §14 "später ...
                                     erweitert werden können").

    return MusicPlanningResult
"""

from __future__ import annotations

from music_engine.candidates import CandidateContext, MusicCandidateProvider, generate_all_candidates
from music_engine.domain import (
    AdminArtistOverride,
    AdminMusicSettings,
    AdminTrackOverride,
    GroupMusicProfile,
    MusicCatalog,
    MusicOccasionProfile,
    MusicPlanningResult,
    MusicStrategy,
    RawSongRequest,
    TrackScore,
)
from music_engine.duration import select_tracks_for_duration
from music_engine.fairness import compute_guest_coverage
from music_engine.group_profile import build_group_music_profile, compute_group_weight
from music_engine.phases import compute_phases
from music_engine.ranking import RuleBasedTrackRanker, TrackRanker
from music_engine.resolver import deduplicate_requests, resolve_song_requests
from music_engine.sequence import optimize_sequence
from party_context.domain import DerivedPartyContext, MusicContextModifiers

_DEFAULT_ADMIN_GENRE_BOOST = 0.3
_DEFAULT_ADMIN_GENRE_SUPPRESS = 0.3


def _blend_weights(
    occasion_weights: dict[str, float], group_weights: dict[str, float], occasion_share: float, group_share: float
) -> dict[str, float]:
    """Spec §50: gewichtete Mischung aus Anlass-Prior und Gruppenprofil über
    alle vorkommenden Keys."""
    keys = set(occasion_weights) | set(group_weights)
    blended = {
        key: round(occasion_weights.get(key, 0.0) * occasion_share + group_weights.get(key, 0.0) * group_share, 4)
        for key in keys
    }
    return blended


def _apply_admin_genre_bias(
    genre_weights: dict[str, float], admin_settings: AdminMusicSettings
) -> dict[str, float]:
    """Spec §61 Admin-UI "Checkbox/Boost/Suppress" je Genre - wirkt additiv
    auf die bereits geblendeten Gewichte, die in die Kandidatensuche
    einfließen (der harte Ausschluss von ``banned_genres`` passiert
    zusätzlich/unabhängig in ``ranking.is_hard_excluded``)."""
    adjusted = dict(genre_weights)
    for genre in admin_settings.preferred_genres:
        adjusted[genre] = min(1.0, adjusted.get(genre, 0.0) + _DEFAULT_ADMIN_GENRE_BOOST)
    for genre in admin_settings.discouraged_genres:
        adjusted[genre] = max(0.0, adjusted.get(genre, 0.0) - _DEFAULT_ADMIN_GENRE_SUPPRESS)
    for genre in admin_settings.banned_genres:
        adjusted[genre] = 0.0
    return adjusted


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _apply_music_context_modifiers(
    genre_weights: dict[str, float],
    tag_weights: dict[str, float],
    mood_weights: dict[str, float],
    energy_target: float,
    danceability_target: float,
    phases: list,
    modifiers: MusicContextModifiers,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], float, float, list]:
    """§30-37 (Party-Context-Engine-Spec): ``MusicContextModifiers`` wirken
    AUSSCHLIESSLICH auf Genre-Gewichte/Energy-Curve/Danceability/
    Phasen-Strategie - niemals auf die Musikmenge (§66, kein
    Demand-Multiplier-Feld auf ``MusicContextModifiers``, die Trackanzahl
    ergibt sich ausschließlich aus der Partydauer, siehe
    ``select_tracks_for_duration``). Gibt neue, unabhängige Kopien zurück
    (kein In-Place-Mutieren der vom Aufrufer übergebenen Dicts/Listen)."""
    from dataclasses import replace as _replace

    genre_weights = dict(genre_weights)
    tag_weights = dict(tag_weights)
    mood_weights = dict(mood_weights)

    energy_target = _clamp01(energy_target + modifiers.energy_modifier)
    danceability_target = _clamp01(danceability_target + modifiers.danceability_modifier)

    if modifiers.bass_penalty > 0:
        tag_weights["bass_heavy"] = max(0.0, tag_weights.get("bass_heavy", 0.0) - modifiers.bass_penalty)

    if modifiers.conversation_modifier != 0:
        tag_weights["conversation_friendly"] = _clamp01(
            tag_weights.get("conversation_friendly", 0.0) + modifiers.conversation_modifier
        )
        mood_weights["chill"] = _clamp01(mood_weights.get("chill", 0.0) + modifiers.conversation_modifier)
        mood_weights["relaxed"] = _clamp01(mood_weights.get("relaxed", 0.0) + modifiers.conversation_modifier)

    if modifiers.outdoor_modifier != 0:
        tag_weights["dancefloor"] = _clamp01(tag_weights.get("dancefloor", 0.0) + modifiers.outdoor_modifier)

    if modifiers.late_night_energy_penalty > 0:
        phases = [
            _replace(phase, target_energy=max(0.0, phase.target_energy - modifiers.late_night_energy_penalty))
            if phase.id in ("late", "closing")
            else phase
            for phase in phases
        ]

    return genre_weights, tag_weights, mood_weights, energy_target, danceability_target, phases


def build_music_strategy(
    occasion_profile: MusicOccasionProfile,
    group_profile: GroupMusicProfile,
    admin_settings: AdminMusicSettings,
    total_minutes: float,
    derived_context: DerivedPartyContext | None = None,
) -> MusicStrategy:
    """Spec §50: verschmilzt den statischen Anlass-Prior mit dem aus den
    Songwünschen abgeleiteten Gruppenprofil per Bayesian Shrinkage
    (``group_weight = request_count / (request_count + 15)``) und berechnet
    daraus die konkreten Party-Phasen (Spec §46/§47).

    ``derived_context`` (§77 Party-Context-Engine-Spec, optional): wird
    ``derived_context.music_modifiers`` über ``_apply_music_context_modifiers``
    NACH dem Occasion/Gruppen-Blend angewendet (eigene Schicht, ändert nie
    die Musikmenge). Bleibt ``None`` (Standard), ist das Verhalten
    unverändert zur bisherigen Formel."""
    group_weight = compute_group_weight(group_profile.request_count)
    occasion_share = 1.0 - group_weight

    genre_weights = _blend_weights(
        occasion_profile.preferred_genres, group_profile.genre_weights, occasion_share, group_weight
    )
    genre_weights = _apply_admin_genre_bias(genre_weights, admin_settings)
    era_weights = _blend_weights(
        occasion_profile.preferred_eras, group_profile.era_weights, occasion_share, group_weight
    )
    mood_weights = _blend_weights(
        occasion_profile.preferred_moods, group_profile.mood_weights, occasion_share, group_weight
    )

    occasion_energy = (
        sum(occasion_profile.energy_curve.values()) / len(occasion_profile.energy_curve)
        if occasion_profile.energy_curve
        else 0.5
    )
    energy_target = occasion_energy * occasion_share + group_profile.energy_target * group_weight
    danceability_target = (
        occasion_profile.danceability_target * occasion_share + group_profile.danceability_target * group_weight
    )
    familiarity_target = (
        occasion_profile.familiarity_target * occasion_share + group_profile.familiarity_target * group_weight
    )

    explicit_policy = occasion_profile.default_explicit_policy
    if not admin_settings.explicit_allowed:
        explicit_policy = "ban"

    phases = compute_phases(total_minutes, occasion_profile)
    tag_weights = dict(occasion_profile.preferred_tags)

    if derived_context is not None:
        genre_weights, tag_weights, mood_weights, energy_target, danceability_target, phases = (
            _apply_music_context_modifiers(
                genre_weights,
                tag_weights,
                mood_weights,
                energy_target,
                danceability_target,
                phases,
                derived_context.music_modifiers,
            )
        )

    return MusicStrategy(
        occasion_id=occasion_profile.occasion_id,
        genre_weights=genre_weights,
        era_weights=era_weights,
        mood_weights=mood_weights,
        tag_weights=tag_weights,
        familiarity_target=round(familiarity_target, 4),
        danceability_target=round(danceability_target, 4),
        energy_target=round(energy_target, 4),
        phases=phases,
        group_weight=round(group_weight, 4),
        explicit_policy=explicit_policy,
    )


def validate_playlist(
    selected: list[TrackScore],
    actual_duration_ms: int,
    target_duration_ms: int,
    tolerance: float,
    unresolved_requests: list,
    guests_covered: int,
    guests_total: int,
) -> list[str]:
    """Spec §70/§71-ähnliche Review-Hinweise für das Admin-Dashboard - rein
    additive Warnungen, blockieren nichts (die Playlist wird trotzdem
    zurückgegeben, damit der Admin selbst entscheidet)."""
    issues: list[str] = []

    if not selected:
        issues.append("Keine Tracks ausgewählt - die Playlist ist leer.")

    if target_duration_ms > 0:
        deviation = abs(actual_duration_ms - target_duration_ms) / target_duration_ms
        if deviation > tolerance * 1.5:
            issues.append(
                f"Ist-Dauer weicht um {deviation * 100:.1f}% vom Ziel ab "
                f"(Toleranz: ±{tolerance * 100:.1f}%)."
            )

    if unresolved_requests:
        issues.append(
            f"{len(unresolved_requests)} Songwünsche konnten nicht sicher aufgelöst werden "
            "und benötigen manuelle Prüfung."
        )

    if guests_total > 0 and guests_covered / guests_total < 0.5:
        issues.append(
            f"Nur {guests_covered}/{guests_total} Gäste mit Songwunsch sind in der finalen "
            "Playlist vertreten."
        )

    return issues


def plan_party_music(
    raw_song_requests: list[RawSongRequest],
    party_duration_minutes: float,
    occasion_profile: MusicOccasionProfile,
    admin_settings: AdminMusicSettings,
    catalog: MusicCatalog,
    admin_track_overrides: dict[str, AdminTrackOverride] | None = None,
    admin_artist_overrides: dict[str, AdminArtistOverride] | None = None,
    providers: list[MusicCandidateProvider] | None = None,
    ranker: TrackRanker | None = None,
    derived_context: DerivedPartyContext | None = None,
) -> MusicPlanningResult:
    """Kern-API der Music Recommendation & Party Playlist Engine (Spec §92).
    Nimmt rohe Songwünsche + Partydauer + Anlass + Admin-Settings entgegen und
    liefert eine vollständig geplante, sequenzierte ``MusicPlanningResult``.

    ``derived_context`` (§76/§77 Party-Context-Engine-Spec, optional): wird
    unverändert an ``build_music_strategy`` durchgereicht (eigene additive
    Modifier-Schicht auf Energy/Danceability/Genre-/Tag-Gewichte/
    Late-Night-Phase, §30-37) - ändert NIE die Musikmenge (§66)."""
    admin_track_overrides = admin_track_overrides or {}
    admin_artist_overrides = admin_artist_overrides or {}
    ranker = ranker or RuleBasedTrackRanker()

    # 1-2. Resolution + Dedup (Spec §7-9).
    resolved_requests = resolve_song_requests(raw_song_requests, catalog)
    track_preferences, unresolved_requests = deduplicate_requests(resolved_requests)

    # 3. Gruppenprofil (Spec §17/§18).
    group_profile = build_group_music_profile(track_preferences, catalog)

    # 4. Zieldauer (Spec §13): Partydauer * (1 + Puffer).
    target_minutes = party_duration_minutes * (1.0 + admin_settings.playlist_duration_buffer)

    # 5. Strategie (Bayesian-Blend Occasion x Gruppe + Phasen, Spec §46/§50).
    strategy = build_music_strategy(
        occasion_profile, group_profile, admin_settings, target_minutes, derived_context=derived_context
    )

    # 6. Kandidaten (Spec §51/§52).
    ctx = CandidateContext(
        catalog=catalog,
        strategy=strategy,
        track_preferences=track_preferences,
        admin_settings=admin_settings,
        admin_track_overrides=admin_track_overrides,
        admin_artist_overrides=admin_artist_overrides,
    )
    candidates = generate_all_candidates(ctx, providers=providers)

    # 7. Scoring (Spec §49; phase=None hier, da die Selektion phasenunabhängig
    # erfolgt - die Phasenzuordnung passiert erst nach der Dauer-Optimierung,
    # siehe compute_phase_fit()-Docstring in ranking.py).
    scored = ranker.rank(
        candidates,
        catalog,
        occasion_profile,
        group_profile,
        admin_settings,
        phase=None,
        admin_track_overrides=admin_track_overrides,
        admin_artist_overrides=admin_artist_overrides,
    )

    # 8-9. Fairness-bewusste Dauer-Optimierung (Spec §11/§12/§15/§65).
    selected, actual_duration_ms, dropped_track_ids = select_tracks_for_duration(
        scored, resolved_requests, track_preferences, catalog, target_minutes,
    )

    # 10-11. Phasenzuordnung + Sequenzierung (Spec §66-69).
    slots = optimize_sequence(selected, catalog, strategy.phases, target_minutes)

    # 12. Guest Coverage (Spec §72).
    guests_covered, guests_total = compute_guest_coverage(resolved_requests, [s.track_id for s in selected])
    guest_coverage = (guests_covered / guests_total) if guests_total > 0 else 0.0

    requested_track_ids = set(track_preferences.keys())
    requested_selected_ids = requested_track_ids & {s.track_id for s in selected}

    # 13. Validierung / Review-Hinweise (Spec §70/§71).
    review_issues = validate_playlist(
        selected,
        actual_duration_ms,
        int(target_minutes * 60_000),
        tolerance=0.025,
        unresolved_requests=unresolved_requests,
        guests_covered=guests_covered,
        guests_total=guests_total,
    )

    explanations = [
        f"Zieldauer: {target_minutes:.1f} min (Partydauer {party_duration_minutes:.0f} min "
        f"+ {admin_settings.playlist_duration_buffer * 100:.0f}% Puffer).",
        f"Ist-Dauer: {actual_duration_ms / 60_000:.1f} min mit {len(selected)} Tracks.",
        f"{len(requested_selected_ids)}/{len(requested_track_ids)} angefragte Songs in der finalen "
        "Playlist berücksichtigt, Rest via intelligenter Fairness-/Zeitbudget-Reduktion "
        "zurückgestellt (nicht gelöscht).",
        f"Gäste-Abdeckung: {guests_covered}/{guests_total} Gäste mit mindestens einem "
        "ihrer Songwünsche in der Playlist.",
    ]

    return MusicPlanningResult(
        target_duration_ms=int(target_minutes * 60_000),
        actual_duration_ms=actual_duration_ms,
        total_tracks=len(slots),
        requested_tracks_selected=len(requested_selected_ids),
        requested_tracks_total=len(requested_track_ids),
        guest_coverage=round(guest_coverage, 4),
        phases=strategy.phases,
        playlist=slots,
        group_profile=group_profile,
        unresolved_requests=unresolved_requests,
        review_issues=review_issues,
        explanations=explanations,
        model_version=strategy.model_version,
        requested_songs_total_count=len(requested_track_ids),
        requested_songs_fitting_count=len(requested_selected_ids),
        unique_guests_with_requests=guests_total,
        unique_guests_covered=guests_covered,
    )


if __name__ == "__main__":
    from music_engine.catalog import load_music_catalog
    from music_engine.occasions import get_music_occasion, load_all_music_occasions

    _catalog = load_music_catalog()
    _occasions = load_all_music_occasions()
    _grill = get_music_occasion("grill_party", _occasions)

    # Spec §99: 2h Party, aber 4h an Songwünschen -> muss intelligent reduzieren.
    tracks_pool = list(_catalog.tracks.values())[:80]
    _raw = [
        RawSongRequest(guest_id=f"Gast{i % 12}", text=t.title, artist_hint=t.artist, title_hint=t.title)
        for i, t in enumerate(tracks_pool)
    ]

    _result = plan_party_music(
        raw_song_requests=_raw,
        party_duration_minutes=120.0,
        occasion_profile=_grill,
        admin_settings=AdminMusicSettings(),
        catalog=_catalog,
    )

    print(
        f"Target: {_result.target_duration_ms / 60000:.1f} min, "
        f"actual: {_result.actual_duration_ms / 60000:.1f} min, "
        f"tracks: {_result.total_tracks}"
    )
    print(f"Requested: {_result.requested_tracks_selected}/{_result.requested_tracks_total} selected.")
    print(f"Guest coverage: {_result.unique_guests_covered}/{_result.unique_guests_with_requests}")
    print(f"Phases: {[p.id for p in _result.phases]}")
    print(f"Review issues: {_result.review_issues}")
    for line in _result.explanations:
        print(f"  - {line}")

    assert _result.total_tracks > 0
    assert _result.actual_duration_ms <= _result.target_duration_ms * 1.03
    assert [s.position for s in _result.playlist] == list(range(1, len(_result.playlist) + 1))
    assert _result.unique_guests_with_requests == 12
    assert _result.unique_guests_covered >= 1

    print("music_engine/engine.py sanity check OK.")
