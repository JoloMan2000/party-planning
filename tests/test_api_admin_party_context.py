"""API-Tests für `/api/v1/admin/party-context` (Phase-3-Plan: Flutter-Admin-
Party-Context-Sektion)."""

from __future__ import annotations


def test_get_metadata_liefert_location_types_und_countries(api_client, admin_headers):
    resp = api_client.get("/api/v1/admin/party-context/metadata", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["location_types"]) == 20
    first = body["location_types"][0]
    assert set(first.keys()) == {"id", "label_de", "label_en"}
    assert len(body["countries"]) > 100
    first_country = body["countries"][0]
    assert set(first_country.keys()) == {"code", "name"}


def test_save_party_context_persistiert_und_gibt_status_ok(api_client, admin_headers):
    payload = {
        "location_type": "garden",
        "indoor_outdoor": "outdoor",
        "country_code": "DE",
        "has_grill": True,
        "has_kitchen": False,
        "has_fridge": True,
        "has_freezer": False,
        "has_ice_machine": False,
        "has_bar": False,
        "has_coffee_machine": False,
        "has_power": True,
        "has_running_water": True,
        "dancing_possible": True,
        "neighbors_sensitive": False,
        "music_volume_limit": None,
        "self_service": True,
        "seating_ratio": 0.4,
        "weather_condition": "sunny",
        "expected_temperature_c": 24.0,
    }
    resp = api_client.post("/api/v1/admin/party-context", json=payload, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    get_resp = api_client.get("/api/v1/admin/party-context", headers=admin_headers)
    saved = get_resp.json()
    assert saved["location_type"] == "garden"
    assert saved["country_code"] == "DE"
    assert saved["has_grill"] is True
    assert saved["seating_ratio"] == 0.4
    assert saved["weather_condition"] == "sunny"
