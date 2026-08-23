"""
Candidate-Provider-Architektur (Spec §51/§52).
==================================================

Implementiert das ``MusicCandidateProvider``-Protocol sowie sieben konkrete
Provider (Spec §51), die alle ``TrackCandidate``-Objekte liefern. Die Engine
hängt dadurch NICHT hart von einer einzigen Empfehlungsquelle ab - fällt eine
externe Quelle künftig weg, arbeitet die Engine weiter mit dem lokalen
Seed-Katalog (Spec §52).

Architekturentscheidung (nicht 1:1 im Spec-Skelett, aber strukturell
notwendig, analog zu ``MusicStrategy``/``PlaylistPlan`` in domain.py):
``CandidateContext`` bündelt alle Eingaben, die die Provider gemeinsam
brauchen (Katalog, Strategie, Track-Preferences, Admin-Settings), damit das
``MusicCandidateProvider``-Protocol eine einzige, stabile Signatur hat und
künftige Provider (z.B. eine externe API) nicht die Funktionssignatur ändern
müssen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from music_engine.domain import (
    AdminArtistOverride,
    AdminMusicSettings,
    AdminTrackOverride,
    MusicCatalog,
    MusicStrategy,
    TrackCandidate,
    TrackPreference,
)

# Wie viele zusätzliche Tracks ein Admin-"preferred"-Artist-Override maximal
# beisteuert (verhindert, dass ein einzelner Artist-Override den gesamten
# Kandidatenpool flutet).
_MAX_TRACKS_PER_ARTIST_OVERRIDE = 5

# Kandidatenpool-Größen der "breiten" Provider (Occasion/GroupTaste/GenreEra/
# Exploration) - bewusst großzügig, da apply_diversity_constraints() und die
# spätere Duration-/Sequence-Optimierung ohnehin stark filtern.
_DEFAULT_POOL_SIZE = 120


@dataclass
class CandidateContext:
    catalog: MusicCatalog
    strategy: MusicStrategy
    track_preferences: dict[str, TrackPreference] = field(default_factory=dict)
    admin_settings: AdminMusicSettings = field(default_factory=AdminMusicSettings)
    admin_track_overrides: dict[str, AdminTrackOverride] = field(default_factory=dict)
    admin_artist_overrides: dict[str, AdminArtistOverride] = field(default_factory=dict)


class MusicCandidateProvider(Protocol):
    """Spec §52: Protocol, damit künftig weitere/andere Kandidatenquellen
    angeschlossen werden können, ohne die Engine umzubauen."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        ...


class RequestedTrackCandidateProvider:
    """Alle Gästewünsche (bereits dedupliziert als ``TrackPreference``) - die
    wichtigste Quelle (Spec §10: Songwünsche haben hohe Priorität)."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        candidates: list[TrackCandidate] = []
        for track_id, pref in ctx.track_preferences.items():
            is_multi = len(pref.supporting_guests) > 1
            candidates.append(
                TrackCandidate(
                    track_id=track_id,
                    source="multi_guest_request" if is_multi else "guest_request",
                    supporting_guests=set(pref.supporting_guests),
                    request_count=pref.request_count,
                )
            )
        return candidates


class AdminCandidateProvider:
    """Admin Must-Play / Preferred Overrides (Spec §62/§63), inkl. Expansion
    von Artist-Overrides auf konkrete Katalog-Tracks."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        candidates: list[TrackCandidate] = []

        for track_id, override in ctx.admin_track_overrides.items():
            if override.status == "must_play":
                candidates.append(TrackCandidate(track_id=track_id, source="admin_must_play", admin_status="must_play"))
            elif override.status == "preferred":
                candidates.append(TrackCandidate(track_id=track_id, source="admin_preferred", admin_status="preferred"))
            # "banned"/"avoid" werden NICHT als Kandidaten erzeugt - deren
            # Ausschluss passiert zusätzlich hart in ranking.py.

        for artist_id, override in ctx.admin_artist_overrides.items():
            if override.status not in ("preferred", "must_play"):
                continue
            artist_key = artist_id.strip().lower()
            track_ids = ctx.catalog.normalized_artist_index.get(artist_key, [])
            source = "admin_must_play" if override.status == "must_play" else "admin_preferred"
            for track_id in track_ids[:_MAX_TRACKS_PER_ARTIST_OVERRIDE]:
                candidates.append(TrackCandidate(track_id=track_id, source=source, admin_status=override.status))

        return candidates


