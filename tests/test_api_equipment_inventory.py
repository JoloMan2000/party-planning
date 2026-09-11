"""API-Tests für ``/api/v1/me/equipment-inventory`` (Phase 1, Spec §7/§166)."""

from __future__ import annotations


def test_requires_authentication(api_client):
    resp = api_client.get("/api/v1/me/equipment-inventory")
    assert resp.status_code == 401


def test_create_list_update_delete_roundtrip(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="equipinv1@example.com")

    create_resp = api_client.post(
        "/api/v1/me/equipment-inventory",
        json={"equipment_item_id": "beer_pong_table", "quantity": 2.0, "notes": "in the garage"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["equipment_item_id"] == "beer_pong_table"
    assert body["quantity"] == 2.0
    assert body["available"] is True
    item_id = body["id"]

    list_resp = api_client.get("/api/v1/me/equipment-inventory", headers=headers)
    assert list_resp.status_code == 200
    assert [i["id"] for i in list_resp.json()] == [item_id]

    patch_resp = api_client.patch(
        f"/api/v1/me/equipment-inventory/{item_id}", json={"quantity": 3.0, "available": False}, headers=headers
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["quantity"] == 3.0
    assert patched["available"] is False
    assert patched["notes"] == "in the garage"  # unverändert

    delete_resp = api_client.request("DELETE", f"/api/v1/me/equipment-inventory/{item_id}", headers=headers)
    assert delete_resp.status_code == 204
    assert api_client.get("/api/v1/me/equipment-inventory", headers=headers).json() == []


def test_cannot_create_duplicate_inventory_row_for_same_equipment_item(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="equipinv2@example.com")
    assert api_client.post(
        "/api/v1/me/equipment-inventory", json={"equipment_item_id": "wine_glass", "quantity": 12.0}, headers=headers
    ).status_code == 201
    resp = api_client.post(
        "/api/v1/me/equipment-inventory", json={"equipment_item_id": "wine_glass", "quantity": 1.0}, headers=headers
    )
    assert resp.status_code == 409


def test_unknown_equipment_item_id_rejected(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="equipinv3@example.com")
    resp = api_client.post(
        "/api/v1/me/equipment-inventory", json={"equipment_item_id": "does_not_exist"}, headers=headers
    )
    assert resp.status_code == 422


def test_cannot_patch_or_delete_another_users_inventory_item(api_client, auth_headers_factory):
    a_headers, _a, _ = auth_headers_factory(email="equipinv4a@example.com")
    b_headers, _b, _ = auth_headers_factory(email="equipinv4b@example.com")

    create_resp = api_client.post(
        "/api/v1/me/equipment-inventory", json={"equipment_item_id": "cooler_box", "quantity": 1.0}, headers=a_headers
    )
    item_id = create_resp.json()["id"]

    assert api_client.patch(
        f"/api/v1/me/equipment-inventory/{item_id}", json={"quantity": 5.0}, headers=b_headers
    ).status_code == 404
    assert api_client.request(
        "DELETE", f"/api/v1/me/equipment-inventory/{item_id}", headers=b_headers
    ).status_code == 404
    # A's Zeile ist unangetastet.
    assert api_client.get("/api/v1/me/equipment-inventory", headers=a_headers).json()[0]["quantity"] == 1.0
