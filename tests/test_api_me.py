"""API-Tests für /me, /me/parties, /me/invitations (Account-basierter Pivot,
Phase 1)."""

from __future__ import annotations


def test_get_me_liefert_eigenes_profil_ohne_passwort_hash(api_client, auth_headers_factory):
    headers, user, _refresh_token = auth_headers_factory(email="whoami@example.com", display_name="Who Am I")
    resp = api_client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user["id"]
    assert body["email"] == "whoami@example.com"
    assert body["display_name"] == "Who Am I"
    assert "password_hash" not in body
    assert "password" not in body


def test_get_me_ohne_token_gibt_401(api_client):
    resp = api_client.get("/api/v1/me")
    assert resp.status_code == 401


def test_get_my_parties_leer_wenn_keine_party(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.get("/api/v1/me/parties", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_my_parties_enthaelt_gehostete_und_eingeladene_parties(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="myparties-host@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="myparties-guest@example.com")

    resp = api_client.post("/api/v1/parties", json={"name": "My Party"}, headers=host_headers)
    assert resp.status_code == 201
    party_id = resp.json()["id"]

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "myparties-guest@example.com"},
        headers=host_headers,
    )
    assert resp.status_code == 201

    resp = api_client.get("/api/v1/me/parties", headers=host_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = api_client.get("/api/v1/me/parties", headers=guest_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == party_id


def test_get_my_invitations(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="myinv-host@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="myinv-guest@example.com")

    resp = api_client.post("/api/v1/parties", json={"name": "Invite Party"}, headers=host_headers)
    party_id = resp.json()["id"]

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "myinv-guest@example.com"},
        headers=host_headers,
    )
    invitation_id = resp.json()["id"]

    resp = api_client.get("/api/v1/me/invitations", headers=guest_headers)
    assert resp.status_code == 200
    invitations = resp.json()
    assert len(invitations) == 1
    assert invitations[0]["id"] == invitation_id
    assert invitations[0]["status"] == "pending"

    resp = api_client.get("/api/v1/me/invitations", headers=host_headers)
    assert resp.status_code == 200
    assert resp.json() == []