def _top_weighted_keys(weights: dict[str, float], limit: int = 6) -> list[str]:
    return [k for k, _ in sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


class OccasionSeedCandidateProvider:
    """Tracks, die stark zu den *statischen* Anlass-Vorlieben passen (Spec
    §51). Nutzt gezielt den Genre-/Era-/Tag-Index des Katalogs statt eines
    vollen Scans."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        candidates: dict[str, TrackCandidate] = {}
        top_genres = _top_weighted_keys(ctx.strategy.genre_weights)
        top_tags = _top_weighted_keys(ctx.strategy.tag_weights)

        pool: list[str] = []
        for genre in top_genres:
            pool.extend(ctx.catalog.genre_index.get(genre, []))
        for tag in top_tags:
            pool.extend(ctx.catalog.tag_index.get(tag, []))

        for track_id in pool[:_DEFAULT_POOL_SIZE]:
            if track_id not in candidates:
                candidates[track_id] = TrackCandidate(track_id=track_id, source="occasion_recommendation")
        return list(candidates.values())


class GroupTasteCandidateProvider:
    """Tracks passend zum Gruppen-Musikgeschmack (Top-Genres/-Eras der
    ``GroupMusicProfile``, bereits in ``strategy`` eingeflossen)."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        if ctx.strategy.group_weight <= 0:
            return []
        candidates: dict[str, TrackCandidate] = {}
        top_eras = _top_weighted_keys(ctx.strategy.era_weights)
        top_genres = _top_weighted_keys(ctx.strategy.genre_weights)

        pool: list[str] = []
        for era in top_eras:
            pool.extend(ctx.catalog.era_index.get(era, []))
        for genre in top_genres:
            pool.extend(ctx.catalog.genre_index.get(genre, []))

        for track_id in pool[:_DEFAULT_POOL_SIZE]:
            if track_id not in candidates:
                candidates[track_id] = TrackCandidate(track_id=track_id, source="group_recommendation")
        return list(candidates.values())


class ArtistNeighbourhoodCandidateProvider:
    """"Fans dieses Artists mögen vermutlich auch..." - weitere Tracks
    derselben Artists, die bereits von Gästen gewünscht wurden."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        requested_artists: set[str] = set()
        for track_id in ctx.track_preferences:
            track = ctx.catalog.get_track(track_id)
            if track:
                requested_artists.add(track.artist.strip().lower())

        candidates: dict[str, TrackCandidate] = {}
        for artist_key in requested_artists:
            for track_id in ctx.catalog.normalized_artist_index.get(artist_key, [])[:_MAX_TRACKS_PER_ARTIST_OVERRIDE]:
                if track_id not in ctx.track_preferences and track_id not in candidates:
                    candidates[track_id] = TrackCandidate(track_id=track_id, source="group_recommendation")
        return list(candidates.values())


class GenreEraCandidateProvider:
    """Breiter Genre-/Era-Fill basierend auf der bereits (Occasion+Gruppe)
    geblendeten ``MusicStrategy`` - deckt Lücken ab, die die enger gefassten
    Occasion-/GroupTaste-Provider nicht abdecken."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        candidates: dict[str, TrackCandidate] = {}
        top_genres = _top_weighted_keys(ctx.strategy.genre_weights, limit=10)
        top_eras = _top_weighted_keys(ctx.strategy.era_weights, limit=len(ctx.strategy.era_weights) or 1)

        for genre in top_genres:
            for track_id in ctx.catalog.genre_index.get(genre, []):
                track = ctx.catalog.get_track(track_id)
                if track and (not top_eras or track.eras.intersection(top_eras)):
                    if track_id not in candidates:
                        candidates[track_id] = TrackCandidate(track_id=track_id, source="occasion_recommendation")

        return list(candidates.values())[:_DEFAULT_POOL_SIZE]


class ExplorationCandidateProvider:
    """Spec §59: kontrollierte Entdeckung (Default 10%) - NIE komplett
    zufällig, sondern weiterhin innerhalb des Anlass-/Gruppenprofils (nur
    ``discouraged_genres`` werden ausgeschlossen), aber mit niedrigerem
    ``familiarity_prior`` als der Kern-Pool (Nische statt Mainstream)."""

    def generate_candidates(self, ctx: CandidateContext) -> list[TrackCandidate]:
        candidates: list[TrackCandidate] = []
        discouraged = set(ctx.admin_settings.discouraged_genres) | set(ctx.admin_settings.banned_genres)
        top_genres = set(_top_weighted_keys(ctx.strategy.genre_weights, limit=8))

        for track_id, track in ctx.catalog.tracks.items():
            if track.genres & discouraged:
                continue
            if not (track.genres & top_genres):
                continue
            if track.familiarity_prior <= 0.55:
                candidates.append(TrackCandidate(track_id=track_id, source="exploration"))

        return candidates[:_DEFAULT_POOL_SIZE]


DEFAULT_PROVIDERS: list[MusicCandidateProvider] = [
    RequestedTrackCandidateProvider(),
    AdminCandidateProvider(),
    OccasionSeedCandidateProvider(),
    GroupTasteCandidateProvider(),
    ArtistNeighbourhoodCandidateProvider(),
    GenreEraCandidateProvider(),
    ExplorationCandidateProvider(),
]

# Rangfolge der Quellen, falls dieselbe track_id von mehreren Providern
# geliefert wird - die "beste" (höchstpriorisierte) Quelle gewinnt beim Merge
# (Spec §10 SOURCE_WEIGHT-Rangfolge).
_SOURCE_PRIORITY = [
    "admin_must_play",
    "multi_guest_request",
    "guest_request",
    "admin_preferred",
    "group_recommendation",
    "occasion_recommendation",
    "exploration",
]


def generate_all_candidates(
    ctx: CandidateContext, providers: list[MusicCandidateProvider] | None = None
) -> dict[str, TrackCandidate]:
    """Ruft alle Provider auf und merged die Ergebnisse zu einem Dict
    ``track_id -> TrackCandidate`` (Spec §92 ``generate_candidates()``-Schritt).
    Liefert derselbe Provider oder mehrere Provider dieselbe ``track_id``,
    gewinnt die höchstpriorisierte Quelle; ``supporting_guests``/
    ``request_count`` werden dabei aus dem ursprünglichen Requested-Kandidaten
    übernommen, falls vorhanden."""
    merged: dict[str, TrackCandidate] = {}
    active_providers = providers if providers is not None else DEFAULT_PROVIDERS

    for provider in active_providers:
        for candidate in provider.generate_candidates(ctx):
            existing = merged.get(candidate.track_id)
            if existing is None:
                merged[candidate.track_id] = candidate
                continue
            existing_rank = _SOURCE_PRIORITY.index(existing.source) if existing.source in _SOURCE_PRIORITY else len(_SOURCE_PRIORITY)
            new_rank = _SOURCE_PRIORITY.index(candidate.source) if candidate.source in _SOURCE_PRIORITY else len(_SOURCE_PRIORITY)
            if new_rank < existing_rank:
                candidate.supporting_guests |= existing.supporting_guests
                candidate.request_count = max(candidate.request_count, existing.request_count)
                merged[candidate.track_id] = candidate
            else:
                existing.supporting_guests |= candidate.supporting_guests
                existing.request_count = max(existing.request_count, candidate.request_count)

    return merged


if __name__ == "__main__":
    from music_engine.catalog import load_music_catalog
    from music_engine.domain import MusicStrategy

    _catalog = load_music_catalog()
    _strategy = MusicStrategy(
        occasion_id="grill_party",
        genre_weights={"pop": 0.9, "rock": 0.8, "throwback_party": 0.9},
        era_weights={"90s": 0.9, "2000s": 0.9},
        tag_weights={"crowd_pleaser": 0.9, "party_classic": 0.9},
    )
    _ctx = CandidateContext(catalog=_catalog, strategy=_strategy)
    _all = generate_all_candidates(_ctx)
    print(f"Generated {len(_all)} unique candidates across {len(DEFAULT_PROVIDERS)} providers.")
    assert len(_all) > 0
    print("music_engine/candidates.py sanity check OK.")
