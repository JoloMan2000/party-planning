from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

import accounts.discover_storage as discover_storage
import accounts.invitation_storage as invitation_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import organizers.storage as organizers_storage
from accounts.domain import DiscoverAction, User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path, get_media_dir
from backend.app.schemas.accounts import InvitationPublic, PartyPublic
from backend.app.schemas.auth import UserPublic

router = APIRouter(prefix="/api/v1/me", tags=["me"])

_MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.get("", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(
        id=current_user.id, email=current_user.email, display_name=current_user.display_name,
        profile_image=current_user.profile_image, email_verified=current_user.email_verified,
        created_at=current_user.created_at,
    )


@router.get("/parties", response_model=list[PartyPublic])
def get_my_parties(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[PartyPublic]:
    parties = party_storage.list_parties_for_user(db_path, current_user.id)
    result = []
    for party, _membership in parties:
        publication = discover_storage.get_publication(db_path, party.id)
        discover_action = discover_storage.get_discover_action(db_path, current_user.id, party.id)
        my_discover_action = (
            discover_action.action.value
            if discover_action is not None and discover_action.action in (DiscoverAction.GOING, DiscoverAction.MAYBE)
            else None
        )
        result.append(
            PartyPublic(
                id=party.id, host_user_id=party.host_user_id, name=party.name, description=party.description,
                starts_at=party.starts_at, location=party.location, cover_image=party.cover_image,
                is_published=publication is not None,
                event_type=publication.event_type if publication is not None else "",
                interest_tags=publication.interest_tags if publication is not None else [],
                max_guests=publication.max_guests if publication is not None else 0,
                host_is_verified=organizers_storage.is_user_verified_organizer_member(db_path, party.host_user_id),
                my_discover_action=my_discover_action,
                created_at=party.created_at, updated_at=party.updated_at,
            )
        )
    return result


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


@router.post("/profile-image", response_model=UserPublic)
async def upload_profile_image(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    media_dir: Path = Depends(get_media_dir),
) -> UserPublic:
    """Nimmt ein Profilbild entgegen, re-encoded es serverseitig als JPEG unter
    einem FESTEN, vom Server bestimmten Dateinamen (``{user_id}.jpg``) - NIE
    der client-gelieferte Dateiname/Content-Type wird für Pfad oder Format
    übernommen. Das verhindert sowohl Path-Traversal (kein client-Pfad landet
    je in einem Dateisystempfad) als auch als Bild getarnte Nicht-Bild-
    Payloads (Pillow muss die Bytes tatsächlich als Bild dekodieren können -
    ein reines Content-Type-Vertrauen wäre hier unzureichend)."""
    raw = await file.read()
    if len(raw) > _MAX_PROFILE_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Profile image too large.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))  # verify() invalidiert das Image-Objekt, neu öffnen
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")

    media_dir.mkdir(parents=True, exist_ok=True)
    destination = media_dir / f"{current_user.id}.jpg"
    image.save(destination, format="JPEG")

    relative_path = f"profile_images/{current_user.id}.jpg"
    user_storage.update_profile_image(db_path, current_user.id, relative_path)
    updated = user_storage.get_user_by_id(db_path, current_user.id)
    return UserPublic(
        id=updated.id, email=updated.email, display_name=updated.display_name,
        profile_image=updated.profile_image, email_verified=updated.email_verified,
        created_at=updated.created_at,
    )
