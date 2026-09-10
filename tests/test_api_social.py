"""API-Tests für den Social Graph (Social-Graph-Phase-1: Friends-Fundament) -
``/me/friends``, ``/me/friend-requests``, ``/users/search``,
``/users/{id}/social-profile``, ``/users/{id}/friend-request``,
``/friend-requests/{id}/{accept,decline,cancel}``, ``/friends/{id}``,
``/users/{id}/block``."""

from __future__ import annotations

import uuid

import organizers.storage as organizers_storage
import social.friendships as friendships
from organizers.domain import OrganizerVerificationStatus


def _onboard_username(api_client, headers, username: str) -> None:
    """Legt Profil an + setzt Username - Vorbedingung, um über
    ``/users/search`` gefunden zu werden."""
    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": "1995-01-01"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    resp = api_client.patch("/api/v1/me/profile", json={"username": username}, headers=headers)
    assert resp.status_code == 200, resp.text


def _onboard(api_client, headers) -> None:
    """Legt nur das Profil an (Onboarding-Vorbedingung fuer
    ``PUT /me/social-privacy``), ohne Username."""
    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": "1995-01-01"}, headers=headers
    )
    assert resp.status_code == 200, resp.text


def _set_privacy(api_client, headers, **kwargs) -> dict:
    resp = api_client.put("/api/v1/me/social-privacy", json=kwargs, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


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


# --- Social-Graph-Phase-3: Social Privacy ---------------------------------


def test_get_social_privacy_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/me/social-privacy")
    assert resp.status_code == 401


def test_get_social_privacy_liefert_defaults_ohne_profil(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="privacydefaults@example.com")
    resp = api_client.get("/api/v1/me/social-privacy", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["friend_list_visibility"] == "friends"
    assert body["friend_request_privacy"] == "everyone"
    assert body["discoverable_by_username"] is True
    assert body["discoverable_by_name"] is True
    assert body["following_visibility"] == "nobody"  # Social-Graph-Phase-7: Default privat


def test_put_social_privacy_ohne_auth_gibt_401(api_client):
    resp = api_client.put("/api/v1/me/social-privacy", json={})
    assert resp.status_code == 401


def test_put_social_privacy_ohne_profil_gibt_409(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="privacynoonboarding@example.com")
    resp = api_client.put("/api/v1/me/social-privacy", json={"friend_list_visibility": "nobody"}, headers=headers)
    assert resp.status_code == 409


def test_put_social_privacy_ungueltiger_wert_gibt_422(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="privacyinvalid@example.com")
    _onboard(api_client, headers)
    resp = api_client.put("/api/v1/me/social-privacy", json={"friend_list_visibility": "nonsense"}, headers=headers)
    assert resp.status_code == 422


def test_put_social_privacy_happy_path(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="privacyokuser@example.com")
    _onboard(api_client, headers)
    body = _set_privacy(
        api_client, headers,
        friend_list_visibility="everyone", friend_request_privacy="nobody",
        discoverable_by_username=False, discoverable_by_name=False,
        following_visibility="everyone",
    )
    assert body == {
        "friend_list_visibility": "everyone", "friend_request_privacy": "nobody",
        "discoverable_by_username": False, "discoverable_by_name": False,
        "following_visibility": "everyone",
    }

    # Persistiert - erneutes GET liefert dieselben Werte.
    resp = api_client.get("/api/v1/me/social-privacy", headers=headers)
    assert resp.json() == body


def test_put_social_privacy_partial_update_laesst_uebrige_felder_unveraendert(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="privacypartial@example.com")
    _onboard(api_client, headers)
    _set_privacy(api_client, headers, friend_list_visibility="everyone", friend_request_privacy="nobody")

    body = _set_privacy(api_client, headers, discoverable_by_username=False)
    assert body["friend_list_visibility"] == "everyone"  # unveraendert
    assert body["friend_request_privacy"] == "nobody"  # unveraendert
    assert body["discoverable_by_username"] is False


# --- Social-Graph-Phase-3: GET /users/{id}/friends ------------------------


def test_get_user_friends_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/users/some-id/friends")
    assert resp.status_code == 401


def test_get_user_friends_unbekannter_user_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="userfriends404@example.com")
    resp = api_client.get("/api/v1/users/does-not-exist/friends", headers=headers)
    assert resp.status_code == 404


def test_get_user_friends_geblockt_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="userfriendsblocka@example.com")
    headers_b, b, _ = auth_headers_factory(email="userfriendsblockb@example.com")
    api_client.post(f"/api/v1/users/{b['id']}/block", headers=headers_a)
    resp = api_client.get(f"/api/v1/users/{b['id']}/friends", headers=headers_a)
    assert resp.status_code == 403


