"""API-Tests für Activities + Guest-Voting (Equipment Engine Phase 4) -
mirrort ``tests/test_api_admin_equipment.py``'s Fixture-Nutzung
(``host_party_factory``, ``co_host_headers_factory``, ``_make_guest_headers``)."""

from __future__ import annotations


def _make_guest_headers(api_client, auth_headers_factory, party_id: str) -> dict:
    import accounts.party_storage as party_storage
    from accounts.domain import PartyRole, RsvpStatus

    headers, user, _refresh_token = auth_headers_factory()
    party_storage.upsert_membership(api_client.db_path, party_id, user["id"], PartyRole.GUEST, RsvpStatus.ACCEPTED)
    return headers


def _create_activity(api_client, party_id, headers, name="Beer Pong", station_id="beer_pong"):
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/activities",
        json={"name": name, "station_id": station_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_host_creates_activity(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    activity = _create_activity(api_client, party_id, headers)
    assert activity["name"] == "Beer Pong"
    assert activity["station_id"] == "beer_pong"
    assert activity["vote_count"] == 0
    assert activity["voted_by_me"] is False


def test_co_host_can_also_create(api_client, host_party_factory, co_host_headers_factory):
    party_id, _headers, _user = host_party_factory()
    co_host_headers = co_host_headers_factory(party_id)
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/activities", json={"name": "Karaoke"}, headers=co_host_headers
    )
    assert resp.status_code == 201


def test_guest_cannot_create(api_client, host_party_factory, auth_headers_factory):
    party_id, _headers, _user = host_party_factory()
    guest_headers = _make_guest_headers(api_client, auth_headers_factory, party_id)
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/activities", json={"name": "Karaoke"}, headers=guest_headers
    )
    assert resp.status_code == 403


def test_non_member_gets_403_on_list(api_client, host_party_factory, auth_headers_factory):
    party_id, headers, _user = host_party_factory()
    _create_activity(api_client, party_id, headers)
    outsider_headers, _user2, _ = auth_headers_factory(email="outsider@example.com")
    resp = api_client.get(f"/api/v1/parties/{party_id}/activities", headers=outsider_headers)
    assert resp.status_code == 403


def test_guest_can_list_and_vote_idempotently_then_retract(api_client, host_party_factory, auth_headers_factory):
    party_id, headers, _user = host_party_factory()
    activity = _create_activity(api_client, party_id, headers)
    guest_headers = _make_guest_headers(api_client, auth_headers_factory, party_id)

    list_resp = api_client.get(f"/api/v1/parties/{party_id}/activities", headers=guest_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["vote_count"] == 0
    assert listed[0]["voted_by_me"] is False

    vote_resp = api_client.post(
        f"/api/v1/parties/{party_id}/activities/{activity['id']}/vote", headers=guest_headers
    )
    assert vote_resp.status_code == 200
    assert vote_resp.json()["vote_count"] == 1
    assert vote_resp.json()["voted_by_me"] is True

    # Idempotent - voting again does not double-count.
    vote_again_resp = api_client.post(
        f"/api/v1/parties/{party_id}/activities/{activity['id']}/vote", headers=guest_headers
    )
    assert vote_again_resp.json()["vote_count"] == 1

    list_after_vote = api_client.get(f"/api/v1/parties/{party_id}/activities", headers=guest_headers).json()
    assert list_after_vote[0]["vote_count"] == 1
    assert list_after_vote[0]["voted_by_me"] is True

    retract_resp = api_client.delete(
        f"/api/v1/parties/{party_id}/activities/{activity['id']}/vote", headers=guest_headers
    )
    assert retract_resp.status_code == 204

    list_after_retract = api_client.get(f"/api/v1/parties/{party_id}/activities", headers=guest_headers).json()
    assert list_after_retract[0]["vote_count"] == 0
    assert list_after_retract[0]["voted_by_me"] is False

    # Retracting again is a no-op, not an error.
    retract_again_resp = api_client.delete(
        f"/api/v1/parties/{party_id}/activities/{activity['id']}/vote", headers=guest_headers
    )
    assert retract_again_resp.status_code == 204


def test_host_only_delete_and_guest_forbidden(api_client, host_party_factory, auth_headers_factory):
    party_id, headers, _user = host_party_factory()
    activity = _create_activity(api_client, party_id, headers)
    guest_headers = _make_guest_headers(api_client, auth_headers_factory, party_id)

    forbidden_resp = api_client.delete(
        f"/api/v1/parties/{party_id}/admin/activities/{activity['id']}", headers=guest_headers
    )
    assert forbidden_resp.status_code == 403

    ok_resp = api_client.delete(f"/api/v1/parties/{party_id}/admin/activities/{activity['id']}", headers=headers)
    assert ok_resp.status_code == 204

    list_resp = api_client.get(f"/api/v1/parties/{party_id}/activities", headers=headers)
    assert list_resp.json() == []


def test_cross_party_activity_id_returns_404_on_vote_and_delete(api_client, host_party_factory, auth_headers_factory):
    party_a, headers_a, _ = host_party_factory()
    party_b, headers_b, _ = host_party_factory()
    activity = _create_activity(api_client, party_a, headers_a)

    vote_resp = api_client.post(f"/api/v1/parties/{party_b}/activities/{activity['id']}/vote", headers=headers_b)
    assert vote_resp.status_code == 404

    delete_resp = api_client.delete(f"/api/v1/parties/{party_b}/admin/activities/{activity['id']}", headers=headers_b)
    assert delete_resp.status_code == 404
