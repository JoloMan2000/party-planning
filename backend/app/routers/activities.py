"""Party-gescopte Activities-Endpunkte (Equipment Engine Phase 4, "Real
Activities Domain + Guest Voting"): Host/Co-Host-Verwaltung (Erstellen/
Löschen) + Member-Lesen/Voting für JEDES echte Party-Mitglied unabhängig vom
RSVP-Status - mirrort den Zugriffs-Präzedenzfall aus
``parties.py::get_party`` (``PartyRole.{HOST,CO_HOST,GUEST}`` reicht;
RSVP-Status ist in dieser Codebase NIE ein Autorisierungs-Filter, nur
Headcount-Mathematik, siehe ``admin_equipment.py``).

Zwei ``APIRouter`` in EINER Datei, exaktes Pendant zu ``admin_equipment.py``s
``router``/``provisions_router``-Split: Host-vs-Member ist hier ein echter
URL-Präfix-Unterschied (``/activities`` vs. ``/admin/activities``), nicht nur
ein anderer ``require_party_role``-Satz auf demselben Präfix.

Vote/Unvote mirrort ``social/follows.py``s Idempotenz-Konvention exakt:
POST-to-add (200, Status-DTO statt 201 - ein wiederholter Vote ist ein
No-Op-Erfolg, keine neue Ressource) / DELETE-to-remove (204, kein Body, keine
Existenzprüfung des Votes selbst - nur die Activity wird 404-geprüft)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import activities.storage as activities_storage
from accounts.domain import PartyMembership, PartyRole, User
from activities.domain import Activity
from backend.app.core.auth import get_current_user, require_party_role
from backend.app.core.deps import get_db_path
from backend.app.schemas.activities import ActivityCreate, ActivityPublic

router = APIRouter(prefix="/api/v1/parties/{party_id}/activities", tags=["activities"])
admin_router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/activities", tags=["admin"])

_require_member = require_party_role({PartyRole.HOST, PartyRole.CO_HOST, PartyRole.GUEST})
_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})


def _to_public(activity: Activity, vote_count: int, voted_by_me: bool) -> ActivityPublic:
    return ActivityPublic(
        id=activity.id, party_id=activity.party_id, created_by_user_id=activity.created_by_user_id,
        name=activity.name, station_id=activity.station_id, vote_count=vote_count, voted_by_me=voted_by_me,
    )


def _get_party_activity_or_404(db_path: Path, party_id: str, activity_id: str) -> Activity:
    """404 statt 403 bei fremder/falsch-gescopter Activity - keine Existenz
    verraten (mirrort ``admin_equipment.py::_get_party_provision_or_404``)."""
    existing = activities_storage.get_activity(db_path, activity_id)
    if existing is None or existing.party_id != party_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found.")
    return existing


# --- Host/Co-Host management --------------------------------------------


@admin_router.post("", response_model=ActivityPublic, status_code=status.HTTP_201_CREATED)
def create_activity(
    party_id: str,
    payload: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership: PartyMembership = Depends(_require_admin),
) -> ActivityPublic:
    activity = activities_storage.create_activity(
        db_path, uuid.uuid4().hex, party_id, current_user.id, payload.name, station_id=payload.station_id,
    )
    return _to_public(activity, vote_count=0, voted_by_me=False)


@admin_router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    party_id: str,
    activity_id: str,
    db_path: Path = Depends(get_db_path),
    _membership: PartyMembership = Depends(_require_admin),
) -> None:
    _get_party_activity_or_404(db_path, party_id, activity_id)
    activities_storage.delete_activity(db_path, activity_id)


# --- Member read + voting ------------------------------------------------


@router.get("", response_model=list[ActivityPublic])
def list_activities(
    party_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership: PartyMembership = Depends(_require_member),
) -> list[ActivityPublic]:
    party_activities = activities_storage.list_activities_for_party(db_path, party_id)
    vote_counts = activities_storage.count_votes_by_activity_for_party(db_path, party_id)
    voted_ids = activities_storage.list_voted_activity_ids_for_user(db_path, party_id, current_user.id)
    return [
        _to_public(a, vote_count=vote_counts.get(a.id, 0), voted_by_me=a.id in voted_ids)
        for a in party_activities
    ]


@router.post("/{activity_id}/vote", response_model=ActivityPublic)
def vote_for_activity(
    party_id: str,
    activity_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership: PartyMembership = Depends(_require_member),
) -> ActivityPublic:
    activity = _get_party_activity_or_404(db_path, party_id, activity_id)
    activities_storage.cast_vote(db_path, uuid.uuid4().hex, activity_id, current_user.id)
    vote_count = activities_storage.count_votes_for_activity(db_path, activity_id)
    return _to_public(activity, vote_count=vote_count, voted_by_me=True)


@router.delete("/{activity_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
def retract_vote_for_activity(
    party_id: str,
    activity_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership: PartyMembership = Depends(_require_member),
) -> None:
    _get_party_activity_or_404(db_path, party_id, activity_id)
    activities_storage.retract_vote(db_path, activity_id, current_user.id)