def test_get_user_friends_visibility_nobody_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="userfriendsnobodya@example.com")
    headers_b, b, _ = auth_headers_factory(email="userfriendsnobodyb@example.com")
    _onboard(api_client, headers_b)
    _set_privacy(api_client, headers_b, friend_list_visibility="nobody")
    resp = api_client.get(f"/api/v1/users/{b['id']}/friends", headers=headers_a)
    assert resp.status_code == 403


def test_get_user_friends_visibility_friends_ohne_freundschaft_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="userfriendsfriendsa@example.com")
    headers_b, b, _ = auth_headers_factory(email="userfriendsfriendsb@example.com")
    _onboard(api_client, headers_b)
    _set_privacy(api_client, headers_b, friend_list_visibility="friends")
    resp = api_client.get(f"/api/v1/users/{b['id']}/friends", headers=headers_a)
    assert resp.status_code == 403


def test_get_user_friends_visibility_friends_mit_freundschaft_erlaubt(api_client, auth_headers_factory):
    headers_a, a, _ = auth_headers_factory(email="userfriendsokfrienda@example.com")
    headers_b, b, _ = auth_headers_factory(email="userfriendsokfriendb@example.com")
    _onboard(api_client, headers_b)
    _set_privacy(api_client, headers_b, friend_list_visibility="friends")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])
    resp = api_client.get(f"/api/v1/users/{b['id']}/friends", headers=headers_a)
    assert resp.status_code == 200


def test_get_user_friends_visibility_everyone_erlaubt(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="userfriendseveryonea@example.com")
    headers_b, b, _ = auth_headers_factory(email="userfriendseveryoneb@example.com")
    _onboard(api_client, headers_b)
    _set_privacy(api_client, headers_b, friend_list_visibility="everyone")
    resp = api_client.get(f"/api/v1/users/{b['id']}/friends", headers=headers_a)
    assert resp.status_code == 200


def test_get_user_friends_self_immer_erlaubt_trotz_nobody(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="userfriendsselfnobody@example.com")
    _onboard(api_client, headers)
    _set_privacy(api_client, headers, friend_list_visibility="nobody")
    resp = api_client.get(f"/api/v1/users/{user['id']}/friends", headers=headers)
    assert resp.status_code == 200


# --- Social-Graph-Phase-3: mutual_friend_count -----------------------------


def test_search_liefert_mutual_friend_count(api_client, auth_headers_factory):
    headers_me, me, _ = auth_headers_factory(email="mutualsearchme@example.com")
    headers_target, target, _ = auth_headers_factory(email="mutualsearchtarget@example.com")
    headers_shared, shared, _ = auth_headers_factory(email="mutualsearchshared@example.com")
    _onboard_username(api_client, headers_target, "MutualSearchTarget")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, me["id"], shared["id"])
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, target["id"], shared["id"])

    resp = api_client.get("/api/v1/users/search?q=mutualsearchtarget", headers=headers_me)
    assert resp.status_code == 200
    result = next(r for r in resp.json()["results"] if r["user_id"] == target["id"])
    assert result["mutual_friend_count"] == 1


def test_social_profile_liefert_mutual_friend_count(api_client, auth_headers_factory):
    headers_me, me, _ = auth_headers_factory(email="mutualprofileme@example.com")
    headers_target, target, _ = auth_headers_factory(email="mutualprofiletarget@example.com")
    headers_shared, shared, _ = auth_headers_factory(email="mutualprofileshared@example.com")
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, me["id"], shared["id"])
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, target["id"], shared["id"])

    resp = api_client.get(f"/api/v1/users/{target['id']}/social-profile", headers=headers_me)
    assert resp.status_code == 200
    assert resp.json()["mutual_friend_count"] == 1


def test_mutual_friend_count_null_ohne_ueberschneidung(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="mutualzeroM@example.com")
    headers_target, target, _ = auth_headers_factory(email="mutualzeroT@example.com")
    resp = api_client.get(f"/api/v1/users/{target['id']}/social-profile", headers=headers_me)
    assert resp.json()["mutual_friend_count"] == 0


# --- Social-Graph-Phase-3: friend_request_privacy enforcement -------------


