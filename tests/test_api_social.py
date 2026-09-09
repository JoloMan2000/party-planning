"""API-Tests für den Social Graph (Social-Graph-Phase-1: Friends-Fundament) -
``/me/friends``, ``/me/friend-requests``, ``/users/search``,
``/users/{id}/social-profile``, ``/users/{id}/friend-request``,
``/friend-requests/{id}/{accept,decline,cancel}``, ``/friends/{id}``,
``/users/{id}/block``."""

from __future__ import annotations

import uuid

import social.friendships as friendships


def _onboard_username(api_client, headers, username: str) -> None:
    """Legt Profil an + setzt Username - Vorbedingung, um über
    ``/users/search`` gefunden zu werden."""
    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": "1995-01-01"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    resp = api_client.patch("/api/v1/me/profile", json={"username": username}, headers=headers)
    assert resp.status_code == 200, resp.text


def test_send_friend_request_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/users/some-id/friend-request")
    assert resp.status_code == 401


def test_send_friend_request_gegen_sich_selbst_gibt_422(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="selfreq@example.com")
    resp = api_client.post(f"/api/v1/users/{user['id']}/friend-request", headers=headers)
    assert resp.status_code == 422


def test_send_friend_request_unbekannter_user_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="requnknown@example.com")
    resp = api_client.post("/api/v1/users/does-not-exist/friend-request", headers=headers)
    assert resp.status_code == 404


def test_send_friend_request_happy_path(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="reqa@example.com")
    headers_b, b, _ = auth_headers_factory(email="reqb@example.com")

    resp = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merged"] is False
    assert body["request"]["status"] == "pending"
    assert body["request"]["direction"] == "outgoing"
    assert body["request"]["other_user_id"] == b["id"]


def test_send_friend_request_duplicate_gibt_409(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="dupa@example.com")
    headers_b, b, _ = auth_headers_factory(email="dupb@example.com")

    api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    resp = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    assert resp.status_code == 409


def test_send_friend_request_bereits_befreundet_gibt_409(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="alreadyfrienda@example.com")
    headers_b, b, _ = auth_headers_factory(email="alreadyfriendb@example.com")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])

    resp = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    assert resp.status_code == 409


def test_send_friend_request_geblockt_gibt_403(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="blockeda@example.com")
    headers_b, b, _ = auth_headers_factory(email="blockedb@example.com")
    api_client.post(f"/api/v1/users/{a['id']}/block", headers=headers_b)

    resp = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    assert resp.status_code == 403


def test_send_friend_request_cross_merge(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="mergea@example.com")
    headers_b, b, _ = auth_headers_factory(email="mergeb@example.com")

    api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    resp = api_client.post(f"/api/v1/users/{a['id']}/friend-request", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["merged"] is True

    friends_resp = api_client.get("/api/v1/me/friends", headers=headers_a)
    assert any(f["user_id"] == b["id"] for f in friends_resp.json())


def test_accept_friend_request_von_falschem_akteur_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="acceptwronga@example.com")
    headers_b, b, _ = auth_headers_factory(email="acceptwrongb@example.com")
    headers_c, _c, _ = auth_headers_factory(email="acceptwrongc@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/accept", headers=headers_c)
    assert resp.status_code == 403


def test_accept_friend_request_unbekannte_id_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="acceptunknown@example.com")
    resp = api_client.post("/api/v1/friend-requests/does-not-exist/accept", headers=headers)
    assert resp.status_code == 404


