from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError

import accounts.user_storage as user_storage
from accounts import email_sender
from accounts.domain import User
from backend.app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from backend.app.core.config import settings
from backend.app.core.deps import get_db_path
from backend.app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RefreshRequest,
    SignupRequest,
    UserPublic,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_GENERIC_RESET_REQUEST_RESPONSE = PasswordResetRequestResponse()
_INVALID_OR_EXPIRED_TOKEN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token."
)
_PASSWORD_RESET_TOKEN_EXPIRY_MINUTES = 30


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
    locked = HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed login attempts. Please try again later.",
    )
    email = payload.email.strip().lower()

    # Lockout-Check läuft VOR dem Credential-Lookup und hängt ausschließlich
    # von der eingegebenen E-Mail-Zeichenkette ab, nicht davon, ob dahinter
    # ein echter Account steckt - sonst würde das Lockout-Verhalten selbst zu
    # einem E-Mail-Enumeration-Kanal (registrierte vs. unregistrierte
    # Adressen würden sich nach mehreren Versuchen unterschiedlich verhalten).
    attempt = user_storage.get_login_attempt(db_path, email)
    if attempt is not None and attempt.locked_until is not None:
        locked_until = (
            attempt.locked_until if attempt.locked_until.tzinfo else attempt.locked_until.replace(tzinfo=timezone.utc)
        )
        if datetime.now(timezone.utc) < locked_until:
            raise locked

    creds = user_storage.get_credentials_by_email(db_path, email)
    if creds is None or not verify_password(payload.password, creds[1]):
        user_storage.record_failed_login(
            db_path,
            email,
            max_attempts=settings.login_max_failed_attempts,
            lockout_minutes=settings.login_lockout_minutes,
        )
        raise unauthorized

    user_storage.reset_login_attempts(db_path, email)
    user, _password_hash = creds
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


@router.post("/request-password-reset", response_model=PasswordResetRequestResponse)
def request_password_reset(
    payload: PasswordResetRequest, db_path: Path = Depends(get_db_path)
) -> PasswordResetRequestResponse:
    """Löst immer den identischen 200-Response aus, egal ob die E-Mail
    existiert - Account-Existenz darf niemals über Response-Unterschiede
    oder Timing verraten werden."""
    user = user_storage.get_user_by_email(db_path, payload.email)
    if user is not None:
        token_id = uuid.uuid4().hex
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=_PASSWORD_RESET_TOKEN_EXPIRY_MINUTES)

        user_storage.invalidate_password_reset_tokens_for_user(db_path, user.id)
        user_storage.create_password_reset_token(db_path, token_id, user.id, token_hash, expires_at)

        reset_link = f"{settings.password_reset_base_url}/{token_id}:{raw_token}"
        try:
            email_sender.send_password_reset_email(user.email, reset_link)
        except Exception:
            # SMTP-Fehler dürfen weder die Response ändern noch die Account-
            # Existenz verraten - der Token bleibt trotzdem gültig, falls die
            # E-Mail doch ankommt oder der Link anderweitig zugestellt wird.
            pass
    return _GENERIC_RESET_REQUEST_RESPONSE


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: PasswordResetConfirmRequest, db_path: Path = Depends(get_db_path)) -> None:
    token_id, _, raw_token = payload.token.partition(":")
    if not token_id or not raw_token:
        raise _INVALID_OR_EXPIRED_TOKEN

    record = user_storage.get_password_reset_token(db_path, token_id)
    if record is None or record.used_at is not None:
        raise _INVALID_OR_EXPIRED_TOKEN

    now = datetime.now(timezone.utc)
    expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise _INVALID_OR_EXPIRED_TOKEN

    token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    if not hmac.compare_digest(token_hash, record.token_hash):
        raise _INVALID_OR_EXPIRED_TOKEN

    current_password_hash = user_storage.get_password_hash_by_user_id(db_path, record.user_id)
    if current_password_hash is None:
        raise _INVALID_OR_EXPIRED_TOKEN
    if verify_password(payload.new_password, current_password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from current password.",
        )

    user_storage.update_password_hash(db_path, record.user_id, hash_password(payload.new_password))
    user_storage.mark_password_reset_token_used(db_path, token_id)
    user_storage.revoke_all_refresh_tokens_for_user(db_path, record.user_id)
    return None
