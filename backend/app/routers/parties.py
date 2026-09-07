from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

import accounts.discover_storage as discover_storage
import accounts.invitation_storage as invitation_storage
import accounts.notification_storage as notification_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import PartyRole, User
from backend.app.core.auth import get_current_user, require_party_role
from backend.app.core.deps import get_db_path, get_media_dir
from backend.app.schemas.accounts import (
    GuestListEntry,
    InvitationCreate,
    InvitationPublic,
    PartyCreate,
    PartyGuestsResponse,
    PartyPublic,
    PartyUpdate,
)
from backend.app.schemas.discover import PartyPublishRequest

router = APIRouter(prefix="/api/v1/parties", tags=["parties"])

_MAX_COVER_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def _to_party_public(party, publication=None) -> PartyPublic:
    return PartyPublic(
        id=party.id, host_user_id=party.host_user_id, name=party.name, description=party.description,
        starts_at=party.starts_at, location=party.location, cover_image=party.cover_image,
        is_published=publication is not None,
        event_type=publication.event_type if publication is not None else "",
        interest_tags=publication.interest_tags if publication is not None else [],
        created_at=party.created_at, updated_at=party.updated_at,
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
    return _to_party_public(party, discover_storage.get_publication(db_path, party_id))


@router.patch("/{party_id}", response_model=PartyPublic)
def update_party(
    party_id: str,
    payload: PartyUpdate,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> PartyPublic:
    party = party_storage.update_party(db_path, party_id, **payload.model_dump(exclude_unset=True))
    return _to_party_public(party, discover_storage.get_publication(db_path, party_id))


@router.post("/{party_id}/publish", response_model=PartyPublic)
def publish_party(
    party_id: str,
    payload: PartyPublishRequest,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST})),
) -> PartyPublic:
    """Macht eine bereits existierende private Party im Discover-Deck
    anderer User sichtbar (MVP-Scope-Entscheidung: kein separater Event-
    Erstellungs-Flow, siehe Plan). Nur der Host darf das."""
    discover_storage.publish_party(db_path, party_id, event_type=payload.event_type, interest_tags=payload.interest_tags)
    party = party_storage.get_party(db_path, party_id)
    return _to_party_public(party, discover_storage.get_publication(db_path, party_id))


@router.delete("/{party_id}/publish", status_code=status.HTTP_204_NO_CONTENT)
def unpublish_party(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST})),
) -> None:
    discover_storage.unpublish_party(db_path, party_id)


@router.post("/{party_id}/cover-image", response_model=PartyPublic)
async def upload_party_cover_image(
    party_id: str,
    file: UploadFile,
    db_path: Path = Depends(get_db_path),
    media_dir: Path = Depends(get_media_dir),
    _membership=Depends(require_party_role({PartyRole.HOST})),
) -> PartyPublic:
    """Party-Cover-Bild ("Party-Motto"-Foto fürs Discover-Deck) - identisches
    Pillow-Verify+Re-Encode-Muster wie ``me.py::upload_profile_image`` (fester
    serverseitiger Dateiname, nie der Client-Dateiname/-Content-Type), nur
    unter einem eigenen ``party_images``-Unterordner desselben ``/media``-
    Mounts (kein neues StaticFiles-Mount/Setting nötig)."""
    raw = await file.read()
    if len(raw) > _MAX_COVER_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Cover image too large.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")

    party_images_dir = media_dir.parent / "party_images"
    party_images_dir.mkdir(parents=True, exist_ok=True)
    destination = party_images_dir / f"{party_id}.jpg"
    image.save(destination, format="JPEG")

    relative_path = f"party_images/{party_id}.jpg"
    party_storage.set_cover_image(db_path, party_id, relative_path)
    party = party_storage.get_party(db_path, party_id)
    return _to_party_public(party, discover_storage.get_publication(db_path, party_id))


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
    party = party_storage.get_party(db_path, party_id)
    party_name = party.name if party is not None else party_id
    notification_storage.create_notification(
        db_path, uuid.uuid4().hex, invited_user.id, party_id, "invitation",
        f"You've been invited to {party_name}.",
    )
    return InvitationPublic(
        id=invitation.id, party_id=invitation.party_id, host_user_id=invitation.host_user_id,
        invited_user_id=invitation.invited_user_id, status=invitation.status.value,
        invitation_message=invitation.invitation_message, version=invitation.version,
        created_at=invitation.created_at, viewed_at=invitation.viewed_at, responded_at=invitation.responded_at,
    )
