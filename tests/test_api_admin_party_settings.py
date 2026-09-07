"""API-Tests für `/api/v1/parties/{party_id}/admin/party-settings` (Phase-4-
Plan: Multi-Tenant Admin Router)."""

from __future__ import annotations


def test_get_party_settings_liefert_aktuelle_settings(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "event_type" in body
    assert "party_name" in body


def test_get_event_types_liefert_alle_typen_mit_labels(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings/event-types", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 1
    first = body[0]
    assert set(first.keys()) == {"id", "emoji", "label_de", "label_en", "default_title"}


def test_save_party_settings_persistiert_und_gibt_status_ok(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    payload = {
        "event_type": "birthday",
        "party_name": "Max' Geburtstag",
        "party_date": "",
        "party_start_time": "20:00",
        "party_duration_hours": 5.0,
        "party_location": "Musterstraße 1",
    }
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/party-settings", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    get_resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings", headers=headers)
    saved = get_resp.json()
    assert saved["event_type"] == "birthday"
    assert saved["party_name"] == "Max' Geburtstag"
    assert saved["party_start_time"] == "20:00"
