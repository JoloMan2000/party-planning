from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PartyCreate(BaseModel):
    name: str
    description: str = ""
    starts_at: datetime | None = None
    location: str = ""


class PartyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    starts_at: datetime | None = None
    location: str | None = None


class PartyPublic(BaseModel):
    id: str
    host_user_id: str
    name: str
    description: str
    starts_at: datetime | None
    location: str
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
