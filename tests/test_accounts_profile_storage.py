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


def test_neues_profil_hat_leeren_username(db_path):
    profile = profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    assert profile.username == ""


def test_username_kann_gesetzt_werden(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    updated = profile_storage.upsert_user_profile(db_path, "user-1", username="MaxM")
    assert updated.username == "MaxM"


def test_username_none_laesst_bestehenden_wert_unveraendert(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1), username="MaxM")
    unchanged = profile_storage.upsert_user_profile(db_path, "user-1", gender="woman")
    assert unchanged.username == "MaxM"
    assert unchanged.gender == "woman"


def test_username_eindeutigkeit_ist_case_insensitiv(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1), username="MaxM")
    profile_storage.upsert_user_profile(db_path, "user-2", birth_date=date(1990, 1, 1))
    with pytest.raises(profile_storage.UsernameAlreadyTakenError):
        profile_storage.upsert_user_profile(db_path, "user-2", username="maxm")


def test_is_username_available(db_path):
    assert profile_storage.is_username_available(db_path, "maxm") is True
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1), username="MaxM")
    assert profile_storage.is_username_available(db_path, "maxm") is False
    assert profile_storage.is_username_available(db_path, "MAXM") is False
    assert profile_storage.is_username_available(db_path, "someoneelse") is True


# --- Social-Graph-Phase-3: Privacy-Felder ---------------------------------


def test_neues_profil_hat_privacy_defaults(db_path):
    profile = profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    assert profile.friend_list_visibility == "friends"
    assert profile.friend_request_privacy == "everyone"
    assert profile.discoverable_by_username is True
    assert profile.discoverable_by_name is True


def test_friend_list_visibility_kann_gesetzt_werden(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    updated = profile_storage.upsert_user_profile(db_path, "user-1", friend_list_visibility="nobody")
    assert updated.friend_list_visibility == "nobody"


def test_friend_request_privacy_kann_gesetzt_werden(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    updated = profile_storage.upsert_user_profile(db_path, "user-1", friend_request_privacy="nobody")
    assert updated.friend_request_privacy == "nobody"


def test_discoverable_flags_unabhaengig_setzbar(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    updated = profile_storage.upsert_user_profile(db_path, "user-1", discoverable_by_username=False)
    assert updated.discoverable_by_username is False
    assert updated.discoverable_by_name is True  # unveraendert

    updated2 = profile_storage.upsert_user_profile(db_path, "user-1", discoverable_by_name=False)
    assert updated2.discoverable_by_username is False  # bleibt vom vorigen Aufruf
    assert updated2.discoverable_by_name is False


def test_privacy_felder_none_lassen_bestehende_werte_unveraendert(db_path):
    profile_storage.upsert_user_profile(
        db_path, "user-1", birth_date=date(1995, 1, 1),
        friend_list_visibility="everyone", friend_request_privacy="nobody",
        discoverable_by_username=False, discoverable_by_name=False,
    )
    unchanged = profile_storage.upsert_user_profile(db_path, "user-1", gender="woman")
    assert unchanged.friend_list_visibility == "everyone"
    assert unchanged.friend_request_privacy == "nobody"
    assert unchanged.discoverable_by_username is False
    assert unchanged.discoverable_by_name is False


def test_init_profile_storage_migration_ist_idempotent_mit_privacy_feldern(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1), friend_list_visibility="nobody")
    profile_storage.init_profile_storage(db_path)  # erneuter Aufruf darf Werte nicht zuruecksetzen
    survived = profile_storage.get_user_profile(db_path, "user-1")
    assert survived.friend_list_visibility == "nobody"


# --- Social-Graph-Phase-7: following_visibility --------------------------


def test_neues_profil_hat_following_visibility_default_nobody(db_path):
    profile = profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    assert profile.following_visibility == "nobody"


def test_following_visibility_kann_gesetzt_werden(db_path):
    profile_storage.upsert_user_profile(db_path, "user-1", birth_date=date(1995, 1, 1))
    updated = profile_storage.upsert_user_profile(db_path, "user-1", following_visibility="friends")
    assert updated.following_visibility == "friends"
    updated2 = profile_storage.upsert_user_profile(db_path, "user-1", following_visibility="everyone")
    assert updated2.following_visibility == "everyone"


def test_following_visibility_none_laesst_bestehenden_wert_unveraendert(db_path):
    profile_storage.upsert_user_profile(
        db_path, "user-1", birth_date=date(1995, 1, 1), following_visibility="everyone",
        friend_list_visibility="nobody",
    )
    unchanged = profile_storage.upsert_user_profile(db_path, "user-1", gender="woman")
    assert unchanged.following_visibility == "everyone"
    assert unchanged.friend_list_visibility == "nobody"  # unabhaengiges Feld unberuehrt


def test_init_profile_storage_migration_ist_idempotent_mit_following_visibility(db_path):
    profile_storage.upsert_user_profile(
        db_path, "user-1", birth_date=date(1995, 1, 1), following_visibility="everyone"
    )
    profile_storage.init_profile_storage(db_path)
    survived = profile_storage.get_user_profile(db_path, "user-1")
    assert survived.following_visibility == "everyone"
