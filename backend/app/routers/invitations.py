from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.invitation_storage as invitation_storage
from accounts.domain import Invitation, RsvpStatus, User
from backend.app.core.auth import get_current_user, get_invitation_for_rsvp, get_invitation_for_viewer
from backend.app.core.deps import get_db_path
from backend.app.schemas.accounts import InvitationPublic, RsvpRequest, RsvpResponse

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])


def _to_invitation_public(invitation: Invitation) -> InvitationPublic:
    return InvitationPublic(
        id=invitation.id, party_id=invitation.party_id, host_user_id=invitation.host_user_id,
        invited_user_id=invitation.invited_user_id, status=invitation.status.value,
        invitation_message=invitation.invitation_message, version=invitation.version,
        created_at=invitation.created_at, viewed_at=invitation.viewed_at, responded_at=invitation.responded_at,
    )


@router.get("/{invitation_id}", response_model=InvitationPublic)
def get_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    invitation: Invitation = Depends(get_invitation_for_viewer),
) -> InvitationPublic:
    if current_user.id == invitation.invited_user_id:
        viewed = invitation_storage.mark_invitation_viewed(db_path, invitation_id)
        if viewed is not None:
            invitation = viewed
    return _to_invitation_public(invitation)


@router.put("/{invitation_id}/rsvp", response_model=RsvpResponse)
def rsvp(
    invitation_id: str,
    payload: RsvpRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _invitation: Invitation = Depends(get_invitation_for_rsvp),
) -> RsvpResponse:
    try:
        new_status = RsvpStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ungültiger RSVP-Status.")

    try:
        result = invitation_storage.apply_rsvp_transition(
            db_path, invitation_id, new_status, current_user.id, payload.version,
            client_request_id=payload.client_request_id,
        )
    except invitation_storage.InvitationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden.")
    except invitation_storage.VersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Version-Konflikt.", "current_version": exc.current_version},
        )
    except invitation_storage.InvalidTransitionError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ungültiger Statuswechsel.")
    except invitation_storage.IdempotencyKeyReuseError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotenzschlüssel bereits mit anderem Status verwendet.")

    return RsvpResponse(
        invitation_id=result.invitation_id, party_id=result.party_id, status=result.status.value,
        responded_at=result.responded_at, version=result.version,
    )
