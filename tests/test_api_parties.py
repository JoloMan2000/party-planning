"""API-Tests für Party-CRUD, Gästeliste + Einladungen (Account-basierter
Pivot, Phase 1)."""

from __future__ import annotations


def test_create_party_macht_ersteller_zum_host(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory()
    resp = api_client.post("/api/v1/parties", json={"name": "Summer BBQ", "location": "Garden"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Summer BBQ"
    assert body["host_user_id"] == user["id"]


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
