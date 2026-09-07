"""API-Tests für die In-App-Notification-Inbox (Phase 5)."""

from __future__ import annotations


def _make_party_with_invitation(api_client, auth_headers_factory, host_email: str, guest_email: str):
    host_headers, host, _ = auth_headers_factory(email=host_email)
    guest_headers, guest, _ = auth_headers_factory(email=guest_email)
    party_id = api_client.post("/api/v1/parties", json={"name": "Notif Party"}, headers=host_headers).json()["id"]
    inv = api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": guest_email}, headers=host_headers
    ).json()
    return host_headers, host, guest_headers, guest, party_id, inv["id"]


def test_invite_erzeugt_notification_fuer_eingeladenen_user(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, party_id, _inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "notifinvite-host@example.com", "notifinvite-guest@example.com"
    )
    resp = api_client.get("/api/v1/me/notifications", headers=guest_headers)
    assert resp.status_code == 200
    notifications = resp.json()
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "invitation"
    assert notifications[0]["party_id"] == party_id
    assert notifications[0]["read"] is False


def test_host_bekommt_keine_notification_fuer_eigene_einladung(api_client, auth_headers_factory):
    host_headers, _host, _g, _guest, _party_id, _inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "notifhost-host@example.com", "notifhost-guest@example.com"
    )
    resp = api_client.get("/api/v1/me/notifications", headers=host_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_rsvp_erzeugt_notification_fuer_host(api_client, auth_headers_factory):
    host_headers, _host, guest_headers, _guest, party_id, inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "notifrsvp-host@example.com", "notifrsvp-guest@example.com"
    )
    resp = api_client.put(
        f"/api/v1/invitations/{inv_id}/rsvp", json={"status": "accepted", "version": 1}, headers=guest_headers
    )
    assert resp.status_code == 200

    notifications = api_client.get("/api/v1/me/notifications", headers=host_headers).json()
    rsvp_notifications = [n for n in notifications if n["kind"] == "rsvp"]
    assert len(rsvp_notifications) == 1
    assert rsvp_notifications[0]["party_id"] == party_id


def test_mark_read_setzt_read_flag(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, _party_id, _inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "notifread-host@example.com", "notifread-guest@example.com"
    )
    notification_id = api_client.get("/api/v1/me/notifications", headers=guest_headers).json()[0]["id"]

    resp = api_client.post(f"/api/v1/me/notifications/{notification_id}/read", headers=guest_headers)
    assert resp.status_code == 200
    assert resp.json()["read"] is True

    notifications = api_client.get("/api/v1/me/notifications", headers=guest_headers).json()
    assert notifications[0]["read"] is True


def test_mark_read_fuer_fremde_notification_gibt_404(api_client, auth_headers_factory):
    _h, _host, guest_headers, _guest, _party_id, _inv_id = _make_party_with_invitation(
        api_client, auth_headers_factory, "notifcross-host@example.com", "notifcross-guest@example.com"
    )
    notification_id = api_client.get("/api/v1/me/notifications", headers=guest_headers).json()[0]["id"]

    stranger_headers, _, _ = auth_headers_factory(email="notifcross-stranger@example.com")
    resp = api_client.post(f"/api/v1/me/notifications/{notification_id}/read", headers=stranger_headers)
    assert resp.status_code == 404


def test_notifications_route_ohne_token_gibt_401(api_client):
    resp = api_client.get("/api/v1/me/notifications")
    assert resp.status_code == 401
