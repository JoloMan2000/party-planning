"""Social-Profile-Endpoints (Onboarding-Spec, Phase 6).

``birth_date`` ist bewusst NIE Teil von ``PATCH /me/profile`` (geschützt) -
der einzige Schreibpfad dafür ist ``POST /me/profile/birth-date-correction``,
der sowohl das initiale Setzen beim Onboarding ALS AUCH spätere Korrekturen
abdeckt (in beiden Fällen wird ein Audit-Eintrag geschrieben, siehe
``accounts/profile_storage.py::apply_birth_date_correction`` - bei
Erstanlage ist ``previous_birth_date`` dort einfach ``None``)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.profile_storage as profile_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.profile import (
    BirthDateCorrectionRequest,
    ProfilePublic,
    ProfileUpdateRequest,
)

router = APIRouter(prefix="/api/v1/me/profile", tags=["profile"])


def _calculate_age(birth_date: date) -> int:
    """Alter wird IMMER serverseitig berechnet, nie als statischer Wert
    gespeichert (Onboarding-Spec §Birth date)."""
    today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _to_public(profile) -> ProfilePublic:
    return ProfilePublic(
        user_id=profile.user_id,
        birth_date=profile.birth_date,
        age=_calculate_age(profile.birth_date),
        gender=profile.gender,
        bio=profile.bio,
        username=profile.username,
        onboarding_completed_at=profile.onboarding_completed_at,
        profile_completion_version=profile.profile_completion_version,
    )


@router.get("", response_model=ProfilePublic)
def get_profile(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> ProfilePublic:
    profile = profile_storage.get_user_profile(db_path, current_user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil noch nicht angelegt.")
    return _to_public(profile)


@router.patch("", response_model=ProfilePublic)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> ProfilePublic:
    existing = profile_storage.get_user_profile(db_path, current_user.id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profil muss zuerst über birth-date-correction (Onboarding) angelegt werden.",
        )
    try:
        profile = profile_storage.upsert_user_profile(
            db_path, current_user.id, gender=payload.gender, bio=payload.bio, username=payload.username
        )
    except profile_storage.UsernameAlreadyTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dieser Username ist bereits vergeben.")
    return _to_public(profile)


@router.post("/birth-date-correction", response_model=ProfilePublic)
def correct_birth_date(
    payload: BirthDateCorrectionRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> ProfilePublic:
    if payload.birth_date >= date.today():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Geburtsdatum muss in der Vergangenheit liegen.")
    if _calculate_age(payload.birth_date) < 13:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mindestalter nicht erreicht.")
    profile = profile_storage.apply_birth_date_correction(
        db_path, current_user.id, payload.birth_date, reason=payload.reason
    )
    return _to_public(profile)
