"""
GroupMusicProfile-Builder (Spec §17-18/§50).
================================================

Leitet aus den deduplizierten ``TrackPreference``-Objekten (siehe resolver.py)
ein ``GroupMusicProfile`` ab: Genre-/Era-/Mood-/Sprache-/Artist-Gewichte sowie
Energy-/Danceability-/Familiarity-/Singalong-Targets.

Zentrale Regel (Spec §18): "Wenn ein Gast zehn Techno-Songs einträgt, soll
dies weniger Gewicht haben als zehn unterschiedliche Gäste mit jeweils einem
Techno-Song." Deshalb NICHT rohe Request-Zahlen verwenden, sondern
``unique_guest_support`` - UND zusätzlich pro Gast/Kategorie abklingende
Gewichte (1, 1/2, 1/3, ...), damit ein einzelner Gast mit sehr vielen
Wünschen im selben Genre die Gewichte dieses Genres nicht linear dominiert
(Spec §18 "Optional Gastbeiträge pro Kategorie deckeln").
"""

from __future__ import annotations

from collections import defaultdict

from music_engine.domain import GroupMusicProfile, MusicCatalog, TrackPreference

_DEFAULT_ENERGY = 0.5
_DEFAULT_DANCEABILITY = 0.5
_DEFAULT_FAMILIARITY = 0.5
_DEFAULT_SINGALONG = 0.3

# Spec §50: group_weight = request_count / (request_count + 15) - dieselbe
# Formel dient hier zusätzlich als GroupMusicProfile.confidence (je mehr
# Datenpunkte, desto vertrauenswürdiger das Profil eigenständig).
_SHRINKAGE_PRIOR_STRENGTH = 15.0


def compute_group_weight(request_count: int, prior_strength: float = _SHRINKAGE_PRIOR_STRENGTH) -> float:
    """Spec §50 Bayesian-Shrinkage-Gewicht: mit mehr Gästewünschen wird das
    Gruppenprofil zunehmend wichtiger gegenüber dem Occasion-Prior."""
    if request_count <= 0:
        return 0.0
    return request_count / (request_count + prior_strength)


def _add_diminishing(
    weights: dict[str, float],
    guest_contribution_counts: dict[tuple[str, str], int],
    guest_id: str,
    key: str,
) -> None:
    """Fügt einen abklingenden Beitrag (1, 1/2, 1/3, ...) für ``guest_id`` in
    der Kategorie ``key`` hinzu und aktualisiert den Zähler."""
    counter_key = (guest_id, key)
    already = guest_contribution_counts[counter_key]
    weights[key] = weights.get(key, 0.0) + 1.0 / (already + 1)
    guest_contribution_counts[counter_key] = already + 1


