"""Geo-Such-Endpunkte (Suggest/Retrieve/Reverse) - Spec §7-9, §67-70, §104.

Alle Routen verlangen ``get_current_user`` (kein anonymer Zugriff, Spec §104
Abuse-Prevention-Baseline). Provider-Fehler führen NIE zu einem 500 (Spec
§97/§99) - ``geo.providers`` selbst wirft ohnehin nie, dieses Modul fügt
zusätzlich die serverseitige Mindestlänge fürs Suchfeld hinzu (Spec §11;
das eigentliche Debounce passiert client-seitig)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_geo_search_provider
from backend.app.schemas.geo import (
    GeoAddressPublic,
    GeoPlacePublic,
    GeoPointPublic,
    GeoReverseRequest,
    GeoRetrieveRequest,
    GeoSuggestResponse,
    GeoSuggestionPublic,
)
from geo.domain import GeoPlace, GeoPoint, GeoSearchContext
from geo.providers import GeoSearchProvider

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])

_MIN_QUERY_LENGTH = 2


def _to_place_public(place: GeoPlace) -> GeoPlacePublic:
    return GeoPlacePublic(
        id=place.id,
        name=place.name,
        place_type=place.place_type,
        address=GeoAddressPublic(
            street=place.address.street,
            house_number=place.address.house_number,
            postal_code=place.address.postal_code,
            city=place.address.city,
            district=place.address.district,
            region=place.address.region,
            country_code=place.address.country_code,
            country_name=place.address.country_name,
            formatted_address=place.address.formatted_address,
        ),
        point=GeoPointPublic(latitude=place.point.latitude, longitude=place.point.longitude) if place.point else None,
        provider=place.provider,
        provider_place_id=place.provider_place_id,
        precision=place.precision.value,
    )


@router.get("/suggest", response_model=GeoSuggestResponse)
def suggest_places(
    query: str,
    session_id: str | None = None,
    bias_lat: float | None = None,
    bias_lon: float | None = None,
    bias_country: str | None = None,
    _current_user: User = Depends(get_current_user),
    provider: GeoSearchProvider = Depends(get_geo_search_provider),
) -> GeoSuggestResponse:
    if len(query.strip()) < _MIN_QUERY_LENGTH:
        return GeoSuggestResponse(suggestions=[])

    context = GeoSearchContext(
        bias_point=GeoPoint(latitude=bias_lat, longitude=bias_lon) if bias_lat is not None and bias_lon is not None else None,
        bias_country_code=bias_country,
        search_session_id=session_id,
    )
    try:
        suggestions = provider.suggest(query, context)
    except Exception:
        return GeoSuggestResponse(suggestions=[])
    return GeoSuggestResponse(
        suggestions=[
            GeoSuggestionPublic(
                provider_place_id=s.provider_place_id,
                primary_text=s.primary_text,
                secondary_text=s.secondary_text,
                place_type=s.place_type,
                provider=s.provider,
            )
            for s in suggestions
        ]
    )


@router.post("/retrieve", response_model=Optional[GeoPlacePublic])
def retrieve_place(
    payload: GeoRetrieveRequest,
    _current_user: User = Depends(get_current_user),
    provider: GeoSearchProvider = Depends(get_geo_search_provider),
) -> GeoPlacePublic | None:
    context = GeoSearchContext(search_session_id=payload.session_id)
    try:
        place = provider.retrieve(payload.provider_place_id, context)
    except Exception:
        return None
    return _to_place_public(place) if place is not None else None


@router.post("/reverse", response_model=Optional[GeoPlacePublic])
def reverse_geocode(
    payload: GeoReverseRequest,
    _current_user: User = Depends(get_current_user),
    provider: GeoSearchProvider = Depends(get_geo_search_provider),
) -> GeoPlacePublic | None:
    try:
        place = provider.reverse_geocode(GeoPoint(latitude=payload.latitude, longitude=payload.longitude))
    except Exception:
        return None
    return _to_place_public(place) if place is not None else None
