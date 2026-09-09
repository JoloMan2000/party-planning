"""Pytest-Unit-Tests für ``social.search`` (Social-Graph-Phase-1/3).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

import accounts.profile_storage as profile_storage
import accounts.user_storage as user_storage
import social.search as search


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "search_test.db"
    user_storage.init_user_storage(path)
    profile_storage.init_profile_storage(path)
    return path


@pytest.fixture()
def me(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "me@example.com", "hash", "Me")


def _make_user(db_path, email, display_name, username=None, **privacy):
    user = user_storage.create_user(db_path, uuid.uuid4().hex, email, "hash", display_name)
    profile_storage.upsert_user_profile(db_path, user.id, birth_date=date(1990, 1, 1), username=username, **privacy)
    return user


def test_search_findet_per_username(db_path, me):
    target = _make_user(db_path, "target@example.com", "Target Person", username="TargetHandle")
    results = search.search_users(db_path, "targethandle", exclude_user_id=me.id)
    assert any(r.user_id == target.id for r in results)


def test_search_findet_per_display_name(db_path, me):
    target = _make_user(db_path, "target2@example.com", "Very Unique Name")
    results = search.search_users(db_path, "Very Unique", exclude_user_id=me.id)
    assert any(r.user_id == target.id for r in results)


def test_search_discoverable_by_username_false_versteckt_nur_username_treffer(db_path, me):
    target = _make_user(
        db_path, "target3@example.com", "Hidden Handle Person", username="hiddenhandle123",
        discoverable_by_username=False,
    )
    assert not any(r.user_id == target.id for r in search.search_users(db_path, "hiddenhandle123", exclude_user_id=me.id))
    assert any(r.user_id == target.id for r in search.search_users(db_path, "Hidden Handle", exclude_user_id=me.id))


def test_search_discoverable_by_name_false_versteckt_nur_name_treffer(db_path, me):
    target = _make_user(
        db_path, "target4@example.com", "Secret Name Person", username="opennhandle456",
        discoverable_by_name=False,
    )
    assert not any(r.user_id == target.id for r in search.search_users(db_path, "Secret Name", exclude_user_id=me.id))
    assert any(r.user_id == target.id for r in search.search_users(db_path, "opennhandle456", exclude_user_id=me.id))


def test_search_beide_toggles_aus_macht_user_vollstaendig_unsichtbar(db_path, me):
    target = _make_user(
        db_path, "target5@example.com", "Totally Hidden Person", username="totallyhidden789",
        discoverable_by_username=False, discoverable_by_name=False,
    )
    assert search.search_users(db_path, "totallyhidden789", exclude_user_id=me.id) == []
    assert search.search_users(db_path, "Totally Hidden", exclude_user_id=me.id) == []


def test_search_user_ohne_profil_ist_per_default_discoverable(db_path, me):
    # Kein upsert_user_profile-Aufruf -> keine user_profiles-Zeile -> COALESCE(..., 1)-Default greift.
    target = user_storage.create_user(db_path, uuid.uuid4().hex, "noprofile@example.com", "hash", "No Profile Person")
    results = search.search_users(db_path, "No Profile", exclude_user_id=me.id)
    assert any(r.user_id == target.id for r in results)


def test_search_treffer_in_beiden_zweigen_wird_nicht_dupliziert(db_path, me):
    target = _make_user(db_path, "target6@example.com", "Overlap Overlap", username="overlapoverlap")
    results = search.search_users(db_path, "overlap", exclude_user_id=me.id)
    matching = [r for r in results if r.user_id == target.id]
    assert len(matching) == 1


def test_search_limit_wirkt_auf_kombiniertes_ergebnis(db_path, me):
    for i in range(5):
        _make_user(db_path, f"limituser{i}@example.com", f"LimitMatch Person {i}", username=f"limitmatch{i}")
    results = search.search_users(db_path, "limitmatch", exclude_user_id=me.id, limit=3)
    assert len(results) == 3
