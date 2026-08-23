"""
Sequence Optimizer (Spec §66-69).
====================================

Nachdem der Duration Optimizer (music_engine/duration.py) entschieden hat,
WELCHE Tracks in die Playlist kommen, entscheidet dieses Modul in welcher
REIHENFOLGE sie gespielt werden. Selection Score (Spec §49) und
Sequenzierung sind bewusst getrennte Probleme (Spec §66: "Nicht Selection
Score mit Reihenfolge verwechseln.").

Ablauf:
    1. ``assign_tracks_to_phases``: jeder ausgewählte Track wird der Phase
       zugeordnet, zu der er am besten passt (``ranking.compute_phase_fit``),
       innerhalb des Zeitbudgets jeder Phase (Spec §69: Guest Requests
       landen NICHT automatisch alle am Anfang, sondern dort, wo sie
       energetisch/thematisch passen).
    2. ``classify_anchor_track``: markiert besonders bekannte
       Mitsing-/Peak-Songs als ``anchor_track`` (Spec §67).
    3. ``_order_phase_tracks``: ordnet die Tracks innerhalb jeder Phase per
       Greedy-Nearest-Neighbor über ``transition_cost`` (Spec §66), wobei
       Anchor Tracks bewusst über die Phase verteilt statt geclustert werden
       (Spec §67/§68 Mikro-Dramaturgie) - abrupte Übergänge sind dabei nicht
       grundsätzlich verboten, sondern nur bei Anchor-Häufung zusätzlich
       "bestraft".
    4. ``optimize_sequence``: orchestriert 1-3 und baut die finale
       ``PlaylistSlot``-Liste (Positionsnummern, phase_id, reasons).
"""

from __future__ import annotations

from music_engine.domain import MusicCatalog, MusicPhase, MusicTrack, PlaylistSlot, TrackScore
from music_engine.phases import phase_minutes
from music_engine.ranking import compute_phase_fit

# Spec §67: Anchor Tracks = besonders bekannte Partytracks, große
# Mitsing-Songs, starke Peak-Songs. Schwellen bewusst konservativ gewählt,
# damit nur eine kleine Teilmenge als Anchor gilt (sonst verliert die
# Spreizung ihren Sinn).
_ANCHOR_FAMILIARITY_MIN = 0.75
_ANCHOR_SINGALONG_MIN = 0.6
_ANCHOR_PARTY_SCORE_MIN = 0.7
_ANCHOR_TAGS = {"anthem", "singalong", "peak"}

# Transition-Cost Gewichte (Spec §66). Bewusst moderat, damit gelegentliche
# abrupte Übergänge (z.B. Peak-Wechsel) nicht komplett unterbunden werden
# ("Aber abrupte Übergänge nicht grundsätzlich verbieten.").
_GENRE_JUMP_PENALTY = 0.3
_MOOD_JUMP_PENALTY = 0.3
_ERA_JUMP_PENALTY = 0.2
_SAME_ARTIST_PENALTY = 0.6

_DEFAULT_TRACK_DURATION_MS = 210_000


def _track_duration(catalog: MusicCatalog, track_id: str) -> int:
    track = catalog.get_track(track_id)
    if track and track.duration_ms:
        return track.duration_ms
    return _DEFAULT_TRACK_DURATION_MS


def classify_anchor_track(track: MusicTrack) -> bool:
    """Spec §67: besonders bekannte Partytracks / große Mitsing-Songs /
    starke Peak-Songs. Reine Heuristik auf Basis vorhandener Katalogfelder,
    kein hartes Tag-Erfordernis (falls Tags fehlen, entscheiden die
    numerischen Scores allein)."""
    if track.familiarity_prior < _ANCHOR_FAMILIARITY_MIN:
        return False
    if track.party_score >= _ANCHOR_PARTY_SCORE_MIN:
        return True
    if track.singalong_score >= _ANCHOR_SINGALONG_MIN:
        return True
    if track.tags & _ANCHOR_TAGS:
        return True
    return False


def _track_energy(track: MusicTrack | None) -> float:
    if track is None or track.energy_score is None:
        return 0.5
    return track.energy_score


def transition_cost(a: MusicTrack, b: MusicTrack) -> float:
    """Spec §66: additive Kostenfunktion für den Übergang Track a -> b.
    Niedrigere Kosten = harmonischerer Übergang."""
    energy_jump_penalty = abs(_track_energy(a) - _track_energy(b))
    mood_jump_penalty = 0.0 if (a.moods & b.moods) else _MOOD_JUMP_PENALTY
    genre_jump_penalty = 0.0 if (a.genres & b.genres) else _GENRE_JUMP_PENALTY
    era_jump_penalty = 0.0 if (a.eras & b.eras) else _ERA_JUMP_PENALTY
    same_artist_penalty = _SAME_ARTIST_PENALTY if a.artist == b.artist else 0.0

    return (
        energy_jump_penalty
        + mood_jump_penalty
        + genre_jump_penalty
        + same_artist_penalty
        + era_jump_penalty
    )


