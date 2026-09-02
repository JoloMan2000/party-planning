"""API-Tests für Invitation-Ansicht + RSVP (Account-basierter Pivot,
Phase 1, AUFGABE-Spec §47/§48/§56/§57)."""

from __future__ import annotations

import uuid


def _make_party_with_invitation(api_client, auth_headers_factory, host_email: str, guest_email: str):
    host_headers, host, _ = auth_headers_factory(email=host_email)
    guest_headers, guest, _ = auth_headers_factory(email=guest_email)
    party_id = api_client.post("/api/v1/parties", json={"name": "P"}, headers=host_headers).json()["id"]
    inv = api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": guest_email}, headers=host_headers
    ).json()
    return host_headers, host, guest_headers, guest, party_id, inv["id"]


def test_get_invitation_als_invited_user_markiert_viewed(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "invview-host@example.com", "invview-guest@example.com"
    )
    resp = api_client.get(f"/api/v1/invitations/{inv_id}", headers=guest_headers)
    assert resp.status_code == 200
    assert resp.json()["viewed_at"] is not None


def test_get_invitation_als_host_erlaubt_ohne_viewed_zu_setzen(api_client, auth_headers_factory):
    host_headers, _host, _g, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "invhostview-host@example.com", "invhostview-guest@example.com"
    )
    resp = api_client.get(f"/api/v1/invitations/{inv_id}", headers=host_headers)
    assert resp.status_code == 200
    assert resp.json()["viewed_at"] is None


def test_get_invitation_als_unbeteiligter_gibt_403(api_client, auth_headers_factory):
    _h, _host, _g, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "invforbid-host@example.com", "invforbid-guest@example.com"
    )
    stranger_headers, _, _ = auth_headers_factory(email="invforbid-stranger@example.com")
    resp = api_client.get(f"/api/v1/invitations/{inv_id}", headers=stranger_headers)
    assert resp.status_code == 403


def test_rsvp_happy_path_matcht_spec_shape(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvphappy-host@example.com", "rsvphappy-guest@example.com"
    )
    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"invitation_id", "party_id", "status", "responded_at", "version"}
    assert body["invitation_id"] == inv_id
    assert body["party_id"] == party_id
    assert body["status"] == "accepted"
    assert body["version"] == 2
    assert body["responded_at"] is not None


def test_rsvp_als_falscher_user_gibt_403(api_client, auth_headers_factory):
    _h, _host, _g, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvpwrong-host@example.com", "rsvpwrong-guest@example.com"
    )
    stranger_headers, _, _ = auth_headers_factory(email="rsvpwrong-stranger@example.com")
    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=stranger_headers)
    assert resp.status_code == 403


def test_rsvp_als_host_gibt_403(api_client, auth_headers_factory):
    host_headers, _host, _g, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvphost-host@example.com", "rsvphost-guest@example.com"
    )
    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=host_headers)
    assert resp.status_code == 403


def test_rsvp_stale_version_gibt_409(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvpstale-host@example.com", "rsvpstale-guest@example.com"
    )
    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers)
    assert resp.status_code == 200

    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "tentative", "version": 1}, headers=guest_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["current_version"] == 2


def test_rsvp_invalid_transition_gibt_422(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvpinvalid-host@example.com", "rsvpinvalid-guest@example.com"
    )
    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "revoked", "version": 1}, headers=guest_headers)
    assert resp.status_code == 422


def test_rsvp_idempotentes_double_send(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, _party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvpidem-host@example.com", "rsvpidem-guest@example.com"
    )
    client_request_id = uuid.uuid4().hex
    payload = {"status": "accepted", "version": 1, "client_request_id": client_request_id}

    resp1 = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json=payload, headers=guest_headers)
    assert resp1.status_code == 200
    assert resp1.json()["version"] == 2

    resp2 = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json=payload, headers=guest_headers)
    assert resp2.status_code == 200
    assert resp2.json()["version"] == 2  # unverändert, kein zweiter Bump


def test_rsvp_voller_transition_zyklus_und_counts_update(api_client, auth_headers_factory):
    host_headers, _host, guest_headers, _guest, party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "rsvpcycle-host@example.com", "rsvpcycle-guest@example.com"
    )
    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "tentative", "version": 1}, headers=guest_headers)
    assert resp.status_code == 200
    assert resp.json()["version"] == 2

    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 2}, headers=guest_headers)
    assert resp.status_code == 200
    assert resp.json()["version"] == 3

    guests = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers).json()
    assert guests["counts"]["accepted"] == 1
    assert guests["counts"]["tentative"] == 0

    resp = api_client.put(f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "declined", "version": 3}, headers=guest_headers)
    assert resp.status_code == 200

    guests = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers).json()
    assert guests["counts"]["declined"] == 1
