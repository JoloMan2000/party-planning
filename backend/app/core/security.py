"""Admin-JWT-Auth (Phase-1-Plan Schritt 4).

Ersetzt den trivialen ``?admin=<ADMIN_TOKEN>``-Query-Param-Vergleich aus
``"Party Planning.py"`` durch ein kurzlebiges JWT, ausgestellt nach
Password-Login. Bewusst simpel gehalten (ein gemeinsames Admin-Passwort,
kein Multi-User) - selbes Sicherheitsniveau wie heute (ein geteiltes
Secret), da noch kein echter Launch geplant ist (siehe Plan Schritt 4).

``get_current_admin`` ist bewusst so geschnitten, dass eine spätere
Auth-Härtung (z.B. Firebase/OAuth, Phase 4) NUR diese Datei anfasst - alle
Router hängen nur von der Dependency-Signatur ab, nicht von der
Implementierung dahinter.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_admin_password(password: str) -> bool:
    """Konstante-Zeit-Vergleich (kein Timing-Angriff auf das Passwort)."""
    return secrets.compare_digest(password, settings.admin_password)


def create_admin_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": "admin", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """FastAPI-Dependency, an jedem ``admin_*``-Router als All-or-Nothing-Gate
    angehängt (mirroring der heutigen ``is_admin``-Prüfung in
    ``"Party Planning.py"``)."""
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
    if payload.get("sub") != "admin":
        raise unauthorized
    return "admin"
