from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.invitation_storage as invitation_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import PartyRole, User
from backend.app.core.auth import get_current_user, require_party_role
from backend.app.core.deps import get_db_path
from backend.app.schemas.accounts import (
    GuestListEntry,
    InvitationCreate,
    InvitationPublic,
    PartyCreate,
    PartyGuestsResponse,
    PartyPublic,
    PartyUpdate,
)

router = APIRouter(prefix="/api/v1/parties", tags=["parties"])


def _to_party_public(party) -> PartyPublic:
    return PartyPublic(
        id=party.id, host_user_id=party.host_user_id, name=party.name, description=party.description,
        starts_at=party.starts_at, location=party.location, created_at=party.created_at,
        updated_at=party.updated_at,
    )


@router.post("", response_model=PartyPublic, status_code=status.HTTP_201_CREATED)
def create_party(
    payload: PartyCreate, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> PartyPublic:
    party = party_storage.create_party(
        db_path, uuid.uuid4().hex, current_user.id, payload.name,
        description=payload.description, starts_at=payload.starts_at, location=payload.location,
    )
    return _to_party_public(party)


@router.get("/{party_id}", response_model=PartyPublic)
def get_party(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST, PartyRole.GUEST})),
) -> PartyPublic:
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")
    return _to_party_public(party)


@router.patch("/{party_id}", response_model=PartyPublic)
def update_party(
    party_id: str,
    payload: PartyUpdate,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> PartyPublic:
    party = party_storage.update_party(db_path, party_id, **payload.model_dump(exclude_unset=True))
    return _to_party_public(party)


@router.get("/{party_id}/guests", response_model=PartyGuestsResponse)
def get_party_guests(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> PartyGuestsResponse:
    memberships = party_storage.list_memberships_for_party(db_path, party_id)
    guests = []
    for membership in memberships:
        user = user_storage.get_user_by_id(db_path, membership.user_id)
        if user is None:
            continue
        guests.append(
            GuestListEntry(
                user_id=user.id, display_name=user.display_name, email=user.email,
                role=membership.role.value, rsvp_status=membership.rsvp_status.value,
                joined_at=membership.joined_at,
            )
        )
    counts = party_storage.count_rsvp_statuses(db_path, party_id)
    return PartyGuestsResponse(guests=guests, counts=counts)


@router.post("/{party_id}/invitations", response_model=InvitationPublic, status_code=status.HTTP_201_CREATED)
def invite_guest(
    party_id: str,
    payload: InvitationCreate,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> InvitationPublic:
    invited_user = user_storage.get_user_by_email(db_path, payload.invited_user_email)
    if invited_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein User mit dieser E-Mail gefunden.")
    try:
        invitation = invitation_storage.create_invitation(
            db_path, uuid.uuid4().hex, party_id, current_user.id, invited_user.id,
            invitation_message=payload.invitation_message,
        )
    except invitation_storage.InvitationAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Einladung existiert bereits.")
    return InvitationPublic(
        id=invitation.id, party_id=invitation.party_id, host_user_id=invitation.host_user_id,
        invited_user_id=invitation.invited_user_id, status=invitation.status.value,
        invitation_message=invitation.invitation_message, version=invitation.version,
        created_at=invitation.created_at, viewed_at=invitation.viewed_at, responded_at=invitation.responded_at,
    )
