from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

import accounts.invitation_storage as invitation_storage
import accounts.party_storage as party_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.accounts import InvitationPublic, PartyPublic
from backend.app.schemas.auth import UserPublic

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(
        id=current_user.id, email=current_user.email, display_name=current_user.display_name,
        profile_image=current_user.profile_image, created_at=current_user.created_at,
    )


@router.get("/parties", response_model=list[PartyPublic])
def get_my_parties(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[PartyPublic]:
    parties = party_storage.list_parties_for_user(db_path, current_user.id)
    return [
        PartyPublic(
            id=party.id, host_user_id=party.host_user_id, name=party.name, description=party.description,
            starts_at=party.starts_at, location=party.location, created_at=party.created_at,
            updated_at=party.updated_at,
        )
        for party, _membership in parties
    ]


@router.get("/invitations", response_model=list[InvitationPublic])
def get_my_invitations(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[InvitationPublic]:
    invitations = invitation_storage.list_invitations_for_user(db_path, current_user.id)
    return [
        InvitationPublic(
            id=inv.id, party_id=inv.party_id, host_user_id=inv.host_user_id, invited_user_id=inv.invited_user_id,
            status=inv.status.value, invitation_message=inv.invitation_message, version=inv.version,
            created_at=inv.created_at, viewed_at=inv.viewed_at, responded_at=inv.responded_at,
        )
        for inv in invitations
    ]
