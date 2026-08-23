"""
Gast-Fairness-Auswahl (Spec §11/§12/§97).
=============================================

Ein Gast darf nicht durch viele eingetragene Songwünsche die ganze Playlist
dominieren (Spec §97 Testfall: Gast A mit 30 Wünschen, Gäste B-J mit je 1
Wunsch - bei ausreichender Playlist-Zeit dürfen B-J nicht verdrängt werden).

Strategie (Spec §11): Round-Robin über die Gäste-Wunschlisten -
Runde 1 = erster (kompatibler) Wunsch jedes Gastes, Runde 2 = zweiter Wunsch
jedes Gastes usw. Songs mit mehreren unterstützenden Gästen (Multi-Guest-
Requests) werden weiterhin stark bevorzugt (Spec §98) - sie werden vor dem
Round-Robin an den Anfang gestellt, damit sie unabhängig davon priorisiert
bleiben, in wessen "Runde" sie zufällig zuerst auftauchen.
"""

from __future__ import annotations

from music_engine.domain import ResolvedSongRequest, TrackPreference


def compute_fairness_bonus(already_selected_requests_for_guest: int) -> float:
    """Spec §12: ``fairness_bonus = 1 / (1 + already_selected_requests_for_guest)``.
    Je mehr Songs eines Gastes bereits eingeplant sind, desto geringer der
    Bonus für einen weiteren Song desselben Gastes."""
    return 1.0 / (1.0 + already_selected_requests_for_guest)


def _build_guest_wishlists(resolved_requests: list[ResolvedSongRequest]) -> dict[str, list[str]]:
    """Baut je Gast eine deduplizierte, reihenfolgeerhaltende Liste der von
    ihm gewünschten ``track_id``s (nur aufgelöste Requests mit ``track_id``)."""
    wishlists: dict[str, list[str]] = {}
    for resolved in resolved_requests:
        if not resolved.track_id:
            continue
        guest_tracks = wishlists.setdefault(resolved.guest_id, [])
        if resolved.track_id not in guest_tracks:
            guest_tracks.append(resolved.track_id)
    return wishlists


def order_requested_tracks_with_fairness(
    resolved_requests: list[ResolvedSongRequest],
    track_preferences: dict[str, TrackPreference],
) -> list[str]:
    """Liefert alle angefragten ``track_id``s in einer fairnessbewussten
    Prioritätsreihenfolge (Spec §11/§12/§97/§98):

    1. Multi-Guest-Requests zuerst, sortiert nach Anzahl unterstützender
       Gäste (absteigend) - sie sollen nie durch Round-Robin-Zufall
       verdrängt werden (Spec §98).
    2. Danach alle übrigen (Single-Guest-)Requests im Round-Robin-Verfahren:
       Runde 1 = je ein Wunsch pro Gast, Runde 2 = zweiter Wunsch pro Gast,
       usw. (Spec §11).

    Diese Reihenfolge ist eine reine Priorisierung - ob am Ende tatsächlich
    alle Tracks in die Playlist passen, entscheidet erst der Duration
    Optimizer (music_engine/duration.py).
    """
    wishlists = _build_guest_wishlists(resolved_requests)
    guest_order = list(wishlists.keys())  # Reihenfolge = erstes Auftreten (deterministisch)

    multi_guest_tracks = sorted(
        (tid for tid, pref in track_preferences.items() if len(pref.supporting_guests) > 1),
        key=lambda tid: len(track_preferences[tid].supporting_guests),
        reverse=True,
    )

    ordered: list[str] = []
    seen: set[str] = set()
    for track_id in multi_guest_tracks:
        if track_id not in seen:
            ordered.append(track_id)
            seen.add(track_id)

    round_idx = 0
    remaining = True
    while remaining:
        remaining = False
        for guest_id in guest_order:
            guest_tracks = wishlists[guest_id]
            if round_idx < len(guest_tracks):
                remaining = True
                track_id = guest_tracks[round_idx]
                if track_id not in seen:
                    ordered.append(track_id)
                    seen.add(track_id)
        round_idx += 1

    return ordered


def compute_guest_coverage(
    resolved_requests: list[ResolvedSongRequest], selected_track_ids: list[str]
) -> tuple[int, int]:
    """Liefert (guests_covered, total_requesting_guests): wie viele Gäste mit
    mindestens einem aufgelösten Songwunsch haben mindestens einen ihrer
    gewünschten Tracks in der finalen Playlist (Spec §72 Guest Request
    Coverage)."""
    wishlists = _build_guest_wishlists(resolved_requests)
    if not wishlists:
        return 0, 0
    selected_set = set(selected_track_ids)
    covered = sum(1 for tracks in wishlists.values() if selected_set.intersection(tracks))
    return covered, len(wishlists)


if __name__ == "__main__":
    from music_engine.catalog import load_music_catalog
    from music_engine.domain import RawSongRequest
    from music_engine.resolver import deduplicate_requests, resolve_song_requests

    _catalog = load_music_catalog()
    tracks_pool = list(_catalog.tracks.values())[:40]

    # Spec §97: Gast A mit 30 Wünschen, Gäste B-J (9 Gäste) mit je 1 Wunsch.
    _raw: list[RawSongRequest] = []
    for i in range(30):
        track = tracks_pool[i % len(tracks_pool)]
        _raw.append(RawSongRequest(guest_id="GastA", text=track.title, artist_hint=track.artist, title_hint=track.title))
    for letter_idx, guest in enumerate("BCDEFGHIJ"):
        track = tracks_pool[(30 + letter_idx) % len(tracks_pool)]
        _raw.append(RawSongRequest(guest_id=f"Gast{guest}", text=track.title, artist_hint=track.artist, title_hint=track.title))

    _resolved = resolve_song_requests(_raw, _catalog)
    _prefs, _ = deduplicate_requests(_resolved)
    _ordered = order_requested_tracks_with_fairness(_resolved, _prefs)

    # Die ersten 9 Einträge (Runde 1) müssen GastA UND alle 9 anderen Gäste
    # abdecken (round-robin garantiert: jeder Gast kommt spätestens in
    # Runde 1 einmal dran, bevor GastA seinen zweiten Song bekommt).
    first_round = _ordered[:10]
    wishlists = _build_guest_wishlists(_resolved)
    covered_in_first_round = set()
    for guest_id, guest_tracks in wishlists.items():
        if guest_tracks and guest_tracks[0] in first_round:
            covered_in_first_round.add(guest_id)
    print(f"Guests covered within first round-robin pass: {len(covered_in_first_round)}/10")
    assert len(covered_in_first_round) == 10, covered_in_first_round

    print("music_engine/fairness.py sanity check OK.")
