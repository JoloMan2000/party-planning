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
    get_current_user,
    hash_password,
    verify_password,
)
from backend.app.core.config import settings
from backend.app.core.deps import get_db_path
from backend.app.schemas.auth import (
    AccountUnlockConfirmRequest,
    AccountUnlockRequest,
    AccountUnlockRequestResponse,
    AuthTokenResponse,
    EmailVerificationConfirmRequest,
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
_GENERIC_UNLOCK_REQUEST_RESPONSE = AccountUnlockRequestResponse()
_INVALID_OR_EXPIRED_TOKEN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token."
)
_PASSWORD_RESET_TOKEN_EXPIRY_MINUTES = 30
_EMAIL_VERIFICATION_TOKEN_EXPIRY_MINUTES = 60 * 24
# Einmal beim Modul-Import berechneter, echter Argon2-Hash für ein
# Zufallspasswort, das zu keinem echten Account gehört (Security-Hardening-
# Pass). Ohne diesen Dummy-Hash würde `verify_password` in login() nur für
# tatsächlich registrierte E-Mails aufgerufen - Argon2 ist absichtlich
# langsam, also könnte ein Angreifer über die Response-Zeit unterscheiden,
# ob eine E-Mail-Adresse einen Account hat, selbst wenn Lockout/401-Body
# identisch aussehen. `verify_password` läuft jetzt IMMER, egal ob `creds`
# existiert.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
_ACCOUNT_UNLOCK_TOKEN_EXPIRY_MINUTES = 30


def _token_response(db_path: Path, user: User) -> AuthTokenResponse:
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(db_path, user.id)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserPublic(
            id=user.id, email=user.email, display_name=user.display_name,
            profile_image=user.profile_image, email_verified=user.email_verified, created_at=user.created_at,
        ),
    )


def _send_verification_email(db_path: Path, user: User) -> None:
    token_id = uuid.uuid4().hex
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_EMAIL_VERIFICATION_TOKEN_EXPIRY_MINUTES)

    user_storage.create_email_verification_token(db_path, token_id, user.id, token_hash, expires_at)

    verify_link = f"{settings.email_verification_base_url}/{token_id}:{raw_token}"
    try:
        email_sender.send_verification_email(user.email, verify_link)
    except Exception:
        # SMTP-Fehler dürfen Signup nie fehlschlagen lassen (non-blocking
        # Email-Verification, siehe Plan) - der Token bleibt trotzdem gültig,
        # falls die E-Mail doch ankommt oder per Resend erneut versucht wird.
        pass


@router.post("/signup", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db_path: Path = Depends(get_db_path)) -> AuthTokenResponse:
    try:
        user = user_storage.create_user(
            db_path, uuid.uuid4().hex, payload.email, hash_password(payload.password), payload.display_name
        )
    except user_storage.EmailAlreadyRegisteredError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-Mail bereits registriert.")
    _send_verification_email(db_path, user)
    return _token_response(db_path, user)


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest, db_path: Path = Depends(get_db_path)) -> AuthTokenResponse:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch.")
    locked = HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed login attempts. Please try again later.",
    )
    blocked = HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail="Account blocked due to repeated failed login attempts. Check your email to unlock it.",
    )
    email = payload.email.strip().lower()

    # Lockout-Check läuft VOR dem Credential-Lookup und hängt ausschließlich
    # von der eingegebenen E-Mail-Zeichenkette ab, nicht davon, ob dahinter
    # ein echter Account steckt - sonst würde das Lockout-Verhalten selbst zu
    # einem E-Mail-Enumeration-Kanal (registrierte vs. unregistrierte
    # Adressen würden sich nach mehreren Versuchen unterschiedlich verhalten).
    # Tier 3 (`blocked_at`) hat KEINEN Auto-Ablauf - nur der E-Mail-Unlock-Flow
    # löscht die `login_attempts`-Zeile, daher wird dieser Zweig zuerst geprüft.
    attempt = user_storage.get_login_attempt(db_path, email)
    if attempt is not None:
        if attempt.blocked_at is not None:
            raise blocked
        if attempt.locked_until is not None:
            locked_until = (
                attempt.locked_until
                if attempt.locked_until.tzinfo
                else attempt.locked_until.replace(tzinfo=timezone.utc)
            )
            if datetime.now(timezone.utc) < locked_until:
                raise locked

    creds = user_storage.get_credentials_by_email(db_path, email)
    password_hash = creds[1] if creds is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, password_hash)
    if creds is None or not password_valid:
        user_storage.record_failed_login(
            db_path,
            email,
            tier1_max_attempts=settings.login_tier1_max_attempts,
            tier1_lockout_minutes=settings.login_tier1_lockout_minutes,
            tier2_max_attempts=settings.login_tier2_max_attempts,
            tier2_lockout_minutes=settings.login_tier2_lockout_minutes,
            tier3_max_attempts=settings.login_tier3_max_attempts,
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
            profile_image=user.profile_image, email_verified=user.email_verified, created_at=user.created_at,
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


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: EmailVerificationConfirmRequest, db_path: Path = Depends(get_db_path)) -> None:
    token_id, _, raw_token = payload.token.partition(":")
    if not token_id or not raw_token:
        raise _INVALID_OR_EXPIRED_TOKEN

    record = user_storage.get_email_verification_token(db_path, token_id)
    if record is None or record.used_at is not None:
        raise _INVALID_OR_EXPIRED_TOKEN

    now = datetime.now(timezone.utc)
    expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise _INVALID_OR_EXPIRED_TOKEN

    token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    if not hmac.compare_digest(token_hash, record.token_hash):
        raise _INVALID_OR_EXPIRED_TOKEN

    user_storage.set_email_verified(db_path, record.user_id, True)
    user_storage.mark_email_verification_token_used(db_path, token_id)
    return None


