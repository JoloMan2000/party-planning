"""User-Auth (Account-basierter Pivot, Phase 1) - ersetzt das gemeinsame
Admin-Passwort/-JWT aus ``backend/app/core/security.py`` (gelöscht) durch
echte User-Accounts mit Argon2id-Passwort-Hashing und Access-/Refresh-Token-
Paaren.

Access-Token: kurzlebig (15min), ``{"sub": user_id, "type": "access", "exp": ...}``.
Refresh-Token: langlebig (30 Tage), self-contained signiertes JWT mit ``jti``,
zusätzlich als SHA-256-Hash in ``refresh_tokens`` persistiert (Hybrid-Design) -
ermöglicht serverseitigen Widerruf/Rotation, ohne bei jedem Access-Token-Check
die DB anfassen zu müssen.

``require_party_role``/``get_invitation_for_viewer``/``get_invitation_for_rsvp``
sind Dependency-Factories bzw. Dependencies, die die Rollen-/Ownership-Checks
aus der AUFGABE-Spec (§47/§48: ``user_id`` wird NIE aus dem Request-Body
vertraut, immer aus dem JWT-Principal abgeleitet) an einer Stelle bündeln.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

import accounts.invitation_storage as invitation_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import Invitation, PartyRole, User
from backend.app.core.config import settings
from backend.app.core.deps import get_db_path

_bearer_scheme = HTTPBearer(auto_error=False)
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(db_path: str | Path, user_id: str) -> str:
    jti = uuid.uuid4().hex
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": user_id, "type": "refresh", "jti": jti, "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    user_storage.save_refresh_token(db_path, jti, user_id, token_hash, issued_at, expires_at)
    return token


def decode_refresh_token(token: str) -> dict:
    """Prüft nur Signatur/Ablauf/``type``, keine DB-Zugriffe. Raises
    ``JWTError`` (Signatur ungültig/abgelaufen) oder ``ValueError`` (falscher
    Token-Typ)."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "refresh":
        raise ValueError("not a refresh token")
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db_path: Path = Depends(get_db_path),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nicht authentifiziert.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise unauthorized
    if payload.get("type") != "access":
        raise unauthorized
    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized
    user = user_storage.get_user_by_id(db_path, user_id)
    if user is None:
        raise unauthorized
    return user


def require_party_role(allowed_roles: set[PartyRole]):
    """Dependency-Factory: 404 falls Party unbekannt, 403 falls der User
    keine oder eine nicht ausreichende Rolle in dieser Party hat. Erwartet
    einen ``party_id``-Pfadparameter auf der Route."""

    def _dependency(
        party_id: str,
        current_user: User = Depends(get_current_user),
        db_path: Path = Depends(get_db_path),
    ):
        party = party_storage.get_party(db_path, party_id)
        if party is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")
        membership = party_storage.get_membership(db_path, party_id, current_user.id)
        if membership is None or membership.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Party.")
        return membership

    return _dependency


def get_invitation_for_viewer(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> Invitation:
    """Die eingeladene Person ODER Host/Co-Host der Party dürfen die
    Invitation ansehen."""
    invitation = invitation_storage.get_invitation(db_path, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden.")
    if current_user.id == invitation.invited_user_id:
        return invitation
    membership = party_storage.get_membership(db_path, invitation.party_id, current_user.id)
    if membership is not None and membership.role in (PartyRole.HOST, PartyRole.CO_HOST):
        return invitation
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Einladung.")


def get_invitation_for_rsvp(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> Invitation:
    """Strikt (AUFGABE-Spec §47/§48): NUR die eingeladene Person selbst darf
    per RSVP antworten - ``user_id`` wird nie aus dem Request-Body vertraut."""
    invitation = invitation_storage.get_invitation(db_path, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden.")
    if current_user.id != invitation.invited_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur die eingeladene Person darf antworten.")
    return invitation
