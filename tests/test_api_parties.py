"""API-Tests für Party-CRUD, Gästeliste + Einladungen (Account-basierter
Pivot, Phase 1) sowie Invite-Friends/Co-Host-Promotion (Social-Graph-Phase-2)."""

from __future__ import annotations

import uuid

import social.friendships as friendships


def test_create_party_macht_ersteller_zum_host(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory()
    resp = api_client.post("/api/v1/parties", json={"name": "Summer BBQ", "location": "Garden"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Summer BBQ"
    assert body["host_user_id"] == user["id"]


def test_create_party_mit_leerem_namen_gibt_422(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    resp = api_client.post("/api/v1/parties", json={"name": ""}, headers=headers)
    assert resp.status_code == 422


def test_create_party_mit_zu_langem_namen_gibt_422(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    resp = api_client.post("/api/v1/parties", json={"name": "x" * 201}, headers=headers)
    assert resp.status_code == 422


def test_create_party_mit_zu_langer_beschreibung_gibt_422(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    resp = api_client.post(
        "/api/v1/parties", json={"name": "P", "description": "x" * 5001}, headers=headers
    )
    assert resp.status_code == 422


def test_create_party_mit_zu_langem_ort_gibt_422(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    resp = api_client.post("/api/v1/parties", json={"name": "P", "location": "x" * 301}, headers=headers)
    assert resp.status_code == 422


def test_patch_party_mit_leerem_namen_gibt_422(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.patch(f"/api/v1/parties/{party_id}", json={"name": ""}, headers=headers)
    assert resp.status_code == 422


def test_patch_party_mit_zu_langem_namen_gibt_422(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.patch(f"/api/v1/parties/{party_id}", json={"name": "x" * 201}, headers=headers)
    assert resp.status_code == 422


def test_get_party_als_host_erlaubt(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory()
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.get(f"/api/v1/parties/{party_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == party_id


def test_get_party_als_unbeteiligter_gibt_403(api_client, auth_headers_factory):
    host_headers, _, _ = auth_headers_factory(email="partyhost@example.com")
    stranger_headers, _, _ = auth_headers_factory(email="strangerx@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    resp = api_client.get(f"/api/v1/parties/{party_id}", headers=stranger_headers)
    assert resp.status_code == 403


def test_get_unbekannte_party_gibt_404(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    resp = api_client.get("/api/v1/parties/unknown-id", headers=headers)
    assert resp.status_code == 404


def test_patch_party_als_host_erlaubt_partial_update(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    party_id = api_client.post(
        "/api/v1/parties", json={"name": "Old Name", "location": "Old Place"}, headers=headers
    ).json()["id"]
    resp = api_client.patch(f"/api/v1/parties/{party_id}", json={"name": "New Name"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"
    assert body["location"] == "Old Place"


def test_patch_party_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, _, _ = auth_headers_factory(email="patchhost@example.com")
    guest_headers, _, _ = auth_headers_factory(email="patchguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "patchguest@example.com"},
        headers=host_headers,
    )
    resp = api_client.patch(f"/api/v1/parties/{party_id}", json={"name": "Hacked"}, headers=guest_headers)
    assert resp.status_code == 403


def test_invite_unbekannte_email_gibt_404(api_client, auth_headers_factory):
    headers, _, _ = auth_headers_factory()
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": "nobody@example.com"}, headers=headers
    )
    assert resp.status_code == 404


def test_invite_zweimal_gibt_409(api_client, auth_headers_factory):
    host_headers, _, _ = auth_headers_factory(email="doublehost@example.com")
    auth_headers_factory(email="doubleguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    resp1 = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "doubleguest@example.com"},
        headers=host_headers,
    )
    assert resp1.status_code == 201
    resp2 = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "doubleguest@example.com"},
        headers=host_headers,
    )
    assert resp2.status_code == 409


def test_invite_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, _, _ = auth_headers_factory(email="invhost@example.com")
    guest_headers, _, _ = auth_headers_factory(email="invguest@example.com")
    auth_headers_factory(email="invtarget@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": "invguest@example.com"}, headers=host_headers
    )
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "invtarget@example.com"},
        headers=guest_headers,
    )
    assert resp.status_code == 403


def test_get_guests_zeigt_liste_und_counts(api_client, auth_headers_factory):
    host_headers, _, _ = auth_headers_factory(email="guestlisthost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="guestlistguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    inv_id = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "guestlistguest@example.com"},
        headers=host_headers,
    ).json()["id"]

    resp = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["pending"] == 1
    assert any(g["user_id"] == guest["id"] for g in body["guests"])

    api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers)

    resp = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers)
    body = resp.json()
    assert body["counts"]["accepted"] == 1
    assert body["counts"]["pending"] == 0


def test_get_guests_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, _, _ = auth_headers_factory(email="guestlistforbid-host@example.com")
    guest_headers, _, _ = auth_headers_factory(email="guestlistforbid-guest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "guestlistforbid-guest@example.com"},
        headers=host_headers,
    )
    resp = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=guest_headers)
    assert resp.status_code == 403


# --- Social-Graph-Phase-2: Invite Friends ---------------------------------


def _befriend(api_client, user_a: dict, user_b: dict) -> None:
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, user_a["id"], user_b["id"])


def test_invite_friends_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/parties/some-id/invitations/friends", json={"friend_user_ids": ["x"]})
    assert resp.status_code == 401


def test_invite_friends_unbekannte_party_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="inviteffriends404@example.com")
    resp = api_client.post(
        "/api/v1/parties/does-not-exist/invitations/friends", json={"friend_user_ids": ["x"]}, headers=headers
    )
    assert resp.status_code == 404


def test_invite_friends_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="invitefriendshost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="invitefriendsguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    inv_id = api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": guest["email"]}, headers=host_headers
    ).json()["id"]
    api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers)

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations/friends", json={"friend_user_ids": [host["id"]]}, headers=guest_headers
    )
    assert resp.status_code == 403


def test_invite_friends_leere_liste_gibt_422(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="invitefriendsempty@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations/friends", json={"friend_user_ids": []}, headers=headers
    )
    assert resp.status_code == 422


def test_invite_friends_happy_path(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="invitefriendsokhost@example.com")
    friend_headers, friend, _ = auth_headers_factory(email="invitefriendsokfriend@example.com")
    _befriend(api_client, host, friend)
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations/friends", json={"friend_user_ids": [friend["id"]]}, headers=host_headers
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["status"] == "invited"
    assert results[0]["invitation_id"]

    guests = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers).json()["guests"]
    assert any(g["user_id"] == friend["id"] for g in guests)


