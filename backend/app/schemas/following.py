"""Pydantic-Schemas für die Following-Domain (Social-Graph-Phase-5,
AUFGABE-Spec §45-79). Mirrort die Konvention von
``backend/app/schemas/social.py`` (reine ``BaseModel``-DTOs, kleine
Action-Response-Objekte wie ``UserBlockResponse``).

``GET /me/following/organizers`` nutzt ``OrganizerPublic`` aus
``backend/app/schemas/organizers.py`` wieder (mit ``my_role=None``) - kein
eigener DTO nötig."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrganizerFollowStatusResponse(BaseModel):
    """Antwort auf ``POST/GET /organizers/{id}/follow[ers]``. ``following``
    ist immer aus Sicht des aufrufenden Users; ``follower_count`` ist die
    serverseitige Gesamtzahl (Spec §59)."""

    organizer_id: str
    follower_count: int
    following: bool


class EventFollowStatusResponse(BaseModel):
    """Antwort auf ``POST/GET /events/{party_id}/follow[ers]``. Event = eine
    veröffentlichte Party, adressiert über ``party_id`` (die überall in
    Discover genutzte stabile Kennung)."""

    party_id: str
    follower_count: int
    following: bool


class FollowedEventPublic(BaseModel):
    """Eine Zeile in ``GET /me/following/events``. Enthält nur noch
    veröffentlichte Events - Follows auf inzwischen unveröffentlichte Partys
    werden serverseitig ausgeblendet (nicht gelöscht)."""

    party_id: str
    name: str
    starts_at: datetime | None  # parties.starts_at ist nullable
    location: str
    event_type: str
    followed_at: datetime
