from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.core.security import create_admin_token, verify_admin_password
from backend.app.schemas.auth import AdminLoginRequest, AdminLoginResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/admin/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest) -> AdminLoginResponse:
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falsches Passwort.")
    return AdminLoginResponse(access_token=create_admin_token())
