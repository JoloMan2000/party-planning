"""Organizer-Domain-Foundation-Endpunkte (Social-Graph-Phase-4). Backend-
only diese Phase - kein Mobile-Screen dafür, exakt das gleiche Precedent
wie die bestehende (Curl-only) User-Verification (``admin_users.py``)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import organizers.storage as organizers_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.organizers import (
    OrganizerCreate,
    OrganizerMemberAddRequest,
    OrganizerMemberPublic,
    OrganizerMembersResponse,
    OrganizerPublic,
)
from organizers.domain import OrganizerMembership, OrganizerRole

router = APIRouter(prefix="/api/v1/organizers", tags=["organizers"])


def require_organizer_role(allowed_roles: set[OrganizerRole] | None):
    """Dependency-Factory: 404 falls Organizer unbekannt, 403 falls der User
    keine oder eine nicht ausreichende Rolle in diesem Organizer hat -
    exaktes Pendant zu ``backend.app.core.auth.require_party_role``.
    ``allowed_roles=None`` bedeutet "irgendein Mitglied reicht" (für
    Endpunkte, die keine bestimmte Rolle brauchen, nur Mitgliedschaft)."""

    def _dependency(
        organizer_id: str,
        current_user: User = Depends(get_current_user),
        db_path: Path = Depends(get_db_path),
    ) -> OrganizerMembership:
        organizer = organizers_storage.get_organizer(db_path, organizer_id)
        if organizer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer nicht gefunden.")
        membership = organizers_storage.get_membership(db_path, organizer_id, current_user.id)
        if membership is None or (allowed_roles is not None and membership.role not in allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diesen Organizer.")
        return membership

    return _dependency


def _to_organizer_public(organizer, my_role: str | None = None) -> OrganizerPublic:
    return OrganizerPublic(
        id=organizer.id, owner_user_id=organizer.owner_user_id, display_name=organizer.display_name,
        organizer_type=organizer.organizer_type, verification_status=organizer.verification_status.value,
        description=organizer.description, website_url=organizer.website_url, my_role=my_role,
        created_at=organizer.created_at, updated_at=organizer.updated_at,
    )


def _to_member_public(membership: OrganizerMembership) -> OrganizerMemberPublic:
    return OrganizerMemberPublic(
        organizer_id=membership.organizer_id, user_id=membership.user_id, role=membership.role.value,
        created_at=membership.created_at, updated_at=membership.updated_at,
    )


@router.post("", response_model=OrganizerPublic, status_code=status.HTTP_201_CREATED)
def create_organizer(
    payload: OrganizerCreate, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> OrganizerPublic:
    """Self-Serve-Erstellung (jeder eingeloggte User darf) - erzeugt
    atomisch den Organizer + eine ``OWNER``-Membership für den Ersteller
    (siehe ``organizers.storage.create_organizer``), exaktes Pendant zu
    ``parties.py::create_party``."""
    organizer = organizers_storage.create_organizer(
        db_path, uuid.uuid4().hex, current_user.id, payload.display_name,
        organizer_type=payload.organizer_type, description=payload.description, website_url=payload.website_url,
    )
    return _to_organizer_public(organizer, my_role=OrganizerRole.OWNER.value)


@router.get("/mine", response_model=list[OrganizerPublic])
def list_my_organizers(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[OrganizerPublic]:
    return [
        _to_organizer_public(organizer, my_role=membership.role.value)
        for organizer, membership in organizers_storage.list_organizers_for_user(db_path, current_user.id)
    ]


@router.get("/{organizer_id}", response_model=OrganizerPublic)
def get_organizer(
    organizer_id: str,
    db_path: Path = Depends(get_db_path),
    membership: OrganizerMembership = Depends(require_organizer_role(None)),
) -> OrganizerPublic:
    organizer = organizers_storage.get_organizer(db_path, organizer_id)
    if organizer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer nicht gefunden.")
    return _to_organizer_public(organizer, my_role=membership.role.value)


@router.post("/{organizer_id}/members", response_model=OrganizerMemberPublic)
def add_member(
    organizer_id: str,
    payload: OrganizerMemberAddRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership: OrganizerMembership = Depends(require_organizer_role({OrganizerRole.OWNER})),
) -> OrganizerMemberPublic:
    """Nur der Owner darf Mitgliedschaften setzen (mirrors
    ``parties.py::promote_co_host``'s Host-only-Einschränkung) - akzeptiert
    ALLE fünf ``OrganizerRole``-Werte, keine künstlich eingeschränkte
    Teilmenge (siehe Plan: 3 von 5 Enum-Werten wären sonst diese Phase
    nie erreichbar). Self-Target ist verboten: ein Owner, der sich selbst
    umstuft, könnte den Organizer verwaisen lassen - es gibt (noch) keinen
    Ownership-Transfer-Flow."""
    if payload.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Du kannst deine eigene Rolle nicht ändern.")
    role = OrganizerRole(payload.role)
    membership = organizers_storage.upsert_membership(db_path, organizer_id, payload.user_id, role)
    return _to_member_public(membership)


@router.get("/{organizer_id}/members", response_model=OrganizerMembersResponse)
def list_members(
    organizer_id: str,
    db_path: Path = Depends(get_db_path),
    _membership: OrganizerMembership = Depends(require_organizer_role(None)),
) -> OrganizerMembersResponse:
    members = [_to_member_public(m) for m in organizers_storage.list_members(db_path, organizer_id)]
    return OrganizerMembersResponse(members=members)