def test_send_friend_request_privacy_nobody_gibt_403(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="reqprivacya@example.com")
    headers_b, b, _ = auth_headers_factory(email="reqprivacyb@example.com")
    _onboard(api_client, headers_b)
    _set_privacy(api_client, headers_b, friend_request_privacy="nobody")

    resp = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    assert resp.status_code == 403


def test_send_friend_request_privacy_everyone_default_funktioniert(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="reqprivacydefaulta@example.com")
    headers_b, b, _ = auth_headers_factory(email="reqprivacydefaultb@example.com")
    resp = api_client.post(f"/api/v1/users/{b['id']}/friend-request", headers=headers_a)
    assert resp.status_code == 200


# --- Social-Graph-Phase-6: unified search --------------------------------


def _make_organizer(api_client, owner_user_id: str, *, verified: bool, name: str = "Boiler Room") -> str:
    """Legt direkt über die Storage-Schicht einen Organizer an (dupliziert
    aus tests/test_api_following.py, damit jene Datei unangetastet bleibt)."""
    organizer = organizers_storage.create_organizer(api_client.db_path, uuid.uuid4().hex, owner_user_id, name)
    if verified:
        organizers_storage.set_verification_status(
            api_client.db_path, organizer.id, OrganizerVerificationStatus.VERIFIED
        )
    return organizer.id


def _publish_party(api_client, headers, user_id: str, name: str = "Summer Sound") -> str:
    party_id = api_client.post("/api/v1/parties", json={"name": name}, headers=headers).json()["id"]
    # Publish-Gate braucht Mitgliedschaft in einem verifizierten Organizer;
    # Name bewusst OHNE Bezug zum Party-Namen, damit er die Organizer-Suche
    # in diesen Tests nicht verschmutzt.
    _make_organizer(api_client, user_id, verified=True, name=f"PublisherOrg {uuid.uuid4().hex}")
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return party_id


def test_unified_search_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/search?q=ab")
    assert resp.status_code == 401


def test_unified_search_zu_kurze_query_gibt_422(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="usearch422@example.com")
    resp = api_client.get("/api/v1/search?q=a", headers=headers)
    assert resp.status_code == 422


def test_unified_search_hat_immer_drei_listen(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="usearchshape@example.com")
    body = api_client.get("/api/v1/search?q=zzznomatch", headers=headers).json()
    assert set(body.keys()) == {"users", "organizers", "events"}
    assert body["users"] == [] and body["organizers"] == [] and body["events"] == []


def test_unified_search_findet_user_und_filtert_geblockte(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="usearchme@example.com")
    headers_target, target, _ = auth_headers_factory(email="usearchtarget@example.com")
    _onboard_username(api_client, headers_target, "UnifiedSearchTarget")

    hits = api_client.get("/api/v1/search?q=unifiedsearchtarget", headers=headers_me).json()["users"]
    assert [u["user_id"] for u in hits] == [target["id"]]
    assert hits[0]["entity_type"] == "user"

    assert api_client.post(f"/api/v1/users/{target['id']}/block", headers=headers_me).status_code == 200
    assert api_client.get("/api/v1/search?q=unifiedsearchtarget", headers=headers_me).json()["users"] == []


def test_unified_search_findet_verifizierten_organizer_mit_follow_status(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="usearchorgme@example.com")
    _owner_headers, owner, _ = auth_headers_factory(email="usearchorgowner@example.com")
    org_id = _make_organizer(api_client, owner["id"], verified=True, name="Unified Boiler Room")

    hits = api_client.get("/api/v1/search?q=unified boiler", headers=headers_me).json()["organizers"]
    assert [o["organizer_id"] for o in hits] == [org_id]
    assert hits[0]["entity_type"] == "organizer"
    assert hits[0]["verified"] is True
    assert hits[0]["follower_count"] == 0
    assert hits[0]["is_following"] is False

    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=headers_me).status_code == 200
    hits2 = api_client.get("/api/v1/search?q=unified boiler", headers=headers_me).json()["organizers"]
    assert hits2[0]["is_following"] is True
    assert hits2[0]["follower_count"] == 1


def test_unified_search_ignoriert_unverifizierten_organizer(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="usearchunverme@example.com")
    _owner_headers, owner, _ = auth_headers_factory(email="usearchunverowner@example.com")
    _make_organizer(api_client, owner["id"], verified=False, name="Unified Unverified Club")
    assert api_client.get("/api/v1/search?q=unified unverified", headers=headers_me).json()["organizers"] == []