def assign_tracks_to_phases(
    selected: list[TrackScore],
    catalog: MusicCatalog,
    phases: list[MusicPhase],
    total_minutes: float,
) -> dict[str, list[TrackScore]]:
    """Spec §69: ordnet jeden ausgewählten Track der Phase zu, zu der er am
    besten passt (``compute_phase_fit``), begrenzt durch das Zeitbudget der
    jeweiligen Phase. Guest Requests durchlaufen exakt dieselbe Logik wie
    empfohlene Tracks - sie landen also NICHT pauschal am Anfang.

    Kleiner Slack (5%) je Phasenbudget, damit knappe Rundungsfälle nicht
    unnötig Tracks in die letzte Phase verdrängen; verbleibende, nirgends
    passende Tracks landen sicherheitshalber in der letzten Phase, damit
    kein ausgewählter Track verloren geht."""
    if not phases:
        return {}

    capacities = {p.id: int(phase_minutes(p, total_minutes) * 60_000 * 1.05) for p in phases}
    filled = {p.id: 0 for p in phases}
    assignment: dict[str, list[TrackScore]] = {p.id: [] for p in phases}

    remaining = list(selected)
    for phase in phases:
        track_fit = {
            s.track_id: compute_phase_fit(catalog.get_track(s.track_id), phase) for s in remaining
        }
        remaining.sort(key=lambda s: track_fit[s.track_id], reverse=True)

        still_remaining: list[TrackScore] = []
        for score in remaining:
            duration = _track_duration(catalog, score.track_id)
            if filled[phase.id] + duration <= capacities[phase.id]:
                assignment[phase.id].append(score)
                filled[phase.id] += duration
            else:
                still_remaining.append(score)
        remaining = still_remaining

    if remaining:
        last_phase_id = phases[-1].id
        assignment[last_phase_id].extend(remaining)

    return assignment


def _anchor_slot_positions(n: int, k: int) -> set[int]:
    """Spec §67 "über die Party verteilen": berechnet ``k`` möglichst
    gleichmäßig über ``n`` Positionen verteilte Ziel-Slots für Anchor Tracks
    (z.B. n=19, k=8 -> Slots ~alle 2-3 Positionen). Reines Scheduling, nicht
    davon abhängig welcher konkrete Track später den Slot füllt."""
    if k <= 0 or n <= 0:
        return set()
    positions: set[int] = set()
    for i in range(k):
        pos = min(n - 1, round((i + 0.5) * n / k))
        while pos in positions and pos < n - 1:
            pos += 1
        positions.add(pos)
    return positions


def _order_phase_tracks(
    phase_scores: list[TrackScore], catalog: MusicCatalog, anchor_ids: set[str]
) -> list[TrackScore]:
    """Spec §66-68: sequenziert eine Phase in zwei kombinierten Schritten:

    1. Scheduling (Spec §67): Anchor Tracks bekommen im Voraus gleichmäßig
       verteilte Ziel-Positionen zugewiesen, damit sie nicht - wie bei
       reiner Greedy-Nearest-Neighbor-Suche - am Ende der Sequenz
       zusammenklumpen, sobald alle "einfachen" Nicht-Anchor-Übergänge
       aufgebraucht sind (Mikro-Dramaturgie statt "Peak Peak Peak Peak
       Peak", Spec §68).
    2. Cost-Minimierung (Spec §66): innerhalb der beiden Pools (Anchor /
       Nicht-Anchor) wird an jeder Position der Track mit der geringsten
       ``transition_cost`` zum Vorgänger gewählt.
    """
    if len(phase_scores) <= 1:
        return list(phase_scores)

    anchors_pool = sorted(
        (s for s in phase_scores if s.track_id in anchor_ids), key=lambda s: s.total_score, reverse=True
    )
    non_anchor_pool = sorted(
        (s for s in phase_scores if s.track_id not in anchor_ids), key=lambda s: s.total_score, reverse=True
    )

    n = len(phase_scores)
    anchor_slots = _anchor_slot_positions(n, len(anchors_pool))

    ordered: list[TrackScore] = []
    for position in range(n):
        want_anchor = position in anchor_slots
        pool = anchors_pool if want_anchor and anchors_pool else non_anchor_pool
        if not pool:
            pool = anchors_pool if anchors_pool else non_anchor_pool

        last_track = catalog.get_track(ordered[-1].track_id) if ordered else None
        best_idx = 0
        best_cost: float | None = None
        for idx, candidate in enumerate(pool):
            candidate_track = catalog.get_track(candidate.track_id)
            if last_track is None or candidate_track is None:
                cost = 0.5
            else:
                cost = transition_cost(last_track, candidate_track)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_idx = idx

        ordered.append(pool.pop(best_idx))

    return ordered


