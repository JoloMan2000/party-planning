from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class PartyPublishRequest(BaseModel):
    event_type: str = ""
    interest_tags: list[str] = []
    max_guests: int = 0

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


class DiscoverDeckResponse(BaseModel):
    cards: list[DiscoverCardPublic]


class DiscoverActionRequest(BaseModel):
    action: str  # "going" | "maybe" | "not_interested"


class DiscoverActionResponse(BaseModel):
    party_id: str
    action: str
    membership_role: str | None
    membership_rsvp_status: str | None
