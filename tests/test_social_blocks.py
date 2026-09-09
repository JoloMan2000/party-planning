"""Pytest-Unit-Tests für ``social.blocks`` (Social-Graph-Phase-1). Ergänzt
den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import social.blocks as blocks
import social.friend_requests as friend_requests
import social.friendships as friendships


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "blocks_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    blocks.init_block_storage(path)
    friendships.init_friendship_storage(path)
    friend_requests.init_friend_request_storage(path)
    return path


@pytest.fixture()
def anna(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")


@pytest.fixture()
def max_(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")


def test_init_ist_idempotent(db_path):
    blocks.init_block_storage(db_path)
    blocks.init_block_storage(db_path)


def test_ohne_block_is_blocked_false(db_path, anna, max_):
    assert blocks.is_blocked(db_path, anna.id, max_.id) is False
    assert blocks.list_blocked_user_ids(db_path, anna.id) == set()


def test_block_user_ist_gerichtet_aber_is_blocked_bidirektional(db_path, anna, max_):
    blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert blocks.is_blocked(db_path, anna.id, max_.id) is True
    assert blocks.is_blocked(db_path, max_.id, anna.id) is True
    # Gerichtet gespeichert: nur anna->max in list_blocked_user_ids(anna).
    assert blocks.list_blocked_user_ids(db_path, anna.id) == {max_.id}
    assert blocks.list_blocked_user_ids(db_path, max_.id) == set()


def test_block_user_ist_idempotent(db_path, anna, max_):
    first = blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    second = blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert first.id == second.id


def test_unblock_user_entfernt_block(db_path, anna, max_):
    blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    blocks.unblock_user(db_path, anna.id, max_.id)
    assert blocks.is_blocked(db_path, anna.id, max_.id) is False


def test_unblock_user_ohne_bestehenden_block_ist_no_op(db_path, anna, max_):
    blocks.unblock_user(db_path, anna.id, max_.id)
    assert blocks.is_blocked(db_path, anna.id, max_.id) is False


def test_block_storniert_pending_friend_request(db_path, anna, max_):
    friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert friend_requests.get_pending_request(db_path, anna.id, max_.id) is None


def test_block_storniert_pending_friend_request_in_umgekehrter_richtung(db_path, anna, max_):
    friend_requests.create_friend_request(db_path, uuid.uuid4().hex, max_.id, anna.id)
    blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert friend_requests.get_pending_request(db_path, max_.id, anna.id) is None


def test_block_beendet_bestehende_friendship(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    friend_requests.accept_friend_request(db_path, result.request.id, max_.id)
    assert friendships.are_friends(db_path, anna.id, max_.id) is True

    blocks.block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert friendships.are_friends(db_path, anna.id, max_.id) is False
