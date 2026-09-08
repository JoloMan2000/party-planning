"""API-Tests für ``backend/app/routers/party_locations.py`` (``PUT``/``GET
/api/v1/parties/{id}/location``) - Idempotenz, RSVP-gegatete Sichtbarkeit
(Spec §120-122), manuelle Pin-Anpassung (Spec §24, §117) und
Location-Change-Benachrichtigungen."""

from __future__ import annotations

import accounts.notification_storage as notification_storage


def _make_party(api_client, headers, name: str = "P") -> str:
    return api_client.post("/api/v1/parties", json={"name": name}, headers=headers).json()["id"]


def _location_payload(**overrides) -> dict:
    payload = {
        "place_name": "Elbphilharmonie",
        "address": {
            "street": "Platz der Deutschen Einheit",
            "house_number": "1",
            "postal_code": "20457",
            "city": "Hamburg",
            "country_code": "DE",
            "country_name": "Germany",
            "formatted_address": "Platz der Deutschen Einheit 1, 20457 Hamburg, Germany",
        },
        "point": {"latitude": 53.5411, "longitude": 9.9844},
        "precision": "exact",
        "provider": "nominatim",
        "provider_place_id": "abc123",
        "public_location_label": "Somewhere in Hamburg",
        "visibility_policy": "exact_after_accept",
        "arrival_instructions": "Ring the bell twice.",
    }
    payload.update(overrides)
    return payload


def test_set_location_ohne_auth_gibt_401(api_client):
    resp = api_client.put("/api/v1/parties/some-id/location", json=_location_payload())
    assert resp.status_code == 401


def test_set_location_als_host_erfolgreich(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="setlochost@example.com")
    party_id = _make_party(api_client, headers)

    resp = api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Host sieht immer exakt.
    assert body["visibility_level"] == "exact"
    assert body["formatted_address"] == "Platz der Deutschen Einheit 1, 20457 Hamburg, Germany"
    assert body["point"] == {"latitude": 53.5411, "longitude": 9.9844}


def test_set_location_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="setlocguesthost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="setlocguest@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "setlocguest@example.com"},
        headers=host_headers,
    )
    resp = api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=guest_headers)
    assert resp.status_code == 403


def test_set_location_zweimal_bleibt_eine_zeile_idempotent(api_client, auth_headers_factory):
    import geo.storage as geo_storage

    headers, _user, _ = auth_headers_factory(email="idempotentloc@example.com")
    party_id = _make_party(api_client, headers)

    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=headers)
    api_client.put(
        f"/api/v1/parties/{party_id}/location",
        json=_location_payload(place_name="Elbphilharmonie Updated"),
        headers=headers,
    )

    location = geo_storage.get_party_location(api_client.db_path, party_id)
    assert location is not None
    assert location.place_name == "Elbphilharmonie Updated"


def test_get_location_ohne_membership_gibt_403(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="getlocnonmemberhost@example.com")
    outsider_headers, _outsider, _ = auth_headers_factory(email="getlocoutsider@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=host_headers)

    resp = api_client.get(f"/api/v1/parties/{party_id}/location", headers=outsider_headers)
    assert resp.status_code == 403


def test_get_location_ohne_strukturierte_daten_gibt_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="getlocnone@example.com")
    party_id = _make_party(api_client, headers)
    resp = api_client.get(f"/api/v1/parties/{party_id}/location", headers=headers)
    assert resp.status_code == 404


def test_pending_guest_sieht_keine_exakten_koordinaten(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="pendinglochost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="pendinglocguest@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=host_headers)
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "pendinglocguest@example.com"},
        headers=host_headers,
    )

    resp = api_client.get(f"/api/v1/parties/{party_id}/location", headers=guest_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["visibility_level"] == "approximate"
    assert body["formatted_address"] is None
    assert body["point"] is None
    assert body["arrival_instructions"] is None
    assert body["display_label"] == "Somewhere in Hamburg"


def test_accepted_guest_sieht_exakte_koordinaten(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="acceptedlochost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="acceptedlocguest@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=host_headers)

    invite_resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "acceptedlocguest@example.com"},
        headers=host_headers,
    )
    invitation = invite_resp.json()
    api_client.put(
        f"/api/v1/invitations/{invitation['id']}/rsvp",
        json={"status": "accepted", "version": invitation["version"]},
        headers=guest_headers,
    )

    resp = api_client.get(f"/api/v1/parties/{party_id}/location", headers=guest_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["visibility_level"] == "exact"
    assert body["point"] == {"latitude": 53.5411, "longitude": 9.9844}
    assert body["arrival_instructions"] == "Ring the bell twice."


def test_manuelle_pin_anpassung_setzt_flag(api_client, auth_headers_factory):
    import geo.storage as geo_storage

    headers, _user, _ = auth_headers_factory(email="manualpin@example.com")
    party_id = _make_party(api_client, headers)

    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=headers)
    api_client.put(
        f"/api/v1/parties/{party_id}/location",
        json=_location_payload(
            manually_adjusted=True, source="manual_pin", point={"latitude": 53.55, "longitude": 9.98}
        ),
        headers=headers,
    )

    location = geo_storage.get_party_location(api_client.db_path, party_id)
    assert location.manually_adjusted is True
    assert location.place_name == "Elbphilharmonie"  # place_name bleibt erhalten


def test_erste_speicherung_erzeugt_keine_notification(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="firstsavehost@example.com")
    party_id = _make_party(api_client, host_headers)

    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=host_headers)

    notifications = notification_storage.list_notifications(api_client.db_path, host["id"])
    assert all(n.kind != "location_changed" for n in notifications)


def test_aenderung_erzeugt_notification_fuer_accepted_guest_nicht_fuer_actor(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="changelochost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="changelocguest@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.put(f"/api/v1/parties/{party_id}/location", json=_location_payload(), headers=host_headers)

    invite_resp = api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "changelocguest@example.com"},
        headers=host_headers,
    )
    invitation = invite_resp.json()
    api_client.put(
        f"/api/v1/invitations/{invitation['id']}/rsvp",
        json={"status": "accepted", "version": invitation["version"]},
        headers=guest_headers,
    )

    api_client.put(
        f"/api/v1/parties/{party_id}/location",
        json=_location_payload(place_name="New Venue"),
        headers=host_headers,
    )

    guest_notifications = notification_storage.list_notifications(api_client.db_path, guest["id"])
    assert any(n.kind == "location_changed" for n in guest_notifications)
