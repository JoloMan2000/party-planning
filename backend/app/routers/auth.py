from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError

import accounts.user_storage as user_storage
from accounts.domain import User
from backend.app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from backend.app.core.deps import get_db_path
from backend.app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SignupRequest,
    UserPublic,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _token_response(db_path: Path, user: User) -> AuthTokenResponse:
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(db_path, user.id)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserPublic(
            id=user.id, email=user.email, display_name=user.display_name,
            profile_image=user.profile_image, created_at=user.created_at,
        ),
    )


@router.post("/signup", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db_path: Path = Depends(get_db_path)) -> AuthTokenResponse:
    try:
        user = user_storage.create_user(
            db_path, uuid.uuid4().hex, payload.email, hash_password(payload.password), payload.display_name
        )
    except user_storage.EmailAlreadyRegisteredError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-Mail bereits registriert.")
    return _token_response(db_path, user)


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest, db_path: Path = Depends(get_db_path)) -> AuthTokenResponse:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch.")
    creds = user_storage.get_credentials_by_email(db_path, payload.email)
    if creds is None:
        raise unauthorized
    user, password_hash = creds
    if not verify_password(payload.password, password_hash):
        raise unauthorized
    return _token_response(db_path, user)


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(payload: RefreshRequest, db_path: Path = Depends(get_db_path)) -> AuthTokenResponse:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh-Token ungültig.")
    try:
        refresh_payload = decode_refresh_token(payload.refresh_token)
    except (JWTError, ValueError):
        raise unauthorized

    jti = refresh_payload.get("jti")
    record = user_storage.get_refresh_token(db_path, jti) if jti else None
    if record is None or record.revoked_at is not None:
        # Wiederverwendung eines bereits rotierten/widerrufenen Tokens ist ein
        # Security-Event - kein stilles Neuausstellen, alle Tokens des Users
        # widerrufen (Reuse-Detection).
        if record is not None:
            user_storage.revoke_all_refresh_tokens_for_user(db_path, record.user_id)
        raise unauthorized

    user = user_storage.get_user_by_id(db_path, record.user_id)
    if user is None:
        raise unauthorized

    new_refresh_token = create_refresh_token(db_path, user.id)
    new_jti = decode_refresh_token(new_refresh_token)["jti"]
    user_storage.revoke_refresh_token(db_path, jti, replaced_by_id=new_jti)

    return AuthTokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=new_refresh_token,
        user=UserPublic(
            id=user.id, email=user.email, display_name=user.display_name,
            profile_image=user.profile_image, created_at=user.created_at,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db_path: Path = Depends(get_db_path)) -> None:
    try:
        refresh_payload = decode_refresh_token(payload.refresh_token)
    except (JWTError, ValueError):
        return None
    jti = refresh_payload.get("jti")
    if jti:
        user_storage.revoke_refresh_token(db_path, jti)
    return None
