"""Pydantic-Schemas für Social-Profile + Explicit-Discovery-Preferences
(Onboarding-Spec, Phase 6). Mirrort die Konvention von
``backend/app/schemas/auth.py``/``accounts.py`` (reine ``BaseModel``-DTOs,
keine Storage-/Domain-Importe außer für Typ-Referenzen)."""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, field_validator

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.]{3,30}$")


class ProfilePublic(BaseModel):
    user_id: str
    birth_date: date
    age: int
    gender: str = ""
    bio: str = ""
    username: str = ""
    onboarding_completed_at: datetime | None = None
    profile_completion_version: int = 0


class ProfileCreateRequest(BaseModel):
    """Nur für den initialen Onboarding-Schritt - einziger Endpoint, der
    ``birth_date`` beim erstmaligen Anlegen entgegennimmt."""

    birth_date: date
    gender: str = ""
    bio: str = ""


class ProfileUpdateRequest(BaseModel):
    """Normales Profil-Update - bewusst OHNE ``birth_date`` (geschützt, siehe
    ``BirthDateCorrectionRequest``). ``username=None`` bedeutet "unverändert
    lassen" (Social-Graph-Phase-1) - siehe
    ``accounts.profile_storage.upsert_user_profile``."""

    gender: str | None = None
    bio: str | None = None
    username: str | None = None

    @field_validator("username")
    @classmethod
    def _username_hat_gueltiges_format(cls, value: str | None) -> str | None:
        if value is not None and not _USERNAME_PATTERN.match(value):
            raise ValueError(
                "username muss 3-30 Zeichen lang sein und darf nur Buchstaben, Zahlen, "
                "Unterstriche und Punkte enthalten."
            )
        return value


class BirthDateCorrectionRequest(BaseModel):
    birth_date: date
    reason: str = ""


class DiscoveryPreferencesPublic(BaseModel):
    discovery_radius_km: float
    allow_major_events_outside_radius: bool
    discovery_city: str
    discovery_lat: float | None = None
    discovery_lon: float | None = None
    preferred_days: list[str] = []
    preferred_dayparts: list[str] = []
    price_preference: str = ""
    mainstream_discovery: float
    personalized_recommendations_enabled: bool


class DiscoveryPreferencesUpdateRequest(BaseModel):
    discovery_radius_km: float = 25.0
    allow_major_events_outside_radius: bool = False
    discovery_city: str = ""
    discovery_lat: float | None = None
    discovery_lon: float | None = None
    preferred_days: list[str] = []
    preferred_dayparts: list[str] = []
    price_preference: str = ""
    mainstream_discovery: float = 0.5
    personalized_recommendations_enabled: bool = True


class MusicPreferenceItem(BaseModel):
    genre_id: str
    preference_level: str = "like"


class MusicPreferencesUpdateRequest(BaseModel):
    preferences: list[MusicPreferenceItem]


class ArtistPreferenceItem(BaseModel):
    artist_reference: str
    display_name: str
    preference_level: str = "like"


class ArtistPreferencesUpdateRequest(BaseModel):
    preferences: list[ArtistPreferenceItem]


class EventInterestsUpdateRequest(BaseModel):
    item_ids: list[str]


class CatalogItemPublic(BaseModel):
    id: str
    label_de: str
    label_en: str
    emoji: str = ""


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed_at: datetime
    profile_completion_version: int
