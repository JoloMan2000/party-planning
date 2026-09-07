"""Pytest-Unit-Tests für ``accounts/profile_storage.py`` (Onboarding-Spec,
Phase 6). Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst
um eine pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

from datetime import date

import pytest

import accounts.profile_storage as profile_storage


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "profile_test.db"
    profile_storage.init_profile_storage(path)
    return path


def test_get_user_profile_none_wenn_nicht_angelegt(db_path):
    assert profile_storage.get_user_profile(db_path, "user-1") is None


def test_upsert_user_profile_erfordert_birth_date_beim_anlegen(db_path):
    with pytest.raises(ValueError):
        profile_storage.upsert_user_profile(db_path, "user-1", gender="x")


def test_upsert_user_profile_aendert_bestehendes_birth_date_nicht(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    updated = profile_storage.upsert_user_profile(db_path, "user-1", gender="woman")
    assert updated.birth_date == date(1995, 1, 1)
    assert updated.gender == "woman"


def test_apply_birth_date_correction_schreibt_audit_log_und_aendert_datum(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    corrected = profile_storage.apply_birth_date_correction(db_path, "user-1", date(1994, 6, 1), reason="Typo")
    assert corrected.birth_date == date(1994, 6, 1)


def test_apply_birth_date_correction_kann_profil_initial_anlegen(db_path):
    corrected = profile_storage.apply_birth_date_correction(db_path, "user-2", date(2000, 1, 1))
    assert corrected.birth_date == date(2000, 1, 1)


def test_mark_onboarding_completed_setzt_timestamp_und_version(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    completed = profile_storage.mark_onboarding_completed(db_path, "user-1", profile_completion_version=2)
    assert completed.onboarding_completed_at is not None
    assert completed.profile_completion_version == 2
