"""API-Tests für ``POST /api/v1/parties/{id}/admin/equipment-demand``
(Phase 1) - mirrort ``tests/test_api_admin_shopping_list.py``'s Muster."""

from __future__ import annotations


def _make_guest_headers(api_client, auth_headers_factory, party_id: str) -> dict:
    import accounts.party_storage as party_storage
    from accounts.domain import PartyRole, RsvpStatus

    headers, user, _refresh_token = auth_headers_factory()
    party_storage.upsert_membership(api_client.db_path, party_id, user["id"], PartyRole.GUEST, RsvpStatus.ACCEPTED)
    return headers


def test_host_can_compute_equipment_demand_for_party(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "demand" in body
    assert "purchase_plan" in body
    # Host allein (guest_count aus Memberships) - always_on Baseline-Items sind trotzdem da.
    assert "dinner_plate" in body["demand"]


def test_co_host_has_same_access_as_host(api_client, host_party_factory, co_host_headers_factory):
    party_id, _headers, _user = host_party_factory()
    co_host_headers = co_host_headers_factory(party_id)
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=co_host_headers)
    assert resp.status_code == 200


def test_guest_role_forbidden(api_client, host_party_factory, auth_headers_factory):
    party_id, _headers, _user = host_party_factory()
    guest_headers = _make_guest_headers(api_client, auth_headers_factory, party_id)
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=guest_headers)
    assert resp.status_code == 403


def test_unknown_party_id_returns_404(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="equipadmin404@example.com")
    resp = api_client.post("/api/v1/parties/does-not-exist/admin/equipment-demand", json={}, headers=headers)
    assert resp.status_code == 404


def test_capacity_and_station_overrides_are_honored(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-demand",
        json={
            "selected_item_ids": ["cornhole_set"],
            "station_activity_interest": {"beer_pong": 2},
            "capacity_need_overrides": {"large_beverage_cooler": 75.0},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    demand = resp.json()["demand"]
    assert demand["large_beverage_cooler"]["final_required_quantity"] == 3
    assert demand["beer_pong_table"]["raw_quantity"] == 2.0
    assert "cornhole_set" in demand


def test_host_inventory_is_netted_against_computed_demand(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()

    # Host besitzt bereits 40 Wine Glasses.
    inv_resp = api_client.post(
        "/api/v1/me/equipment-inventory", json={"equipment_item_id": "wine_glass", "quantity": 40.0}, headers=headers
    )
    assert inv_resp.status_code == 201, inv_resp.text

    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=headers)
    assert resp.status_code == 200
    wine_glass = resp.json()["demand"]["wine_glass"]
    assert wine_glass["existing_quantity"] == 40.0
    assert wine_glass["missing_quantity"] == 0.0  # Host hat schon genug (nur 1 Gast/Host in der Party)