def test_unified_search_findet_veroeffentlichtes_event_mit_organizer_name(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="usearcheventme@example.com")
    host_headers, host, _ = auth_headers_factory(email="usearcheventhost@example.com", display_name="Event Host Name")
    party_id = _publish_party(api_client, host_headers, host["id"], name="Unified Sound Festival")

    hits = api_client.get("/api/v1/search?q=unified sound", headers=headers_me).json()["events"]
    assert [e["party_id"] for e in hits] == [party_id]
    assert hits[0]["entity_type"] == "event"
    assert hits[0]["organizer_name"] == "Event Host Name"
    assert hits[0]["is_following"] is False

    assert api_client.post(f"/api/v1/events/{party_id}/follow", headers=headers_me).status_code == 200
    hits2 = api_client.get("/api/v1/search?q=unified sound", headers=headers_me).json()["events"]
    assert hits2[0]["is_following"] is True


def test_unified_search_ignoriert_unveroeffentlichte_party(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="usearchprivme@example.com")
    host_headers, _host, _ = auth_headers_factory(email="usearchprivhost@example.com")
    api_client.post("/api/v1/parties", json={"name": "Unified Private Party"}, headers=host_headers)
    assert api_client.get("/api/v1/search?q=unified private", headers=headers_me).json()["events"] == []


def test_unified_search_block_filtert_organizer_owner_und_event_host(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="usearchblockme@example.com")
    owner_headers, owner, _ = auth_headers_factory(email="usearchblockowner@example.com")
    org_id = _make_organizer(api_client, owner["id"], verified=True, name="Blocked Owner Room")
    party_id = _publish_party(api_client, owner_headers, owner["id"], name="Blocked Host Fest")

    assert api_client.get("/api/v1/search?q=blocked owner", headers=headers_me).json()["organizers"]
    assert api_client.get("/api/v1/search?q=blocked host", headers=headers_me).json()["events"]

    assert api_client.post(f"/api/v1/users/{owner['id']}/block", headers=headers_me).status_code == 200
    assert api_client.get("/api/v1/search?q=blocked owner", headers=headers_me).json()["organizers"] == []
    assert api_client.get("/api/v1/search?q=blocked host", headers=headers_me).json()["events"] == []
    _ = org_id, party_id


def test_unified_search_zeigt_eigenen_organizer_und_eigenes_event(api_client, auth_headers_factory):
    headers, me, _ = auth_headers_factory(email="usearchownme@example.com")
    org_id = _make_organizer(api_client, me["id"], verified=True, name="My Own Room")
    party_id = _publish_party(api_client, headers, me["id"], name="My Own Fest")

    body = api_client.get("/api/v1/search?q=my own", headers=headers).json()
    assert [o["organizer_id"] for o in body["organizers"]] == [org_id]
    assert body["organizers"][0]["is_following"] is False
    assert [e["party_id"] for e in body["events"]] == [party_id]
    assert body["events"][0]["is_following"] is False


def test_unified_search_limit_wirkt_pro_kategorie(api_client, auth_headers_factory):
    headers, me, _ = auth_headers_factory(email="usearchlimitme@example.com")
    for i in range(3):
        _make_organizer(api_client, me["id"], verified=True, name=f"LimitOrg {i}")
    hits = api_client.get("/api/v1/search?q=limitorg&limit=1", headers=headers).json()["organizers"]
    assert len(hits) == 1


def test_users_search_ergebnisse_tragen_entity_type_user(api_client, auth_headers_factory):
    headers_me, _me, _ = auth_headers_factory(email="entitytypeme@example.com")
    headers_target, target, _ = auth_headers_factory(email="entitytypetarget@example.com")
    _onboard_username(api_client, headers_target, "EntityTypeTarget")
    hits = api_client.get("/api/v1/users/search?q=entitytypetarget", headers=headers_me).json()["results"]
    assert hits and all(u["entity_type"] == "user" for u in hits)


# --- Social-Graph-Phase-7: Following privacy + relationship views --------


def _befriend(api_client, a_id: str, b_id: str) -> None:
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a_id, b_id)


def test_social_privacy_following_visibility_setzbar(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="fv_set@example.com")
    _onboard(api_client, headers)
    body = _set_privacy(api_client, headers, following_visibility="friends")
    assert body["following_visibility"] == "friends"
    body2 = _set_privacy(api_client, headers, following_visibility="everyone")
    assert body2["following_visibility"] == "everyone"


