"""Pytest-Unit-Tests für ``social.friend_requests`` (Social-Graph-Phase-1).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import social.blocks as blocks
import social.friend_requests as friend_requests
import social.friendships as friendships
from social.domain import FriendRequestStatus


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "friend_requests_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    friendships.init_friendship_storage(path)
    blocks.init_block_storage(path)
    friend_requests.init_friend_request_storage(path)
    return path


@pytest.fixture()
def anna(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")


@pytest.fixture()
def max_(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")


@pytest.fixture()
def ben(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "ben@example.com", "hash", "Ben")


def test_init_ist_idempotent(db_path):
    friend_requests.init_friend_request_storage(db_path)
    friend_requests.init_friend_request_storage(db_path)


def test_create_friend_request_gegen_sich_selbst_wirft_error(db_path, anna):
    with pytest.raises(friend_requests.SelfFriendRequestError):
        friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, anna.id)


def test_create_friend_request_normalfall(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert result.merged is False
    assert result.request.status == FriendRequestStatus.PENDING
    assert result.request.sender_id == anna.id
    assert result.request.receiver_id == max_.id


def test_create_friend_request_duplicate_pending_wirft_error(db_path, anna, max_):
    friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    with pytest.raises(friend_requests.FriendRequestAlreadyExistsError):
        friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)


def test_create_friend_request_gegen_geblockten_user_wirft_error(db_path, anna, max_):
    blocks.block_user(db_path, uuid.uuid4().hex, max_.id, anna.id)
    with pytest.raises(friend_requests.UserBlockedError):
        friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)


def test_create_friend_request_bereits_befreundet_wirft_error(db_path, anna, max_):
    friendships.create_friendship(db_path, uuid.uuid4().hex, anna.id, max_.id)
    with pytest.raises(friend_requests.AlreadyFriendsError):
        friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)


def test_create_friend_request_cross_merge(db_path, anna, max_):
    a_to_b = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    b_to_a = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, max_.id, anna.id)

    assert b_to_a.merged is True
    assert b_to_a.friendship is not None
    assert friendships.are_friends(db_path, anna.id, max_.id) is True

    original = friend_requests.get_friend_request(db_path, a_to_b.request.id)
    assert original.status == FriendRequestStatus.ACCEPTED


def test_accept_friend_request_von_falschem_akteur_wirft_error(db_path, anna, max_, ben):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    with pytest.raises(friend_requests.InvalidFriendRequestActorError):
        friend_requests.accept_friend_request(db_path, result.request.id, ben.id)


def test_accept_friend_request_erzeugt_friendship(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    accept_result = friend_requests.accept_friend_request(db_path, result.request.id, max_.id)
    assert accept_result.request.status == FriendRequestStatus.ACCEPTED
    assert friendships.are_friends(db_path, anna.id, max_.id) is True


def test_accept_bereits_akzeptierter_anfrage_wirft_error(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    friend_requests.accept_friend_request(db_path, result.request.id, max_.id)
    with pytest.raises(friend_requests.InvalidFriendRequestTransitionError):
        friend_requests.accept_friend_request(db_path, result.request.id, max_.id)


def test_decline_friend_request_von_falschem_akteur_wirft_error(db_path, anna, max_, ben):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    with pytest.raises(friend_requests.InvalidFriendRequestActorError):
        friend_requests.decline_friend_request(db_path, result.request.id, ben.id)


def test_decline_friend_request_setzt_status_und_erlaubt_neue_anfrage(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    declined = friend_requests.decline_friend_request(db_path, result.request.id, max_.id)
    assert declined.status == FriendRequestStatus.DECLINED

    re_request = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    assert re_request.request.status == FriendRequestStatus.PENDING


def test_cancel_friend_request_von_falschem_akteur_wirft_error(db_path, anna, max_, ben):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    with pytest.raises(friend_requests.InvalidFriendRequestActorError):
        friend_requests.cancel_friend_request(db_path, result.request.id, ben.id)


def test_cancel_friend_request_setzt_status(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    cancelled = friend_requests.cancel_friend_request(db_path, result.request.id, anna.id)
    assert cancelled.status == FriendRequestStatus.CANCELLED


def test_get_friend_request_unbekannte_id_gibt_none(db_path):
    assert friend_requests.get_friend_request(db_path, "unknown") is None


def test_accept_unbekannte_id_wirft_not_found(db_path, anna):
    with pytest.raises(friend_requests.FriendRequestNotFoundError):
        friend_requests.accept_friend_request(db_path, "unknown", anna.id)


def test_list_incoming_requests_default_nur_pending(db_path, anna, max_, ben):
    friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    declined_result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, ben.id, max_.id)
    friend_requests.decline_friend_request(db_path, declined_result.request.id, max_.id)

    incoming = friend_requests.list_incoming_requests(db_path, max_.id)
    assert len(incoming) == 1
    assert incoming[0].sender_id == anna.id


def test_list_outgoing_requests_default_nur_pending(db_path, anna, max_):
    friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    outgoing = friend_requests.list_outgoing_requests(db_path, anna.id)
    assert len(outgoing) == 1
    assert outgoing[0].receiver_id == max_.id


def test_expire_friend_request_setzt_status(db_path, anna, max_):
    result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
    expired = friend_requests.expire_friend_request(db_path, result.request.id)
    assert expired.status == FriendRequestStatus.EXPIRED
