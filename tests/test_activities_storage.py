"""Storage-Tests für ``activities``/``activity_votes`` (Equipment Engine
Phase 4) - mirrort ``tests/test_equipment_provisions_storage.py``'s Stil
(FK-Enforcement ist app-weit AUS, daher genügt ein beliebiger ``uuid``-String
als ``party_id``/``user_id``, keine echten ``parties``/``users``-Zeilen
nötig)."""

from __future__ import annotations

import uuid

import pytest

import activities.storage as activities_storage


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "activities_test.db"
    activities_storage.init_activities_storage(path)
    return path


def test_create_list_get_roundtrip(db_path):
    party_id = uuid.uuid4().hex
    host_id = uuid.uuid4().hex

    created = activities_storage.create_activity(
        db_path, uuid.uuid4().hex, party_id, host_id, "Beer Pong", station_id="beer_pong"
    )
    assert created.party_id == party_id
    assert created.station_id == "beer_pong"

    fetched = activities_storage.get_activity(db_path, created.id)
    assert fetched == created

    listed = activities_storage.list_activities_for_party(db_path, party_id)
    assert [a.id for a in listed] == [created.id]

    assert activities_storage.get_activity(db_path, "unknown") is None
    assert activities_storage.list_activities_for_party(db_path, "unknown-party") == []


def test_delete_activity_cascades_votes_and_is_idempotent(db_path):
    party_id = uuid.uuid4().hex
    host_id = uuid.uuid4().hex
    activity = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_id, host_id, "Karaoke")

    activities_storage.cast_vote(db_path, uuid.uuid4().hex, activity.id, uuid.uuid4().hex)
    activities_storage.cast_vote(db_path, uuid.uuid4().hex, activity.id, uuid.uuid4().hex)
    assert activities_storage.count_votes_for_activity(db_path, activity.id) == 2

    activities_storage.delete_activity(db_path, activity.id)
    assert activities_storage.get_activity(db_path, activity.id) is None
    assert activities_storage.count_votes_for_activity(db_path, activity.id) == 0

    activities_storage.delete_activity(db_path, activity.id)  # No-Op, kein Fehler.
    activities_storage.delete_activity(db_path, "unknown")  # No-Op auch für unbekannte ID.


def test_cast_vote_is_idempotent(db_path):
    party_id = uuid.uuid4().hex
    user_id = uuid.uuid4().hex
    activity = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_id, uuid.uuid4().hex, "Cornhole")

    first = activities_storage.cast_vote(db_path, uuid.uuid4().hex, activity.id, user_id)
    second = activities_storage.cast_vote(db_path, uuid.uuid4().hex, activity.id, user_id)
    assert first.id == second.id
    assert activities_storage.count_votes_for_activity(db_path, activity.id) == 1
    assert activities_storage.has_voted(db_path, activity.id, user_id) is True


def test_retract_vote_is_idempotent_and_safe_when_never_voted(db_path):
    activity = activities_storage.create_activity(db_path, uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex, "Uno")
    user_id = uuid.uuid4().hex

    activities_storage.retract_vote(db_path, activity.id, user_id)  # No-Op, war nie ein Vote.
    assert activities_storage.has_voted(db_path, activity.id, user_id) is False

    activities_storage.cast_vote(db_path, uuid.uuid4().hex, activity.id, user_id)
    activities_storage.retract_vote(db_path, activity.id, user_id)
    assert activities_storage.has_voted(db_path, activity.id, user_id) is False
    activities_storage.retract_vote(db_path, activity.id, user_id)  # No-Op erneut.


def test_count_votes_by_activity_for_party_aggregates_and_isolates_parties(db_path):
    party_a = uuid.uuid4().hex
    party_b = uuid.uuid4().hex
    host_id = uuid.uuid4().hex

    a1 = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_a, host_id, "Beer Pong")
    a2 = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_a, host_id, "Karaoke")
    b1 = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_b, host_id, "Beer Pong")

    activities_storage.cast_vote(db_path, uuid.uuid4().hex, a1.id, uuid.uuid4().hex)
    activities_storage.cast_vote(db_path, uuid.uuid4().hex, a1.id, uuid.uuid4().hex)
    activities_storage.cast_vote(db_path, uuid.uuid4().hex, a2.id, uuid.uuid4().hex)
    activities_storage.cast_vote(db_path, uuid.uuid4().hex, b1.id, uuid.uuid4().hex)

    counts_a = activities_storage.count_votes_by_activity_for_party(db_path, party_a)
    assert counts_a == {a1.id: 2, a2.id: 1}
    assert b1.id not in counts_a  # keine Leakage aus einer anderen Party.


def test_list_voted_activity_ids_for_user_is_scoped_to_party(db_path):
    party_id = uuid.uuid4().hex
    user_id = uuid.uuid4().hex
    host_id = uuid.uuid4().hex

    a1 = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_id, host_id, "Beer Pong")
    a2 = activities_storage.create_activity(db_path, uuid.uuid4().hex, party_id, host_id, "Karaoke")
    other_party_activity = activities_storage.create_activity(
        db_path, uuid.uuid4().hex, uuid.uuid4().hex, host_id, "Beer Pong"
    )

    activities_storage.cast_vote(db_path, uuid.uuid4().hex, a1.id, user_id)
    activities_storage.cast_vote(db_path, uuid.uuid4().hex, other_party_activity.id, user_id)

    voted = activities_storage.list_voted_activity_ids_for_user(db_path, party_id, user_id)
    assert voted == {a1.id}
    assert a2.id not in voted
    assert other_party_activity.id not in voted
