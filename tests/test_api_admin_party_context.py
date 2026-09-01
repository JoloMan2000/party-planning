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


def test_get_derived_party_context_liefert_abgeleitete_felder(api_client, admin_headers):
    resp = api_client.get("/api/v1/admin/party-context/derived", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["season"] in {"spring", "summer", "autumn", "winter"}
    assert body["daypart_primary"]
    assert body["temperature_class"] in {"cold", "cool", "mild", "warm", "hot"}
    assert body["group_size_class"]
    assert isinstance(body["operational_constraints"], list)
    assert isinstance(body["explanations"], list)


def test_override_add_list_delete_roundtrip(api_client, admin_headers):
    payload = {"key": "temperature_class", "value": "warm", "reason": "Zelt mit Heizung"}
    add_resp = api_client.post("/api/v1/admin/party-context/overrides", json=payload, headers=admin_headers)
    assert add_resp.status_code == 201

    list_resp = api_client.get("/api/v1/admin/party-context/overrides", headers=admin_headers)
    overrides = list_resp.json()
    assert any(o["key"] == "temperature_class" and o["value"] == "warm" for o in overrides)

    delete_resp = api_client.delete(
        "/api/v1/admin/party-context/overrides/temperature_class", headers=admin_headers
    )
    assert delete_resp.status_code == 200

    list_resp_after = api_client.get("/api/v1/admin/party-context/overrides", headers=admin_headers)
    assert not any(o["key"] == "temperature_class" for o in list_resp_after.json())