@router.post("/resend-verification-email", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification_email(
    db_path: Path = Depends(get_db_path), current_user: User = Depends(get_current_user)
) -> None:
    if current_user.email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified.")
    user_storage.invalidate_email_verification_tokens_for_user(db_path, current_user.id)
    _send_verification_email(db_path, current_user)
    return None


@router.post("/request-account-unlock", response_model=AccountUnlockRequestResponse)
def request_account_unlock(
    payload: AccountUnlockRequest, db_path: Path = Depends(get_db_path)
) -> AccountUnlockRequestResponse:
    """Löst immer den identischen 200-Response aus, egal ob die E-Mail
    existiert (mirrors ``request_password_reset``) - und egal ob der Account
    aktuell überhaupt gesperrt/blockiert ist (harmlos: ein Unlock-Link für
    einen nicht blockierten Account ist ein No-Op beim Einlösen)."""
    user = user_storage.get_user_by_email(db_path, payload.email)
    if user is not None:
        token_id = uuid.uuid4().hex
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=_ACCOUNT_UNLOCK_TOKEN_EXPIRY_MINUTES)

        user_storage.invalidate_account_unlock_tokens_for_user(db_path, user.id)
        user_storage.create_account_unlock_token(db_path, token_id, user.id, token_hash, expires_at)

        unlock_link = f"{settings.account_unlock_base_url}/{token_id}:{raw_token}"
        try:
            email_sender.send_account_unlock_email(user.email, unlock_link)
        except Exception:
            pass
    return _GENERIC_UNLOCK_REQUEST_RESPONSE


@router.post("/unlock-account", status_code=status.HTTP_204_NO_CONTENT)
def unlock_account(payload: AccountUnlockConfirmRequest, db_path: Path = Depends(get_db_path)) -> None:
    token_id, _, raw_token = payload.token.partition(":")
    if not token_id or not raw_token:
        raise _INVALID_OR_EXPIRED_TOKEN

    record = user_storage.get_account_unlock_token(db_path, token_id)
    if record is None or record.used_at is not None:
        raise _INVALID_OR_EXPIRED_TOKEN

    now = datetime.now(timezone.utc)
    expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise _INVALID_OR_EXPIRED_TOKEN

    token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
    if not hmac.compare_digest(token_hash, record.token_hash):
        raise _INVALID_OR_EXPIRED_TOKEN

    user = user_storage.get_user_by_id(db_path, record.user_id)
    if user is None:
        raise _INVALID_OR_EXPIRED_TOKEN

    # Löscht NUR die Lockout-Zeile (kein Passwort-Reset, keine Token-
    # Revocation) - unlocking ist kein Signal für Kompromittierung wie ein
    # Passwort-Reset, siehe Plan Entscheidung #4.
    user_storage.reset_login_attempts(db_path, user.email)
    user_storage.mark_account_unlock_token_used(db_path, token_id)
    return None
