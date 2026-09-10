"""Pytest-Unit-Tests für ``social.follows`` (Social-Graph-Phase-5).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import organizers.storage as organizers_storage
import social.follows as follows


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "follows_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    organizers_storage.init_organizer_storage(path)
    follows.init_follow_storage(path)
    return path


@pytest.fixture()
def anna(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")


@pytest.fixture()
def max_(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")


@pytest.fixture()
def owner(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "owner@example.com", "hash", "Owner")


@pytest.fixture()
def organizer_a(db_path, owner):
    return organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Boiler Room")


@pytest.fixture()
def organizer_b(db_path, owner):
    return organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Berghain")


@pytest.fixture()
def party(db_path, owner):
    return party_storage.create_party(db_path, uuid.uuid4().hex, owner.id, "Summer Sound")


@pytest.fixture()
def party_b(db_path, owner):
    return party_storage.create_party(db_path, uuid.uuid4().hex, owner.id, "Winter Sound")


def test_init_ist_idempotent(db_path):
    follows.init_follow_storage(db_path)
    follows.init_follow_storage(db_path)


# --- Organizer follows -------------------------------------------------


def test_ohne_follow_is_following_organizer_false(db_path, anna, organizer_a):
    assert follows.is_following_organizer(db_path, anna.id, organizer_a.id) is False
    assert follows.list_organizer_follows(db_path, anna.id) == []
    assert follows.count_organizer_followers(db_path, organizer_a.id) == 0


def test_follow_organizer_legt_beziehung_an(db_path, anna, organizer_a):
    follow = follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    assert follow.user_id == anna.id
    assert follow.organizer_id == organizer_a.id
    assert follows.is_following_organizer(db_path, anna.id, organizer_a.id) is True


def test_follow_organizer_ist_idempotent(db_path, anna, organizer_a):
    first = follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    second = follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    assert first.id == second.id
    assert first.created_at == second.created_at
    assert follows.count_organizer_followers(db_path, organizer_a.id) == 1


def test_follow_organizer_ist_gerichtet(db_path, anna, max_, organizer_a):
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    assert follows.is_following_organizer(db_path, anna.id, organizer_a.id) is True
    assert follows.is_following_organizer(db_path, max_.id, organizer_a.id) is False


def test_count_organizer_followers_zaehlt_ueber_mehrere_user(db_path, anna, max_, organizer_a):
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    follows.follow_organizer(db_path, uuid.uuid4().hex, max_.id, organizer_a.id)
    assert follows.count_organizer_followers(db_path, organizer_a.id) == 2


def test_list_organizer_follows_neueste_zuerst(db_path, anna, organizer_a, organizer_b):
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_b.id)
    listed = follows.list_organizer_follows(db_path, anna.id)
    assert [f.organizer_id for f in listed] == [organizer_b.id, organizer_a.id]


def test_unfollow_organizer_entfernt_beziehung(db_path, anna, organizer_a):
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    follows.unfollow_organizer(db_path, anna.id, organizer_a.id)
    assert follows.is_following_organizer(db_path, anna.id, organizer_a.id) is False
    assert follows.count_organizer_followers(db_path, organizer_a.id) == 0


def test_unfollow_organizer_ohne_bestehenden_ist_no_op(db_path, anna, organizer_a):
    follows.unfollow_organizer(db_path, anna.id, organizer_a.id)
    assert follows.is_following_organizer(db_path, anna.id, organizer_a.id) is False


# --- Event follows ---------------------------------------------------


def test_ohne_follow_is_following_event_false(db_path, anna, party):
    assert follows.is_following_event(db_path, anna.id, party.id) is False
    assert follows.list_event_follows(db_path, anna.id) == []
    assert follows.count_event_followers(db_path, party.id) == 0


def test_follow_event_legt_beziehung_an(db_path, anna, party):
    follow = follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
    assert follow.user_id == anna.id
    assert follow.party_id == party.id
    assert follows.is_following_event(db_path, anna.id, party.id) is True


def test_follow_event_ist_idempotent(db_path, anna, party):
    first = follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
    second = follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
    assert first.id == second.id
    assert follows.count_event_followers(db_path, party.id) == 1


def test_list_event_follows_neueste_zuerst(db_path, anna, party, party_b):
    follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
    follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party_b.id)
    listed = follows.list_event_follows(db_path, anna.id)
    assert [f.party_id for f in listed] == [party_b.id, party.id]


def test_unfollow_event_entfernt_beziehung(db_path, anna, party):
    follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
    follows.unfollow_event(db_path, anna.id, party.id)
    assert follows.is_following_event(db_path, anna.id, party.id) is False


def test_unfollow_event_ohne_bestehenden_ist_no_op(db_path, anna, party):
    follows.unfollow_event(db_path, anna.id, party.id)
    assert follows.is_following_event(db_path, anna.id, party.id) is False


def test_unbekannte_ids_liefern_leere_defaults(db_path):
    assert follows.list_organizer_follows(db_path, "unknown") == []
    assert follows.count_organizer_followers(db_path, "unknown") == 0
    assert follows.list_event_follows(db_path, "unknown") == []
    assert follows.count_event_followers(db_path, "unknown") == 0
    assert follows.is_following_organizer(db_path, "unknown", "unknown") is False
    assert follows.is_following_event(db_path, "unknown", "unknown") is False


# --- Social-Graph-Phase-8: reverse follower-id lookups -----------------


def test_list_organizer_follower_ids_leer(db_path, organizer_a):
    assert follows.list_organizer_follower_ids(db_path, organizer_a.id) == []


def test_list_organizer_follower_ids_mehrere_und_isoliert_pro_organizer(db_path, anna, max_, organizer_a, organizer_b):
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_a.id)
    follows.follow_organizer(db_path, uuid.uuid4().hex, max_.id, organizer_a.id)
    follows.follow_organizer(db_path, uuid.uuid4().hex, anna.id, organizer_b.id)
    assert set(follows.list_organizer_follower_ids(db_path, organizer_a.id)) == {anna.id, max_.id}
    assert follows.list_organizer_follower_ids(db_path, organizer_b.id) == [anna.id]
    assert follows.list_organizer_follower_ids(db_path, "unknown") == []


def test_list_event_follower_ids_leer(db_path, party):
    assert follows.list_event_follower_ids(db_path, party.id) == []


def test_list_event_follower_ids_mehrere_und_isoliert_pro_event(db_path, anna, max_, party, party_b):
    follows.follow_event(db_path, uuid.uuid4().hex, anna.id, party.id)
    follows.follow_event(db_path, uuid.uuid4().hex, max_.id, party.id)
    follows.follow_event(db_path, uuid.uuid4().hex, max_.id, party_b.id)
    assert set(follows.list_event_follower_ids(db_path, party.id)) == {anna.id, max_.id}
    assert follows.list_event_follower_ids(db_path, party_b.id) == [max_.id]
    assert follows.list_event_follower_ids(db_path, "unknown") == []
