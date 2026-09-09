"""Pydantic-Schemas für den Organizer-Domain-Foundation (Social-Graph-
Phase-4). Mirrort die Konvention von ``backend/app/schemas/accounts.py``
(reine ``BaseModel``-DTOs)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from organizers.domain import OrganizerRole

_ORGANIZER_ROLE_VALUES = {role.value for role in OrganizerRole}


class OrganizerCreate(BaseModel):
    display_name: str
    organizer_type: str = ""
    description: str = ""
    website_url: str = ""


class OrganizerPublic(BaseModel):
    id: str
    owner_user_id: str
    display_name: str
    organizer_type: str
    verification_status: str
    description: str
    website_url: str
    # Nur dort befüllt, wo die eigene Mitgliedschaft des Callers ohnehin
    # bekannt ist (get/list-mine) - kein zusätzlicher Lookup nur dafür.
    my_role: str | None = None
    created_at: datetime
    updated_at: datetime


class OrganizerMemberAddRequest(BaseModel):
    user_id: str
    role: str

    @field_validator("role")
    @classmethod
    def _gueltige_role(cls, value: str) -> str:
        if value not in _ORGANIZER_ROLE_VALUES:
            raise ValueError(f"role muss einer von {sorted(_ORGANIZER_ROLE_VALUES)} sein.")
        return value


class OrganizerMemberPublic(BaseModel):
    organizer_id: str
    user_id: str
    role: str
    created_at: datetime
    updated_at: datetime


class OrganizerMembersResponse(BaseModel):
    members: list[OrganizerMemberPublic]