def _normalize_by_max(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        return {}
    max_value = max(weights.values())
    if max_value <= 0:
        return {k: 0.0 for k in weights}
    return {k: round(v / max_value, 4) for k, v in weights.items()}


def build_group_music_profile(
    track_preferences: dict[str, TrackPreference],
    catalog: MusicCatalog,
) -> GroupMusicProfile:
    """Baut ein ``GroupMusicProfile`` aus allen (bereits deduplizierten)
    Track-Präferenzen. Tracks, die nicht im Katalog gefunden werden (sollte
    dank resolver.py nicht vorkommen, aber defensiv abgesichert), werden für
    die Gewichtsberechnung übersprungen."""
    genre_weights: dict[str, float] = {}
    era_weights: dict[str, float] = {}
    mood_weights: dict[str, float] = {}
    language_weights: dict[str, float] = {}
    artist_weights: dict[str, float] = {}

    guest_contribution_counts: dict[tuple[str, str], int] = defaultdict(int)

    energy_acc = 0.0
    danceability_acc = 0.0
    familiarity_acc = 0.0
    singalong_acc = 0.0
    weight_total = 0.0

    unique_requesting_guests: set[str] = set()
    total_request_count = 0

    for pref in track_preferences.values():
        track = catalog.get_track(pref.track_id)
        unique_requesting_guests |= pref.supporting_guests
        total_request_count += pref.request_count

        if track is None:
            continue

        # Jeder unterstützende Gast trägt (abklingend) zu Genre/Era/Mood/
        # Sprache/Artist bei - unique_guest_support statt roher Request-Zahl.
        for guest_id in pref.supporting_guests:
            for genre in track.genres:
                _add_diminishing(genre_weights, guest_contribution_counts, guest_id, genre)
            for era in track.eras:
                _add_diminishing(era_weights, guest_contribution_counts, guest_id, era)
            for mood in track.moods:
                _add_diminishing(mood_weights, guest_contribution_counts, guest_id, mood)
            if track.language:
                _add_diminishing(language_weights, guest_contribution_counts, guest_id, track.language)
            _add_diminishing(artist_weights, guest_contribution_counts, guest_id, track.artist)

        # Numerische Targets: pro unterstützendem Gast einmal gewichtet
        # (unique_guest_support), damit ein Vielschreiber auch hier nicht
        # linear dominiert.
        guest_weight = float(len(pref.supporting_guests))
        energy_acc += (track.energy_score if track.energy_score is not None else _DEFAULT_ENERGY) * guest_weight
        danceability_acc += (
            track.danceability_score if track.danceability_score is not None else _DEFAULT_DANCEABILITY
        ) * guest_weight
        familiarity_acc += track.familiarity_prior * guest_weight
        singalong_acc += track.singalong_score * guest_weight
        weight_total += guest_weight

    if weight_total > 0:
        energy_target = energy_acc / weight_total
        danceability_target = danceability_acc / weight_total
        familiarity_target = familiarity_acc / weight_total
        singalong_target = singalong_acc / weight_total
    else:
        energy_target = _DEFAULT_ENERGY
        danceability_target = _DEFAULT_DANCEABILITY
        familiarity_target = _DEFAULT_FAMILIARITY
        singalong_target = _DEFAULT_SINGALONG

    return GroupMusicProfile(
        genre_weights=_normalize_by_max(genre_weights),
        era_weights=_normalize_by_max(era_weights),
        mood_weights=_normalize_by_max(mood_weights),
        energy_target=round(energy_target, 4),
        danceability_target=round(danceability_target, 4),
        familiarity_target=round(familiarity_target, 4),
        singalong_target=round(singalong_target, 4),
        language_weights=_normalize_by_max(language_weights),
        artist_weights=_normalize_by_max(artist_weights),
        # Spec §18: Vertrauen in das Gruppenprofil soll an der Diversität der
        # Gäste hängen, nicht an der rohen Wunschzahl (ein Gast mit 10
        # Wünschen darf die Gruppe nicht "sicherer" wirken lassen als 10
        # unterschiedliche Gäste mit je einem Wunsch) - deshalb hier bewusst
        # ``unique_requesting_guests`` statt ``total_request_count`` als Input
        # der §50-Shrinkage-Formel.
        confidence=round(compute_group_weight(len(unique_requesting_guests)), 4),
        request_count=total_request_count,
        unique_requesting_guests=len(unique_requesting_guests),
    )


if __name__ == "__main__":
    from music_engine.catalog import load_music_catalog
    from music_engine.resolver import deduplicate_requests, resolve_song_requests
    from music_engine.domain import RawSongRequest

    _catalog = load_music_catalog()

    # 10 Songs von einem Gast (immer selbes Genre-artiges Techno-Cluster via
    # house/edm) vs. 10 unterschiedliche Gäste mit je einem passenden Song -
    # Spec §18: Letzteres soll das Genre-Gewicht STÄRKER treiben.
    _dominant_requests = [
        RawSongRequest(guest_id="Dominant", text="Strobe", title_hint="Strobe", artist_hint="deadmau5")
        for _ in range(10)
    ]
    _diverse_requests = [
        RawSongRequest(guest_id=f"Guest{i}", text="Strobe", title_hint="Strobe", artist_hint="deadmau5")
        for i in range(10)
    ]

    _dom_prefs, _ = deduplicate_requests(resolve_song_requests(_dominant_requests, _catalog))
    _div_prefs, _ = deduplicate_requests(resolve_song_requests(_diverse_requests, _catalog))

    _dom_profile = build_group_music_profile(_dom_prefs, _catalog)
    _div_profile = build_group_music_profile(_div_prefs, _catalog)

    print(f"Dominant-guest profile confidence: {_dom_profile.confidence}, unique_guests={_dom_profile.unique_requesting_guests}")
    print(f"Diverse-guests profile confidence: {_div_profile.confidence}, unique_guests={_div_profile.unique_requesting_guests}")
    assert _div_profile.confidence > _dom_profile.confidence
    assert _div_profile.unique_requesting_guests == 10
    assert _dom_profile.unique_requesting_guests == 1

    print("music_engine/group_profile.py sanity check OK.")