def test_accept_friend_request_happy_path(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="accepta@example.com")
    headers_b, b, _ = auth_headers_factory(email="acceptb@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/accept", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


def test_accept_friend_request_bereits_beantwortet_gibt_422(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="acceptagaina@example.com")
    headers_b, b, _ = auth_headers_factory(email="acceptagainb@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]
    api_client.post(f"/api/v1/friend-requests/{req['id']}/accept", headers=headers_b)

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/accept", headers=headers_b)
    assert resp.status_code == 422


def test_decline_friend_request_happy_path(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="declinea@example.com")
    headers_b, b, _ = auth_headers_factory(email="declineb@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/decline", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


def test_decline_friend_request_von_falschem_akteur_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="declinewronga@example.com")
    headers_b, b, _ = auth_headers_factory(email="declinewrongb@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/decline", headers=headers_a)
    assert resp.status_code == 403


def test_cancel_friend_request_happy_path(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="cancela@example.com")
    headers_b, b, _ = auth_headers_factory(email="cancelb@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/cancel", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_friend_request_von_falschem_akteur_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="cancelwronga@example.com")
    headers_b, b, _ = auth_headers_factory(email="cancelwrongb@example.com")
    req = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a).json()["request"]

    resp = api_client.post(f"/api/v1/friend-requests/{req['id']}/cancel", headers=headers_b)
    assert resp.status_code == 403


def test_get_my_friend_requests_trennt_incoming_und_outgoing(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="inboxa@example.com")
    headers_b, b, _ = auth_headers_factory(email="inboxb@example.com")
    api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)

    inbox_a = api_client.get("/api/v1/me/friend-requests", headers=headers_a).json()
    assert len(inbox_a["outgoing"]) == 1
    assert len(inbox_a["incoming"]) == 0

    inbox_b = api_client.get("/api/v1/me/friend-requests", headers=headers_b).json()
    assert len(inbox_b["incoming"]) == 1
    assert len(inbox_b["outgoing"]) == 0


def test_get_my_friends_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/me/friends")
    assert resp.status_code == 401


def test_get_my_friends_listet_bestehende_freundschaften(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="listfrienda@example.com")
    headers_b, b, _ = auth_headers_factory(email="listfriendb@example.com")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])

    resp = api_client.get("/api/v1/me/friends", headers=headers_a)
    assert resp.status_code == 200
    ids = [f["user_id"] for f in resp.json()]
    assert ids == [b["id"]]


def test_remove_friend_entfernt_freundschaft(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="removefrienda@example.com")
    headers_b, b, _ = auth_headers_factory(email="removefriendb@example.com")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])

    resp = api_client.delete(f"/api/v1/friends/{b['id']}", headers=headers_a)
    assert resp.status_code == 204
    assert api_client.get("/api/v1/me/friends", headers=headers_a).json() == []


def test_remove_friend_ohne_bestehende_freundschaft_ist_idempotent(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="removenoop@example.com")
    resp = api_client.delete("/api/v1/friends/some-id", headers=headers)
    assert resp.status_code == 204


def test_users_search_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/users/search?q=ab")
    assert resp.status_code == 401


def test_users_search_zu_kurze_query_gibt_422(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="searchshort@example.com")
    resp = api_client.get("/api/v1/users/search?q=a", headers=headers)
    assert resp.status_code == 422


def test_users_search_findet_per_username(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="searcha@example.com")
    headers_b, b, _ = auth_headers_factory(email="searchb@example.com")
    _onboard_username(api_client, headers_b, "SearchTarget")

    resp = api_client.get("/api/v1/users/search?q=searchtarget", headers=headers_a)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["user_id"] == b["id"]
    assert results[0]["relationship_status"] == "none"


def test_users_search_findet_sich_selbst_nicht(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="searchself@example.com")
    _onboard_username(api_client, headers, "SelfSearcher")

    resp = api_client.get("/api/v1/users/search?q=selfsearcher", headers=headers)
    assert resp.json()["results"] == []


def test_users_search_filtert_geblockte_user(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="searchblocka@example.com")
    headers_b, b, _ = auth_headers_factory(email="searchblockb@example.com")
    _onboard_username(api_client, headers_b, "BlockedSearchee")
    api_client.post(f"/api/v1/users/{b['id']}/block", headers=headers_a)

    resp = api_client.get("/api/v1/users/search?q=blockedsearchee", headers=headers_a)
    assert resp.json()["results"] == []


