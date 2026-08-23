"""
Playlist Duration Optimizer (Spec §13-16/§65/§99-101).
===========================================================

Wählt aus den gescorten Kandidaten (``TrackScore``, bereits sortiert nach
Gesamtscore) eine finale Trackliste, die das Zeitbudget der Party (Spec §13:
Partydauer * Puffer) möglichst genau trifft (Spec §65: Toleranz ±2-3%, statt
stumpf bis zum Überschreiten aufzufüllen).

Priorisierung bei zu vielen Songwünschen (Spec §15):
    1. Admin Must Play
    2. Multi-Guest-Requests
    3. Fairness-Runde 1..n (ein Wunsch pro Gast, dann der zweite, ...)
    4-6. Group Taste Fit / Occasion Fit / Phase Fit (= Score-Reihenfolge der
         übrigen Empfehlungen)
    7. Weitere Einzelwünsche (bereits in Runde 2..n der Fairness-Reihenfolge
       enthalten)

Kein Songwunsch wird dabei aus der Datenbank gelöscht (Spec §8) - nicht
ausgewählte Requests werden lediglich nicht in die finale Playlist
übernommen (``dropped_track_ids`` im Rückgabewert) und bleiben für
Coverage-Statistiken/Review sichtbar.
"""

from __future__ import annotations

from music_engine.domain import MusicCatalog, ResolvedSongRequest, TrackPreference, TrackScore
from music_engine.fairness import order_requested_tracks_with_fairness
from music_engine.ranking import apply_diversity_constraints

_DEFAULT_TRACK_DURATION_MS = 210_000  # 3:30 Fallback, falls duration_ms unbekannt
_DEFAULT_TOLERANCE = 0.025  # Spec §65: ±2-3%


def _track_duration(catalog: MusicCatalog, track_id: str) -> int:
    track = catalog.get_track(track_id)
    if track and track.duration_ms:
        return track.duration_ms
    return _DEFAULT_TRACK_DURATION_MS


def select_tracks_for_duration(
    scored: list[TrackScore],
    resolved_requests: list[ResolvedSongRequest],
    track_preferences: dict[str, TrackPreference],
    catalog: MusicCatalog,
    target_minutes: float,
    tolerance: float = _DEFAULT_TOLERANCE,
) -> tuple[list[TrackScore], int, list[str]]:
    """Liefert ``(selected_scores, actual_duration_ms, dropped_track_ids)``.

    ``selected_scores`` ist in Prioritätsreihenfolge (Admin Must Play ->
    Multi-Guest -> Fairness-Runden -> übrige Empfehlungen score-sortiert),
    NICHT in Wiedergabereihenfolge - die eigentliche Sequenzierung übernimmt
    music_engine/sequence.py.
    """
    score_by_id = {s.track_id: s for s in scored}
    target_ms = int(max(target_minutes, 0.0) * 60_000)
    upper_bound_ms = int(target_ms * (1 + tolerance))

    admin_must_play_ids = sorted(
        (s.track_id for s in scored if s.source == "admin_must_play"),
        key=lambda tid: score_by_id[tid].total_score,
        reverse=True,
    )

    fairness_order = order_requested_tracks_with_fairness(resolved_requests, track_preferences)
    admin_must_play_set = set(admin_must_play_ids)
    fairness_order = [tid for tid in fairness_order if tid not in admin_must_play_set and tid in score_by_id]

    requested_priority_ids = admin_must_play_ids + fairness_order
    requested_id_set = set(requested_priority_ids)

    filler_scores = [s for s in scored if s.track_id not in requested_id_set]
    filler_scores = apply_diversity_constraints(filler_scores, catalog)

    ordered_candidate_ids = requested_priority_ids + [s.track_id for s in filler_scores]

    selected: list[str] = []
    skipped: list[str] = []
    total_ms = 0

    for track_id in ordered_candidate_ids:
        duration = _track_duration(catalog, track_id)
        if total_ms + duration <= upper_bound_ms:
            selected.append(track_id)
            total_ms += duration
        else:
            skipped.append(track_id)

    # Look-ahead Fill (Spec §65): manche spätere, kürzere Kandidaten passen
    # eventuell noch in die verbleibende Lücke, obwohl ein früherer, größerer
    # Kandidat nicht mehr gepasst hat - so wird die Zieldauer möglichst genau
    # getroffen statt konservativ unterschritten.
    still_skipped: list[str] = []
    for track_id in skipped:
        duration = _track_duration(catalog, track_id)
        if total_ms + duration <= upper_bound_ms:
            selected.append(track_id)
            total_ms += duration
        else:
            still_skipped.append(track_id)

    selected_scores = [score_by_id[tid] for tid in selected if tid in score_by_id]
    return selected_scores, total_ms, still_skipped


if __name__ == "__main__":
    from music_engine.candidates import CandidateContext, generate_all_candidates
    from music_engine.catalog import load_music_catalog
    from music_engine.domain import AdminMusicSettings, GroupMusicProfile, MusicStrategy, RawSongRequest
    from music_engine.occasions import get_music_occasion, load_all_music_occasions
    from music_engine.ranking import RuleBasedTrackRanker
    from music_engine.resolver import deduplicate_requests, resolve_song_requests

    _catalog = load_music_catalog()
    _occasions = load_all_music_occasions()
    _grill = get_music_occasion("grill_party", _occasions)
    _strategy = MusicStrategy(
        occasion_id="grill_party",
        genre_weights=_grill.preferred_genres,
        era_weights=_grill.preferred_eras,
        tag_weights=_grill.preferred_tags,
    )

    # Spec §99: 2h Party, aber 4h an Songwünschen -> muss intelligent reduzieren.
    tracks_pool = list(_catalog.tracks.values())[:80]
    _raw = [
        RawSongRequest(guest_id=f"Gast{i}", text=t.title, artist_hint=t.artist, title_hint=t.title)
        for i, t in enumerate(tracks_pool)
    ]
    _resolved = resolve_song_requests(_raw, _catalog)
    _prefs, _ = deduplicate_requests(_resolved)

    _ctx = CandidateContext(catalog=_catalog, strategy=_strategy, track_preferences=_prefs, admin_settings=AdminMusicSettings())
    _candidates = generate_all_candidates(_ctx)
    _scored = RuleBasedTrackRanker().rank(_candidates, _catalog, _grill, GroupMusicProfile(), AdminMusicSettings())

    _selected, _actual_ms, _dropped = select_tracks_for_duration(
        _scored, _resolved, _prefs, _catalog, target_minutes=120.0
    )
    print(f"Target: 120 min. Selected {len(_selected)} tracks, actual={_actual_ms/60000:.1f} min, dropped={len(_dropped)}")
    assert _actual_ms <= 120 * 60_000 * 1.03
    assert len(_selected) > 0

    print("music_engine/duration.py sanity check OK.")
