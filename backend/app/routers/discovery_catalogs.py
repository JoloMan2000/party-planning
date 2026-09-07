"""Öffentliche Discovery-Katalog-Endpoints (Onboarding-Spec, Phase 6) - kein
Auth nötig, statische Referenzdaten (mirroring die anonymen
``/guest/{party_id}/catalog/*``-Endpoints, nur ohne Party-Scope)."""

from __future__ import annotations

from fastapi import APIRouter

from accounts.discovery_catalogs import (
    EVENT_INTEREST_CATALOG,
    EVENT_SETTING_CATALOG,
    EVENT_SIZE_CATALOG,
    INTEREST_TAG_CATALOG,
    MUSIC_GENRE_CATALOG,
    as_list,
)
from backend.app.schemas.profile import CatalogItemPublic

router = APIRouter(prefix="/api/v1/catalogs", tags=["discovery-catalogs"])


@router.get("/event-interests", response_model=list[CatalogItemPublic])
def list_event_interests() -> list[dict]:
    return as_list(EVENT_INTEREST_CATALOG)


@router.get("/music-genres", response_model=list[CatalogItemPublic])
def list_music_genres() -> list[dict]:
    return as_list(MUSIC_GENRE_CATALOG)


@router.get("/event-sizes", response_model=list[CatalogItemPublic])
def list_event_sizes() -> list[dict]:
    return as_list(EVENT_SIZE_CATALOG)


@router.get("/event-settings", response_model=list[CatalogItemPublic])
def list_event_settings() -> list[dict]:
    return as_list(EVENT_SETTING_CATALOG)


@router.get("/interest-tags", response_model=list[CatalogItemPublic])
def list_interest_tags() -> list[dict]:
    return as_list(INTEREST_TAG_CATALOG)
