"""Pydantic-Schemas für die Activities-Domain (Equipment Engine Phase 4,
"Real Activities Domain + Guest Voting"). Mirrort die Konvention von
``backend/app/schemas/equipment.py``/``backend/app/schemas/organizers.py``
(reine ``BaseModel``-DTOs - Router mappen Dataclass -> DTO manuell, siehe
``_to_public`` in ``backend/app/routers/activities.py``)."""

from __future__ import annotations

from pydantic import BaseModel


class ActivityCreate(BaseModel):
    name: str
    station_id: str | None = None


class ActivityPublic(BaseModel):
    id: str
    party_id: str
    created_by_user_id: str
    name: str
    station_id: str | None
    vote_count: int
    voted_by_me: bool