def optimize_sequence(
    selected: list[TrackScore],
    catalog: MusicCatalog,
    phases: list[MusicPhase],
    total_minutes: float,
) -> list[PlaylistSlot]:
    """Orchestriert Phasenzuordnung + Innerhalb-Phase-Sequenzierung und baut
    die finale, positionsnummerierte ``PlaylistSlot``-Liste (Spec §91)."""
    anchor_ids = {
        s.track_id
        for s in selected
        if (track := catalog.get_track(s.track_id)) is not None and classify_anchor_track(track)
    }

    phase_assignment = assign_tracks_to_phases(selected, catalog, phases, total_minutes)

    slots: list[PlaylistSlot] = []
    position = 1
    for phase in phases:
        ordered = _order_phase_tracks(phase_assignment.get(phase.id, []), catalog, anchor_ids)
        for score in ordered:
            slots.append(
                PlaylistSlot(
                    position=position,
                    phase_id=phase.id,
                    track_id=score.track_id,
                    source=score.source,
                    supporting_guests=sorted(score.supporting_guests),
                    recommendation_score=score.total_score,
                    reasons=list(score.reasons),
                )
            )
            position += 1

    return slots


if __name__ == "__main__":
    from music_engine.candidates import CandidateContext, generate_all_candidates
    from music_engine.catalog import load_music_catalog
    from music_engine.domain import AdminMusicSettings, GroupMusicProfile, MusicStrategy, RawSongRequest
    from music_engine.duration import select_tracks_for_duration
    from music_engine.occasions import get_music_occasion, load_all_music_occasions
    from music_engine.phases import compute_phases
    from music_engine.ranking import RuleBasedTrackRanker
    from music_engine.resolver import deduplicate_requests, resolve_song_requests

    _catalog = load_music_catalog()
    _occasions = load_all_music_occasions()
    _grill = get_music_occasion("grill_party", _occasions)
    _phases = compute_phases(120.0, _grill)
    _strategy = MusicStrategy(
        occasion_id="grill_party",
        genre_weights=_grill.preferred_genres,
        era_weights=_grill.preferred_eras,
        tag_weights=_grill.preferred_tags,
        phases=_phases,
    )

    tracks_pool = list(_catalog.tracks.values())[:60]
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

    _slots = optimize_sequence(_selected, _catalog, _phases, total_minutes=120.0)
    print(f"Sequenced {len(_slots)} slots across {len(_phases)} phases.")
    assert len(_slots) == len(_selected)
    assert [s.position for s in _slots] == list(range(1, len(_slots) + 1))

    # Spec §69: Guest Requests sollen nicht alle in der ersten Phase landen.
    request_phase_ids = {s.phase_id for s in _slots if s.source in {"guest_request", "multi_guest_request"}}
    print(f"Guest-requested tracks appear in phases: {sorted(request_phase_ids)}")
    assert len(request_phase_ids) > 1, "Guest requests sollten über mehrere Phasen verteilt sein"

    # Spec §67/68: Anchor Tracks sollen über die Phase verteilt statt
    # geclustert werden. Mathematisch ist Null-Adjazenz nur möglich, wenn
    # genug Nicht-Anchor-Tracks als "Trenner" existieren (k Anchors
    # brauchen mindestens k-1 Trenner) - das prüfen wir hart; darüber
    # hinaus bleibt es (bewusst, Spec §66 letzter Satz) ein weiches
    # Kriterium statt eines generellen Verbots abrupter Übergänge.
    _anchor_ids = {
        s.track_id for s in _selected if (t := _catalog.get_track(s.track_id)) and classify_anchor_track(t)
    }

    def _count_adjacent_anchors(track_ids: list[str]) -> int:
        return sum(
            1
            for prev_id, next_id in zip(track_ids, track_ids[1:])
            if prev_id in _anchor_ids and next_id in _anchor_ids
        )

    for phase in _phases:
        phase_slots = [s for s in _slots if s.phase_id == phase.id]
        track_ids = [s.track_id for s in phase_slots]
        k = sum(1 for tid in track_ids if tid in _anchor_ids)
        n = len(track_ids)
        optimized_adjacent = _count_adjacent_anchors(track_ids)
        naive_order = sorted(phase_slots, key=lambda s: s.recommendation_score, reverse=True)
        naive_adjacent = _count_adjacent_anchors([s.track_id for s in naive_order])
        separable = max(0, k - (n - k + 1))  # 0 falls genug Nicht-Anchors zum Trennen vorhanden
        print(
            f"  {phase.id}: anchors={k}/{n} adjacent optimized={optimized_adjacent} "
            f"naive={naive_adjacent} min_possible={separable}"
        )
        assert optimized_adjacent == separable, "Anchor-Verteilung nicht optimal trotz ausreichend Trennern"
        assert optimized_adjacent <= naive_adjacent

    for phase in _phases:
        phase_slots = [s for s in _slots if s.phase_id == phase.id]
        phase_ms = sum(_track_duration(_catalog, s.track_id) for s in phase_slots)
        print(f"  {phase.id}: {len(phase_slots)} tracks, {phase_ms/60000:.1f} min (budget {phase_minutes(phase, 120.0):.1f} min)")

    print("music_engine/sequence.py sanity check OK.")
