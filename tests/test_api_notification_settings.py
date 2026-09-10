"""API-Tests für /me/notification-settings (Social-Graph-Phase-8, Spec
§109/§156)."""

from __future__ import annotations


def test_get_notification_settings_liefert_defaults_wenn_nie_gesetzt(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="notifset-defaults@example.com")
    resp = api_client.get("/api/v1/me/notification-settings", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "friend_requests": True,
        "party_invitations": True,
        "organizer_updates": True,
        "followed_event_updates": True,
        "nearby_discover": True,
    }


def test_get_notification_settings_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/me/notification-settings")
    assert resp.status_code == 401


def test_put_notification_settings_persistiert_und_ist_pro_user_isoliert(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="notifset-a@example.com")
    headers_b, _b, _ = auth_headers_factory(email="notifset-b@example.com")

    resp = api_client.put(
        "/api/v1/me/notification-settings",
        json={"organizer_updates": False, "followed_event_updates": False},
        headers=headers_a,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["organizer_updates"] is False
    assert body["followed_event_updates"] is False
    # Weggelassene Felder fallen auf den Schema-Default True zurück (Full-Replace).
    assert body["friend_requests"] is True
    assert body["party_invitations"] is True
    assert body["nearby_discover"] is True

    # Persistiert.
    assert api_client.get("/api/v1/me/notification-settings", headers=headers_a).json() == body
    # Anderer User unberührt.
    assert api_client.get("/api/v1/me/notification-settings", headers=headers_b).json()["organizer_updates"] is True


def test_put_notification_settings_full_replace(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="notifset-replace@example.com")
    api_client.put(
        "/api/v1/me/notification-settings", json={"organizer_updates": False}, headers=headers
    )
    # Zweiter PUT ohne organizer_updates -> zurück auf True (Full-Replace, kein Merge).
    body = api_client.put(
        "/api/v1/me/notification-settings", json={"nearby_discover": False}, headers=headers
    ).json()
    assert body["organizer_updates"] is True
    assert body["nearby_discover"] is False
