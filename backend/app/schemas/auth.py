from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

_SPECIAL_CHARS = re.compile(r"[^A-Za-z0-9]")


class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str

    @field_validator("password")
    @classmethod
    def _password_muss_stark_sein(cls, value: str) -> str:
        """Erzwingt starke Passwörter beim Signup (mind. 12 Zeichen, Groß-
        und Kleinbuchstaben, Ziffer, Sonderzeichen) - schützt Nutzerkonten
        vor leicht zu erratenden/brute-forcebaren Passwörtern."""
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


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str
    profile_image: str = ""
    created_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic
