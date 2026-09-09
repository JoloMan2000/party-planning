"""API-Tests für die Organizer-Domain-Foundation-Endpunkte
(``/api/v1/organizers/*``, ``backend/app/routers/organizers.py``,
Social-Graph-Phase-4). Backend-only diese Phase, siehe Plan."""

from __future__ import annotations


def _create_organizer(api_client, headers, display_name="Acme Events"):
    resp = api_client.post("/api/v1/organizers", json={"display_name": display_name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()


def test_create_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/organizers", json={"display_name": "Acme Events"})
    assert resp.status_code == 401


def test_create_erzeugt_organizer_mit_owner_rolle(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="orgowner1@example.com")
    organizer = _create_organizer(api_client, headers)
    assert organizer["owner_user_id"] == user["id"]
    assert organizer["verification_status"] == "unverified"
    assert organizer["my_role"] == "owner"


def test_get_als_mitglied_erfolgreich(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="orgowner2@example.com")
    organizer = _create_organizer(api_client, headers)
    resp = api_client.get(f"/api/v1/organizers/{organizer['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["my_role"] == "owner"


def test_get_als_nicht_mitglied_gibt_403(api_client, auth_headers_factory):
    owner_headers, _owner, _ = auth_headers_factory(email="orgowner3@example.com")
    other_headers, _other, _ = auth_headers_factory(email="orgoutsider3@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    resp = api_client.get(f"/api/v1/organizers/{organizer['id']}", headers=other_headers)
    assert resp.status_code == 403


def test_get_unbekannter_organizer_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="orgowner4@example.com")
    resp = api_client.get("/api/v1/organizers/unknown-id", headers=headers)
    assert resp.status_code == 404


def test_list_mine_enthaelt_eigene_organizer(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="orgowner5@example.com")
    organizer = _create_organizer(api_client, headers)
    resp = api_client.get("/api/v1/organizers/mine", headers=headers)
    assert resp.status_code == 200
    ids = {o["id"] for o in resp.json()}
    assert organizer["id"] in ids


def test_list_mine_ohne_organizer_ist_leer(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="orgowner6@example.com")
    resp = api_client.get("/api/v1/organizers/mine", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_member_als_owner_erfolgreich(api_client, auth_headers_factory):
    owner_headers, _owner, _ = auth_headers_factory(email="orgowner7@example.com")
    _member_headers, member, _ = auth_headers_factory(email="orgmember7@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    resp = api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": member["id"], "role": "editor"},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "editor"
    assert resp.json()["user_id"] == member["id"]


def test_add_member_als_nicht_owner_gibt_403(api_client, auth_headers_factory):
    owner_headers, _owner, _ = auth_headers_factory(email="orgowner8@example.com")
    member_headers, member, _ = auth_headers_factory(email="orgmember8@example.com")
    _other_headers, other, _ = auth_headers_factory(email="orgother8@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": member["id"], "role": "viewer"},
        headers=owner_headers,
    )
    resp = api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": other["id"], "role": "viewer"},
        headers=member_headers,
    )
    assert resp.status_code == 403


def test_add_member_self_target_gibt_400(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="orgowner9@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    resp = api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": owner["id"], "role": "viewer"},
        headers=owner_headers,
    )
    assert resp.status_code == 400


def test_add_member_gleiche_rolle_ist_idempotent(api_client, auth_headers_factory):
    owner_headers, _owner, _ = auth_headers_factory(email="orgowner10@example.com")
    _member_headers, member, _ = auth_headers_factory(email="orgmember10@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    first = api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": member["id"], "role": "viewer"},
        headers=owner_headers,
    )
    second = api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": member["id"], "role": "viewer"},
        headers=owner_headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["role"] == "viewer"


def test_add_member_unbekannter_organizer_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="orgowner11@example.com")
    _member_headers, member, _ = auth_headers_factory(email="orgmember11@example.com")
    resp = api_client.post(
        "/api/v1/organizers/unknown-id/members",
        json={"user_id": member["id"], "role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_add_member_ungueltige_rolle_gibt_422(api_client, auth_headers_factory):
    owner_headers, _owner, _ = auth_headers_factory(email="orgowner12@example.com")
    _member_headers, member, _ = auth_headers_factory(email="orgmember12@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    resp = api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": member["id"], "role": "superuser"},
        headers=owner_headers,
    )
    assert resp.status_code == 422


def test_list_members_als_mitglied_erfolgreich(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="orgowner13@example.com")
    _member_headers, member, _ = auth_headers_factory(email="orgmember13@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    api_client.post(
        f"/api/v1/organizers/{organizer['id']}/members",
        json={"user_id": member["id"], "role": "admin"},
        headers=owner_headers,
    )
    resp = api_client.get(f"/api/v1/organizers/{organizer['id']}/members", headers=owner_headers)
    assert resp.status_code == 200
    user_ids = {m["user_id"] for m in resp.json()["members"]}
    assert {owner["id"], member["id"]} == user_ids


def test_list_members_als_nicht_mitglied_gibt_403(api_client, auth_headers_factory):
    owner_headers, _owner, _ = auth_headers_factory(email="orgowner14@example.com")
    other_headers, _other, _ = auth_headers_factory(email="orgoutsider14@example.com")
    organizer = _create_organizer(api_client, owner_headers)
    resp = api_client.get(f"/api/v1/organizers/{organizer['id']}/members", headers=other_headers)
    assert resp.status_code == 403
