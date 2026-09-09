"""Pytest-Unit-Tests für ``social.friendships`` (Social-Graph-Phase-1).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import social.friendships as friendships


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "friendships_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    friendships.init_friendship_storage(path)
    return path


@pytest.fixture()
def anna(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")


@pytest.fixture()
def max_(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")


def test_init_ist_idempotent(db_path):
    friendships.init_friendship_storage(db_path)
    friendships.init_friendship_storage(db_path)


def test_ohne_friendship_are_friends_false(db_path, anna, max_):
    assert friendships.are_friends(db_path, anna.id, max_.id) is False
    assert friendships.list_friends_for_user(db_path, anna.id) == []


def test_create_friendship_ist_symmetrisch(db_path, anna, max_):
    friendships.create_friendship(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert friendships.are_friends(db_path, anna.id, max_.id) is True
    assert friendships.are_friends(db_path, max_.id, anna.id) is True


def test_create_friendship_kanonische_ordnung(db_path, anna, max_):
    friendship = friendships.create_friendship(db_path, uuid.uuid4().hex, max_.id, anna.id)
    assert friendship.user_a_id < friendship.user_b_id


def test_create_friendship_ist_idempotent_unabhaengig_von_argument_reihenfolge(db_path, anna, max_):
    first = friendships.create_friendship(db_path, uuid.uuid4().hex, anna.id, max_.id)
    second = friendships.create_friendship(db_path, uuid.uuid4().hex, max_.id, anna.id)
    assert first.id == second.id


def test_list_friends_for_user_isoliert_pro_user(db_path, anna, max_):
    other = user_storage.create_user(db_path, uuid.uuid4().hex, "other@example.com", "hash", "Other")
    friendships.create_friendship(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert len(friendships.list_friends_for_user(db_path, anna.id)) == 1
    assert len(friendships.list_friends_for_user(db_path, max_.id)) == 1
    assert friendships.list_friends_for_user(db_path, other.id) == []


def test_remove_friendship_entfernt_und_ist_symmetrisch(db_path, anna, max_):
    friendships.create_friendship(db_path, uuid.uuid4().hex, anna.id, max_.id)
    friendships.remove_friendship(db_path, max_.id, anna.id)
    assert friendships.are_friends(db_path, anna.id, max_.id) is False


def test_remove_friendship_ohne_bestehende_ist_no_op(db_path, anna, max_):
    friendships.remove_friendship(db_path, anna.id, max_.id)
    assert friendships.are_friends(db_path, anna.id, max_.id) is False
