"""API-Tests für ``/api/v1/parties/{id}/admin/equipment-venue-inventory``
(Phase 2, Spec §98/§146) - mirrort ``tests/test_api_equipment_inventory.py``'s
CRUD/404/409-Muster plus die Rollen-Checks aus ``tests/test_api_admin_equipment.py``."""

from __future__ import annotations


def test_host_can_crud_venue_inventory(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()

    create_resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "folding_chair", "quantity": 40.0, "notes": "from venue"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    provision_id = create_resp.json()["id"]

    list_resp = api_client.get(f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory", headers=headers)
    assert [p["id"] for p in list_resp.json()] == [provision_id]

    patch_resp = api_client.patch(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory/{provision_id}",
        json={"quantity": 50.0}, headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["quantity"] == 50.0
    assert patch_resp.json()["notes"] == "from venue"  # unverändert

    delete_resp = api_client.delete(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory/{provision_id}", headers=headers
    )
    assert delete_resp.status_code == 204


def test_unknown_equipment_item_id_returns_422(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "does-not-exist", "quantity": 1.0}, headers=headers,
    )
    assert resp.status_code == 422


def test_guest_role_forbidden_from_venue_inventory(api_client, host_party_factory, auth_headers_factory):
    import accounts.party_storage as party_storage
    from accounts.domain import PartyRole, RsvpStatus

    party_id, _headers, _user = host_party_factory()
    guest_headers, guest_user, _ = auth_headers_factory(email="venueinvguest@example.com")
    party_storage.upsert_membership(api_client.db_path, party_id, guest_user["id"], PartyRole.GUEST, RsvpStatus.ACCEPTED)

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "folding_chair", "quantity": 1.0}, headers=guest_headers,
    )
    assert resp.status_code == 403


def test_duplicate_provision_for_same_item_conflicts(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "folding_chair", "quantity": 1.0}, headers=headers,
    )
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "folding_chair", "quantity": 1.0}, headers=headers,
    )
    assert resp.status_code == 409


def test_unknown_provision_id_returns_404(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.patch(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory/does-not-exist",
        json={"quantity": 5.0}, headers=headers,
    )
    assert resp.status_code == 404


def test_provision_from_another_party_is_not_visible(api_client, host_party_factory):
    party_a, headers_a, _user_a = host_party_factory()
    party_b, headers_b, _user_b = host_party_factory()

    create_resp = api_client.post(
        f"/api/v1/parties/{party_a}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "folding_chair", "quantity": 1.0}, headers=headers_a,
    )
    provision_id = create_resp.json()["id"]

    resp = api_client.patch(
        f"/api/v1/parties/{party_b}/admin/equipment-venue-inventory/{provision_id}",
        json={"quantity": 5.0}, headers=headers_b,
    )
    assert resp.status_code == 404