def test_social_privacy_following_visibility_ungueltig_gibt_422(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="fv_bad@example.com")
    _onboard(api_client, headers)
    resp = api_client.put("/api/v1/me/social-privacy", json={"following_visibility": "nonsense"}, headers=headers)
    assert resp.status_code == 422


def test_user_following_organizers_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/users/some-id/following/organizers")
    assert resp.status_code == 401


def test_user_following_organizers_unbekannter_user_gibt_404(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="fv_404@example.com")
    resp = api_client.get("/api/v1/users/does-not-exist/following/organizers", headers=headers)
    assert resp.status_code == 404


def test_user_following_organizers_self_immer_erlaubt_trotz_nobody(api_client, auth_headers_factory):
    headers, me, _ = auth_headers_factory(email="fv_self@example.com")
    _onboard(api_client, headers)  # following_visibility bleibt Default "nobody"
    org_id = _make_organizer(api_client, me["id"], verified=True, name="Self View Room")
    # Owner darf eigenem Organizer nicht folgen -> separater Follower.
    fh, follower, _ = auth_headers_factory(email="fv_self_f@example.com")
    _ = fh, follower
    resp = api_client.get(f"/api/v1/users/{me['id']}/following/organizers", headers=headers)
    assert resp.status_code == 200
    _ = org_id


def test_user_following_organizers_visibility_tiers(api_client, auth_headers_factory):
    target_headers, target, _ = auth_headers_factory(email="fv_target@example.com")
    stranger_headers, _s, _ = auth_headers_factory(email="fv_stranger@example.com")
    friend_headers, friend, _ = auth_headers_factory(email="fv_friend@example.com")
    _onboard(api_client, target_headers)

    owner_headers, owner, _ = auth_headers_factory(email="fv_orgowner@example.com")
    org_id = _make_organizer(api_client, owner["id"], verified=True, name="Followed By Target Room")
    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=target_headers).status_code == 200
    _befriend(api_client, target["id"], friend["id"])

    # Default "nobody" -> Fremder 403.
    assert api_client.get(f"/api/v1/users/{target['id']}/following/organizers", headers=stranger_headers).status_code == 403

    # "friends" -> Fremder 403, Freund 200.
    _set_privacy(api_client, target_headers, following_visibility="friends")
    assert api_client.get(f"/api/v1/users/{target['id']}/following/organizers", headers=stranger_headers).status_code == 403
    friend_resp = api_client.get(f"/api/v1/users/{target['id']}/following/organizers", headers=friend_headers)
    assert friend_resp.status_code == 200
    assert [o["id"] for o in friend_resp.json()] == [org_id]

    # "everyone" -> Fremder 200.
    _set_privacy(api_client, target_headers, following_visibility="everyone")
    stranger_resp = api_client.get(f"/api/v1/users/{target['id']}/following/organizers", headers=stranger_headers)
    assert stranger_resp.status_code == 200
    assert [o["id"] for o in stranger_resp.json()] == [org_id]


def test_user_following_organizers_geblockter_viewer_gibt_403(api_client, auth_headers_factory):
    target_headers, target, _ = auth_headers_factory(email="fv_blk_target@example.com")
    viewer_headers, viewer, _ = auth_headers_factory(email="fv_blk_viewer@example.com")
    _onboard(api_client, target_headers)
    _set_privacy(api_client, target_headers, following_visibility="everyone")
    assert api_client.post(f"/api/v1/users/{viewer['id']}/block", headers=target_headers).status_code == 200
    resp = api_client.get(f"/api/v1/users/{target['id']}/following/organizers", headers=viewer_headers)
    assert resp.status_code == 403


def test_user_following_events_visibility_und_inhalt(api_client, auth_headers_factory):
    target_headers, target, _ = auth_headers_factory(email="fv_ev_target@example.com")
    stranger_headers, _s, _ = auth_headers_factory(email="fv_ev_stranger@example.com")
    _onboard(api_client, target_headers)

    host_headers, host, _ = auth_headers_factory(email="fv_ev_host@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"], name="Followed Event Fest")
    assert api_client.post(f"/api/v1/events/{party_id}/follow", headers=target_headers).status_code == 200

    assert api_client.get(f"/api/v1/users/{target['id']}/following/events", headers=stranger_headers).status_code == 403
    _set_privacy(api_client, target_headers, following_visibility="everyone")
    resp = api_client.get(f"/api/v1/users/{target['id']}/following/events", headers=stranger_headers)
    assert resp.status_code == 200
    assert [e["party_id"] for e in resp.json()] == [party_id]

    # Unpublish blendet aus (Zeile bleibt).
    assert api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=host_headers).status_code == 204
    assert api_client.get(f"/api/v1/users/{target['id']}/following/events", headers=stranger_headers).json() == []


