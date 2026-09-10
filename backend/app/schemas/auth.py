from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

_SPECIAL_CHARS = re.compile(r"[^A-Za-z0-9]")


def validate_strong_password(value: str) -> str:
    """Erzwingt starke Passwörter (mind. 12 Zeichen, Groß- und
    Kleinbuchstaben, Ziffer, Sonderzeichen) - schützt Nutzerkonten vor
    leicht zu erratenden/brute-forcebaren Passwörtern. Geteilt zwischen
    Signup und Password-Reset (siehe ``PasswordResetConfirmRequest``
    unten), damit beide Code-Pfade exakt dieselbe Policy durchsetzen."""
    if len(value) < 12:
        raise ValueError("Passwort muss mindestens 12 Zeichen lang sein.")
    if not re.search(r"[a-z]", value):
        raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten.")
    if not re.search(r"[A-Z]", value):
        raise ValueError("Passwort muss mindestens einen Großbuchstaben enthalten.")
    if not re.search(r"[0-9]", value):
        raise ValueError("Passwort muss mindestens eine Ziffer enthalten.")
    if not _SPECIAL_CHARS.search(value):
        raise ValueError("Passwort muss mindestens ein Sonderzeichen enthalten.")
    return value


class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str

    @field_validator("password")
    @classmethod
    def _password_muss_stark_sein(cls, value: str) -> str:
        return validate_strong_password(value)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class AccountDeleteRequest(BaseModel):
    """Social-Graph-Phase-10 (Spec §104) - Re-Auth per aktuellem Passwort
    für den irreversiblen ``DELETE /api/v1/me``."""

    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_muss_stark_sein(cls, value: str) -> str:
        return validate_strong_password(value)


class PasswordResetRequestResponse(BaseModel):
    message: str = "If that email is registered, a password reset link has been sent."


class EmailVerificationConfirmRequest(BaseModel):
    token: str


class AccountUnlockRequest(BaseModel):
    email: str


class AccountUnlockConfirmRequest(BaseModel):
    token: str


class AccountUnlockRequestResponse(BaseModel):
    message: str = "If that account exists, an unlock link has been sent to its email address."


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str
    profile_image: str = ""
    email_verified: bool = False
    created_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic
