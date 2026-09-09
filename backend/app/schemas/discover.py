from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class PartyPublishRequest(BaseModel):
    event_type: str = ""
    interest_tags: list[str] = []
    max_guests: int = 0
    # Geo Platform (Spec §123-124) - schaltet für Discover-Radius-Eligibility
    # einen erweiterten Radius frei (siehe accounts/discover_storage.py::MAJOR_EVENT_RADIUS_KM).
    is_major_event: bool = False

    @field_validator("max_guests")
    @classmethod
    def _max_guests_darf_nicht_negativ_sein(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_guests darf nicht negativ sein.")
        return value


class DiscoverCardPublic(BaseModel):
    party_id: str
    name: str
    description: str
    starts_at: datetime | None
    location: str
    cover_image: str
    event_type: str
    interest_tags: list[str]
    host_display_name: str
    match_score: float
    # Geo Platform (Spec §83) - nur gesetzt, wenn BEIDE Seiten (User-
    # Discovery-Koordinaten + Party-``party_locations``-Punkt) aufgelöst
    # sind; nie eine vorgetäuschte Distanz aus einem Städte-Textvergleich.
    distance_km: float | None = None
    # Build-Schritt 7 (Explainability) - ein kurzer, für den User
    # verständlicher Grund, nie leer (siehe accounts/discover_ranking.py::explain_candidate).
    why: str = ""


class DiscoverDeckResponse(BaseModel):
    cards: list[DiscoverCardPublic]


class DiscoverActionRequest(BaseModel):
    action: str  # "going" | "maybe" | "not_interested"
    # Build-Schritt 3: nur bei action="not_interested" erlaubt (siehe
    # Validierung in backend/app/routers/discover.py::act_on_discover_card) -
    # bewusst kein Enum-Typ hier, damit ein unbekannter Wert als 422 mit
    # klarer Fehlermeldung endet statt als generischer Pydantic-Parse-Fehler.
    reason: str | None = None


class DiscoverActionResponse(BaseModel):
    party_id: str
    action: str
    reason: str
    membership_role: str | None
    membership_rsvp_status: str | None


class OrganizerBlockResponse(BaseModel):
    organizer_id: str
    blocked: bool
