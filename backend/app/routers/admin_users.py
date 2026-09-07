from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.user_storage as user_storage
from accounts.domain import User
from backend.app.core.auth import require_admin
from backend.app.core.deps import get_db_path
from backend.app.schemas.admin import UserAdminPublic

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])


def _to_user_admin_public(user: User) -> UserAdminPublic:
    return UserAdminPublic(
        id=user.id, email=user.email, display_name=user.display_name,
        is_verified=user.is_verified, created_at=user.created_at,
    )


@router.get("", response_model=list[UserAdminPublic])
def list_users(
    db_path: Path = Depends(get_db_path), _admin: User = Depends(require_admin)
) -> list[UserAdminPublic]:
    return [_to_user_admin_public(user) for user in user_storage.list_users(db_path)]


@router.post("/{user_id}/verify", response_model=UserAdminPublic)
def verify_user(
    user_id: str, db_path: Path = Depends(get_db_path), _admin: User = Depends(require_admin)
) -> UserAdminPublic:
    user = user_storage.get_user_by_id(db_path, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden.")
    user_storage.set_user_verified(db_path, user_id, True)
    return _to_user_admin_public(user_storage.get_user_by_id(db_path, user_id))


@router.delete("/{user_id}/verify", response_model=UserAdminPublic)
def unverify_user(
    user_id: str, db_path: Path = Depends(get_db_path), _admin: User = Depends(require_admin)
) -> UserAdminPublic:
    user = user_storage.get_user_by_id(db_path, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden.")
    user_storage.set_user_verified(db_path, user_id, False)
    return _to_user_admin_public(user_storage.get_user_by_id(db_path, user_id))
