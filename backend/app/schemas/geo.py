"""Pydantic-Schemas für die Geo-Platform-Endpunkte (``backend/app/routers/geo.py``).

Mirrort das Muster aus ``backend/app/schemas/accounts.py``/``discover.py``:
reine Request-/Response-Modelle, keine Domain-Logik hier."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class GeoSuggestionPublic(BaseModel):
    provider_place_id: str
    primary_text: str
    secondary_text: str
    place_type: str
    provider: str


class GeoSuggestResponse(BaseModel):
    suggestions: list[GeoSuggestionPublic]


class GeoAddressPublic(BaseModel):
    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    district: str | None = None
    region: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    formatted_address: str = ""


class GeoPointPublic(BaseModel):
    latitude: float
    longitude: float


class GeoPlacePublic(BaseModel):
    id: str
    name: str
    place_type: str
    address: GeoAddressPublic
    point: GeoPointPublic | None
    provider: str
    provider_place_id: str
    precision: str


class GeoRetrieveRequest(BaseModel):
    provider_place_id: str
    session_id: str | None = None

    @field_validator("provider_place_id")
    @classmethod
    def _provider_place_id_darf_nicht_leer_sein(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("provider_place_id darf nicht leer sein.")
        return value


class GeoReverseRequest(BaseModel):
    latitude: float
    longitude: float


class PartyLocationSetRequest(BaseModel):
    """Body für ``PUT /parties/{id}/location`` (Spec §18-25). ``visibility_policy``
    default identisch zum Domain-Default (``exact_after_accept``) - siehe
    ``geo.domain.VisibilityPolicy``."""

    place_name: str | None = None
    address: GeoAddressPublic | None = None
    point: GeoPointPublic | None = None
    precision: str = "approximate"
    provider: str | None = None
    provider_place_id: str | None = None
    public_location_label: str = ""
    visibility_policy: str = "exact_after_accept"
    arrival_instructions: str | None = None
    manually_adjusted: bool = False
    source: str = "organizer_entry"


class PartyLocationViewPublic(BaseModel):
    visibility_level: str
    display_label: str
    formatted_address: str | None
    point: GeoPointPublic | None
    arrival_instructions: str | None
