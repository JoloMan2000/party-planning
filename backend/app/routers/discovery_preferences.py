"""Explicit-Discovery-Preferences-Endpoints (Onboarding-Spec, Phase 6):
Radius/Ort/Timing/Preis/Mainstream-Slider, Musik-Genres, Artists,
Event-Interessen, plus der Onboarding-Abschluss-Gate.

``POST /onboarding/complete`` ist der EINZIGE Ort, der
``onboarding_completed_at`` setzt - serverseitig validiert (kein Client-Trust,
Onboarding-Spec §"No client trust"), damit ein Client nicht einfach behaupten
kann, das Onboarding sei fertig, ohne die Pflichtfelder tatsächlich gefüllt
zu haben."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.discover_learning as discover_learning
import accounts.discovery_storage as discovery_storage
import accounts.profile_storage as profile_storage
from accounts.domain import (
    User,
    UserArtistPreference,
    UserDiscoveryPreferences,
    UserMusicPreference,
)
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.profile import (
    ArtistPreferenceItem,
    ArtistPreferencesUpdateRequest,
    DiscoveryPreferencesPublic,
    DiscoveryPreferencesUpdateRequest,
    EventInterestsUpdateRequest,
    MusicPreferenceItem,
    MusicPreferencesUpdateRequest,
    OnboardingCompleteResponse,
)

router = APIRouter(prefix="/api/v1/me", tags=["discovery-preferences"])


def _to_public(prefs: UserDiscoveryPreferences) -> DiscoveryPreferencesPublic:
    return DiscoveryPreferencesPublic(
        discovery_radius_km=prefs.discovery_radius_km,
        allow_major_events_outside_radius=prefs.allow_major_events_outside_radius,
        discovery_city=prefs.discovery_city,
        discovery_lat=prefs.discovery_lat,
        discovery_lon=prefs.discovery_lon,
        preferred_days=prefs.preferred_days,
        preferred_dayparts=prefs.preferred_dayparts,
        price_preference=prefs.price_preference,
        mainstream_discovery=prefs.mainstream_discovery,
        personalized_recommendations_enabled=prefs.personalized_recommendations_enabled,
    )


@router.get("/discovery-preferences", response_model=DiscoveryPreferencesPublic)
def get_discovery_preferences(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> DiscoveryPreferencesPublic:
    prefs = discovery_storage.get_discovery_preferences(db_path, current_user.id)
    if prefs is None:
        defaults = UserDiscoveryPreferences(user_id=current_user.id)
        return _to_public(defaults)
    return _to_public(prefs)


@router.put("/discovery-preferences", response_model=DiscoveryPreferencesPublic)
def put_discovery_preferences(
    payload: DiscoveryPreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> DiscoveryPreferencesPublic:
    prefs = UserDiscoveryPreferences(
        user_id=current_user.id,
        discovery_radius_km=payload.discovery_radius_km,
        allow_major_events_outside_radius=payload.allow_major_events_outside_radius,
        discovery_city=payload.discovery_city,
        discovery_lat=payload.discovery_lat,
        discovery_lon=payload.discovery_lon,
        preferred_days=payload.preferred_days,
        preferred_dayparts=payload.preferred_dayparts,
        price_preference=payload.price_preference,
        mainstream_discovery=payload.mainstream_discovery,
        personalized_recommendations_enabled=payload.personalized_recommendations_enabled,
    )
    saved = discovery_storage.upsert_discovery_preferences(db_path, current_user.id, prefs)
    return _to_public(saved)


@router.post("/discovery-profile/reset-learning", status_code=status.HTTP_204_NO_CONTENT)
def reset_learning(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> None:
    """Build-Schritt 8: löscht alle gelernten Affinitäten (siehe
    ``accounts/discover_learning.py::reset_learned_profile``) - Ranking
    fällt danach auf reine explizite Preferences zurück. Explizite
    Preferences selbst, Blocked Organizers und Exposure-Historie bleiben
    unangetastet (siehe dortige Docstring-Begründung)."""
    discover_learning.reset_learned_profile(db_path, current_user.id)


@router.put("/discovery-preferences/music", response_model=list[MusicPreferenceItem])
def put_music_preferences(
    payload: MusicPreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> list[MusicPreferenceItem]:
    prefs = [
        UserMusicPreference(user_id=current_user.id, genre_id=p.genre_id, preference_level=p.preference_level)
        for p in payload.preferences
    ]
    saved = discovery_storage.replace_music_preferences(db_path, current_user.id, prefs)
    return [MusicPreferenceItem(genre_id=p.genre_id, preference_level=p.preference_level) for p in saved]


@router.put("/discovery-preferences/artists", response_model=list[ArtistPreferenceItem])
def put_artist_preferences(
    payload: ArtistPreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> list[ArtistPreferenceItem]:
    prefs = [
        UserArtistPreference(
            user_id=current_user.id,
            artist_reference=p.artist_reference,
            display_name=p.display_name,
            preference_level=p.preference_level,
        )
        for p in payload.preferences
    ]
    saved = discovery_storage.replace_artist_preferences(db_path, current_user.id, prefs)
    return [
        ArtistPreferenceItem(
            artist_reference=p.artist_reference, display_name=p.display_name, preference_level=p.preference_level
        )
        for p in saved
    ]


@router.put("/discovery-preferences/event-interests", response_model=list[str])
def put_event_interests(
    payload: EventInterestsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> list[str]:
    saved = discovery_storage.replace_event_interests(db_path, current_user.id, "event_type", payload.item_ids)
    return [p.item_id for p in saved]


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> OnboardingCompleteResponse:
    profile = profile_storage.get_user_profile(db_path, current_user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Geburtsdatum fehlt.")
    if not current_user.display_name.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Anzeigename fehlt.")

    prefs = discovery_storage.get_discovery_preferences(db_path, current_user.id)
    if prefs is None or not prefs.discovery_city.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Discover-Ort fehlt.")

    event_interests = discovery_storage.get_event_interests(db_path, current_user.id, category="event_type")
    if not event_interests:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mindestens ein Event-Interesse fehlt.")

    profile = profile_storage.mark_onboarding_completed(
        db_path, current_user.id, profile_completion_version=profile.profile_completion_version + 1
    )
    assert profile.onboarding_completed_at is not None
    return OnboardingCompleteResponse(
        onboarding_completed_at=profile.onboarding_completed_at,
        profile_completion_version=profile.profile_completion_version,
    )