def test_invite_friends_co_host_darf_auch_einladen(api_client, auth_headers_factory, host_party_factory, co_host_headers_factory):
    party_id, host_headers, host = host_party_factory()
    co_host_headers = co_host_headers_factory(party_id)
    co_host_user = api_client.get("/api/v1/me", headers=co_host_headers).json()
    friend_headers, friend, _ = auth_headers_factory(email="invitefriendscohostfriend@example.com")
    _befriend(api_client, co_host_user, friend)

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations/friends", json={"friend_user_ids": [friend["id"]]}, headers=co_host_headers
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "invited"


def test_invite_friends_gemischter_batch(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="invitefriendsmixhost@example.com")
    friend_headers, friend, _ = auth_headers_factory(email="invitefriendsmixfriend@example.com")
    stranger_headers, stranger, _ = auth_headers_factory(email="invitefriendsmixstranger@example.com")
    _befriend(api_client, host, friend)
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]

    # Freund vorab schon eingeladen -> already_member beim zweiten Aufruf.
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations/friends", json={"friend_user_ids": [friend["id"]]}, headers=host_headers
    )

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations/friends",
        json={"friend_user_ids": [friend["id"], stranger["id"]]},
        headers=host_headers,
    )
    assert resp.status_code == 200
    by_id = {r["user_id"]: r["status"] for r in resp.json()["results"]}
    assert by_id[friend["id"]] == "already_member"
    assert by_id[stranger["id"]] == "not_a_friend"


# --- Social-Graph-Phase-2: Co-Host Promotion ------------------------------


def test_promote_co_host_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/parties/some-id/co-hosts", json={"user_id": "x"})
    assert resp.status_code == 401


def test_promote_co_host_unbekannte_party_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="promotecohost404@example.com")
    resp = api_client.post("/api/v1/parties/does-not-exist/co-hosts", json={"user_id": "x"}, headers=headers)
    assert resp.status_code == 404


def test_promote_co_host_als_co_host_gibt_403(api_client, host_party_factory, co_host_headers_factory):
    party_id, host_headers, host = host_party_factory()
    co_host_headers = co_host_headers_factory(party_id)
    resp = api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": host["id"]}, headers=co_host_headers)
    assert resp.status_code == 403


def test_promote_co_host_unbekanntes_ziel_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="promotecohostunknown@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": "does-not-exist"}, headers=headers)
    assert resp.status_code == 404


def test_promote_co_host_self_target_gibt_400(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="promotecohostself@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=headers).json()["id"]
    resp = api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": user["id"]}, headers=headers)
    assert resp.status_code == 400


def test_promote_co_host_pending_gast_gibt_409(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="promotecohostpendinghost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="promotecohostpendingguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": guest["email"]}, headers=host_headers
    )

    resp = api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": guest["id"]}, headers=host_headers)
    assert resp.status_code == 409


def test_promote_co_host_happy_path(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="promotecohostokhost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="promotecohostokguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    inv_id = api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": guest["email"]}, headers=host_headers
    ).json()["id"]
    api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers)

    resp = api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": guest["id"]}, headers=host_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "co_host"
    assert body["already_co_host"] is False

    guests = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers).json()["guests"]
    assert next(g for g in guests if g["user_id"] == guest["id"])["role"] == "co_host"


def test_promote_co_host_bereits_co_host_ist_idempotent(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="promotecohostidemhost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="promotecohostidemguest@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    inv_id = api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": guest["email"]}, headers=host_headers
    ).json()["id"]
    api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers)
    api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": guest["id"]}, headers=host_headers)

    resp = api_client.post(f"/api/v1/parties/{party_id}/co-hosts", json={"user_id": guest["id"]}, headers=host_headers)
    assert resp.status_code == 200
    assert resp.json()["already_co_host"] is True
