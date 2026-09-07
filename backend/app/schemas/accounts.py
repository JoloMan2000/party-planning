from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Grosszügige, aber endliche Obergrenzen - schützen DB/UI vor unbeabsichtigt
# riesigen Payloads (kein Angriffsschutz per se, eher Robustheit gegen Bugs/
# Copy-Paste-Unfälle auf Client-Seite). `min_length=1` auf `name` verhindert
# zusätzlich einen leeren Partynamen sowohl beim Erstellen als auch beim
# nachträglichen Umbenennen.
_NAME_MAX_LENGTH = 200
_DESCRIPTION_MAX_LENGTH = 5000
_LOCATION_MAX_LENGTH = 300


class PartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=_NAME_MAX_LENGTH)
    description: str = Field("", max_length=_DESCRIPTION_MAX_LENGTH)
    starts_at: datetime | None = None
    location: str = Field("", max_length=_LOCATION_MAX_LENGTH)


class PartyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=_NAME_MAX_LENGTH)
    description: str | None = Field(None, max_length=_DESCRIPTION_MAX_LENGTH)
    starts_at: datetime | None = None
    location: str | None = Field(None, max_length=_LOCATION_MAX_LENGTH)


class PartyPublic(BaseModel):
    id: str
    host_user_id: str
    name: str
    description: str
    starts_at: datetime | None
    location: str
    cover_image: str = ""
    is_published: bool = False
    event_type: str = ""
    interest_tags: list[str] = []
    max_guests: int = 0
    host_is_verified: bool = False
    my_discover_action: str | None = None
    created_at: datetime
    updated_at: datetime


class InvitationCreate(BaseModel):
    invited_user_email: str
    invitation_message: str = ""


class InvitationPublic(BaseModel):
    id: str
    party_id: str
    host_user_id: str
    invited_user_id: str
    status: str
    invitation_message: str
    version: int
    created_at: datetime
    viewed_at: datetime | None
    responded_at: datetime | None


class RsvpRequest(BaseModel):
    status: str
    version: int
    client_request_id: str | None = None


class RsvpResponse(BaseModel):
    invitation_id: str
    party_id: str
    status: str
    responded_at: datetime | None
    version: int


class GuestListEntry(BaseModel):
    user_id: str
    display_name: str
    email: str
    role: str
    rsvp_status: str
    joined_at: datetime


class PartyGuestsResponse(BaseModel):
    guests: list[GuestListEntry]
    counts: dict[str, int]