def test_get_social_profile_unbekannter_user_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="socialprofile404@example.com")
    resp = api_client.get("/api/v1/users/does-not-exist/social-profile", headers=headers)
    assert resp.status_code == 404


def test_get_social_profile_relationship_status_none(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="profilestatusa@example.com")
    headers_b, b, _ = auth_headers_factory(email="profilestatusb@example.com")

    resp = api_client.get(f"/api/v1/users/{b['id']}/social-profile", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["relationship_status"] == "none"


def test_get_social_profile_relationship_status_friends(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="profilefrienda@example.com")
    headers_b, b, _ = auth_headers_factory(email="profilefriendb@example.com")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])

    resp = api_client.get(f"/api/v1/users/{b['id']}/social-profile", headers=headers_a)
    assert resp.json()["relationship_status"] == "friends"


def test_get_social_profile_relationship_status_request_sent_und_received(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="profilereqa@example.com")
    headers_b, b, _ = auth_headers_factory(email="profilereqb@example.com")
    api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)

    resp_a = api_client.get(f"/api/v1/users/{b['id']}/social-profile", headers=headers_a)
    assert resp_a.json()["relationship_status"] == "request_sent"
    resp_b = api_client.get(f"/api/v1/users/{a['id']}/social-profile", headers=headers_b)
    assert resp_b.json()["relationship_status"] == "request_received"


def test_get_social_profile_relationship_status_self(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="profileself@example.com")
    resp = api_client.get(f"/api/v1/users/{user['id']}/social-profile", headers=headers)
    assert resp.json()["relationship_status"] == "self"


def test_block_user_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/users/some-id/block")
    assert resp.status_code == 401


def test_block_user_self_block_gibt_422(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="selfblocksocial@example.com")
    resp = api_client.post(f"/api/v1/users/{user['id']}/block", headers=headers)
    assert resp.status_code == 422


def test_block_user_unbekannter_user_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="blockunknownsocial@example.com")
    resp = api_client.post("/api/v1/users/does-not-exist/block", headers=headers)
    assert resp.status_code == 404


def test_block_user_ist_idempotent(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="blockidema@example.com")
    headers_b, b, _ = auth_headers_factory(email="blockidemb@example.com")

    first = api_client.post(f"/api/v1/users/{b['id']}/block", headers=headers_a)
    second = api_client.post(f"/api/v1/users/{b['id']}/block", headers=headers_a)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"user_id": b["id"], "blocked": True}


def test_block_user_beendet_bestehende_friendship_und_storniert_requests(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="blockendsa@example.com")
    headers_b, b, _ = auth_headers_factory(email="blockendsb@example.com")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])

    api_client.post(f"/api/v1/users/{b['id']}/block", headers=headers_a)
    assert api_client.get("/api/v1/me/friends", headers=headers_a).json() == []

    resp = api_client.get(f"/api/v1/users/{b['id']}/social-profile", headers=headers_a)
    assert resp.json()["relationship_status"] == "blocked"


def test_unblock_user_ohne_auth_gibt_401(api_client):
    resp = api_client.delete("/api/v1/users/some-id/block")
    assert resp.status_code == 401


def test_unblock_user_entfernt_block(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="unblocksociala@example.com")
    headers_b, b, _ = auth_headers_factory(email="unblocksocialb@example.com")
    api_client.post(f"/api/v1/users/{b['id']}/block", headers=headers_a)

    resp = api_client.delete(f"/api/v1/users/{b['id']}/block", headers=headers_a)
    assert resp.status_code == 204

    profile_resp = api_client.get(f"/api/v1/users/{b['id']}/social-profile", headers=headers_a)
    assert profile_resp.json()["relationship_status"] == "none"


def test_unblock_user_ohne_bestehenden_block_ist_no_op(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="unblocknoopsocial@example.com")
    resp = api_client.delete("/api/v1/users/some-id/block", headers=headers)
    assert resp.status_code == 204
