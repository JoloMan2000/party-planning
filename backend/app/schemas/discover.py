from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PartyPublishRequest(BaseModel):
    event_type: str = ""
    interest_tags: list[str] = []


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