def test_user_relationship_view(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="rv_me@example.com")
    other_headers, other, _ = auth_headers_factory(email="rv_other@example.com")
    shared_headers, shared, _ = auth_headers_factory(email="rv_shared@example.com")

    assert api_client.get("/api/v1/users/does-not-exist/relationship", headers=me_headers).status_code == 404

    body = api_client.get(f"/api/v1/users/{other['id']}/relationship", headers=me_headers).json()
    assert body == {"target_user_id": other["id"], "relationship_status": "none", "mutual_friend_count": 0}

    api_client.post(f"/api/v1/users/{other['id']}/friend-request", headers=me_headers)
    body2 = api_client.get(f"/api/v1/users/{other['id']}/relationship", headers=me_headers).json()
    assert body2["relationship_status"] == "request_sent"

    req = api_client.get("/api/v1/me/friend-requests", headers=other_headers).json()["incoming"][0]
    api_client.post(f"/api/v1/friend-requests/{req['id']}/accept", headers=other_headers)
    _befriend(api_client, _me_id(api_client, me_headers), shared["id"])
    _befriend(api_client, other["id"], shared["id"])
    body3 = api_client.get(f"/api/v1/users/{other['id']}/relationship", headers=me_headers).json()
    assert body3["relationship_status"] == "friends"
    assert body3["mutual_friend_count"] == 1


def _me_id(api_client, headers) -> str:
    return api_client.get("/api/v1/me", headers=headers).json()["id"]


def test_organizer_relationship_view(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="orv_me@example.com")
    owner_headers, owner, _ = auth_headers_factory(email="orv_owner@example.com")
    org_id = _make_organizer(api_client, owner["id"], verified=True, name="Relationship Room")

    assert api_client.get("/api/v1/organizers/does-not-exist/relationship", headers=me_headers).status_code == 404

    body = api_client.get(f"/api/v1/organizers/{org_id}/relationship", headers=me_headers).json()
    assert body == {"organizer_id": org_id, "is_following": False, "is_blocked": False}

    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=me_headers).status_code == 200
    assert api_client.post(f"/api/v1/users/{owner['id']}/block", headers=me_headers).status_code == 200
    body2 = api_client.get(f"/api/v1/organizers/{org_id}/relationship", headers=me_headers).json()
    assert body2["is_following"] is True
    assert body2["is_blocked"] is True


def test_event_relationship_view(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="erv_me@example.com")
    host_headers, host, _ = auth_headers_factory(email="erv_host@example.com")

    assert api_client.get("/api/v1/events/does-not-exist/relationship", headers=me_headers).status_code == 404

    private_id = api_client.post("/api/v1/parties", json={"name": "Private"}, headers=host_headers).json()["id"]
    assert api_client.get(f"/api/v1/events/{private_id}/relationship", headers=me_headers).status_code == 404

    party_id = _publish_party(api_client, host_headers, host["id"], name="Rel Event")
    body = api_client.get(f"/api/v1/events/{party_id}/relationship", headers=me_headers).json()
    assert body == {"party_id": party_id, "is_following": False, "interest_status": None}

    assert api_client.post(f"/api/v1/events/{party_id}/follow", headers=me_headers).status_code == 200
    assert api_client.post(
        f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=me_headers
    ).status_code == 200
    body2 = api_client.get(f"/api/v1/events/{party_id}/relationship", headers=me_headers).json()
    assert body2["is_following"] is True
    assert body2["interest_status"] == "going"


# --- Robustness: bounded search limit query param ----------------------


def test_search_limit_out_of_range_gibt_422(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="searchlimit@example.com")
    assert api_client.get("/api/v1/users/search?q=ab&limit=0", headers=headers).status_code == 422
    assert api_client.get("/api/v1/users/search?q=ab&limit=101", headers=headers).status_code == 422
    assert api_client.get("/api/v1/search?q=ab&limit=0", headers=headers).status_code == 422
    assert api_client.get("/api/v1/search?q=ab&limit=101", headers=headers).status_code == 422
