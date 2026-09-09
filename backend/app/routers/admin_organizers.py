"""Admin-Verification-Flow für Organizer (Social-Graph-Phase-4) - exakter
struktureller Spiegel von ``admin_users.py`` (dem LEGACY, jetzt
funktional abgelösten Verification-Flow), reuse von ``require_admin``
ohne Änderung (dessen eigener Docstring nennt das explizit als
vorgesehenen Zweck)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import organizers.storage as organizers_storage
from accounts.domain import User
from backend.app.core.auth import require_admin
from backend.app.core.deps import get_db_path
from backend.app.schemas.admin import OrganizerAdminPublic
from organizers.domain import Organizer, OrganizerVerificationStatus

router = APIRouter(prefix="/api/v1/admin/organizers", tags=["admin"])


def _to_organizer_admin_public(organizer: Organizer) -> OrganizerAdminPublic:
    return OrganizerAdminPublic(
        id=organizer.id, owner_user_id=organizer.owner_user_id, display_name=organizer.display_name,
        verification_status=organizer.verification_status.value, created_at=organizer.created_at,
    )


@router.get("", response_model=list[OrganizerAdminPublic])
def list_organizers(
    db_path: Path = Depends(get_db_path), _admin: User = Depends(require_admin)
) -> list[OrganizerAdminPublic]:
    return [_to_organizer_admin_public(organizer) for organizer in organizers_storage.list_organizers(db_path)]


@router.post("/{organizer_id}/verify", response_model=OrganizerAdminPublic)
def verify_organizer(
    organizer_id: str, db_path: Path = Depends(get_db_path), _admin: User = Depends(require_admin)
) -> OrganizerAdminPublic:
    organizer = organizers_storage.get_organizer(db_path, organizer_id)
    if organizer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer nicht gefunden.")
    organizers_storage.set_verification_status(db_path, organizer_id, OrganizerVerificationStatus.VERIFIED)
    return _to_organizer_admin_public(organizers_storage.get_organizer(db_path, organizer_id))


@router.delete("/{organizer_id}/verify", response_model=OrganizerAdminPublic)
def unverify_organizer(
    organizer_id: str, db_path: Path = Depends(get_db_path), _admin: User = Depends(require_admin)
) -> OrganizerAdminPublic:
    organizer = organizers_storage.get_organizer(db_path, organizer_id)
    if organizer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer nicht gefunden.")
    organizers_storage.set_verification_status(db_path, organizer_id, OrganizerVerificationStatus.UNVERIFIED)
    return _to_organizer_admin_public(organizers_storage.get_organizer(db_path, organizer_id))
