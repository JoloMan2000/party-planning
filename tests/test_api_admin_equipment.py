"""API-Tests für ``POST /api/v1/parties/{id}/admin/equipment-demand``
(Phase 1 + PartyContext-Integration in Phase 2) - mirrort
``tests/test_api_admin_shopping_list.py``'s Muster."""

from __future__ import annotations

import pytest


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


def test_venue_chairs_cover_seating_demand_no_new_procurement(api_client, host_party_factory, auth_headers_factory):
    """Spec §146 "TEST - VENUE PROVIDES CHAIRS" exakt: 50 Gäste * 0.6
    seating_ratio = 30 benötigte Sitzplätze, Venue stellt 40 Stühle ->
    keine neue Beschaffung."""
    import accounts.party_storage as party_storage
    from accounts.domain import PartyRole, RsvpStatus

    party_id, headers, _user = host_party_factory()
    # 49 zusätzliche Gäste + Host = 50 Gäste gesamt.
    for i in range(49):
        guest_headers, guest_user, _ = auth_headers_factory(email=f"venuechair{i}@example.com")
        party_storage.upsert_membership(api_client.db_path, party_id, guest_user["id"], PartyRole.GUEST, RsvpStatus.ACCEPTED)

    api_client.post(f"/api/v1/parties/{party_id}/admin/party-context", json={"seating_ratio": 0.6}, headers=headers)
    api_client.post(
        f"/api/v1/parties/{party_id}/admin/equipment-venue-inventory",
        json={"equipment_item_id": "folding_chair", "quantity": 40.0}, headers=headers,
    )

    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    chair = resp.json()["demand"]["folding_chair"]
    assert chair["raw_quantity"] == pytest.approx(30.0)  # 50 * 0.6 = 30 seats needed (§146)
    assert chair["missing_quantity"] == 0.0  # 40 vorhanden >= 30 benötigt


def test_context_recommendations_appear_for_hot_outdoor_party(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    api_client.post(
        f"/api/v1/parties/{party_id}/admin/party-context",
        json={"indoor_outdoor": "outdoor", "expected_temperature_c": 35.0}, headers=headers,
    )
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=headers)
    assert resp.status_code == 200
    recs = resp.json()["context_recommendations"]
    assert "sun_shade_parasol" in {r["item_id"] for r in recs}


def test_real_beverage_and_food_plan_drive_cooler_and_cake_accessories(api_client, host_party_factory):
    """Spec §49/§51/§150 end-to-end: eine echte, über die Guest-API
    eingereichte Antwort mit einem Bier (kalte Familie) und einem Kuchen
    treibt reale Equipment-Demand - nicht einen manuell getippten Override."""
    party_id, headers, _user = host_party_factory()

    submit_resp = api_client.post(
        f"/api/v1/guest/{party_id}/responses",
        json={"name": "Anna", "start_time": "19:00", "drinks": ["beer_pils"], "food": ["kaesekuchen"]},
    )
    assert submit_resp.status_code == 201, submit_resp.text

    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/equipment-demand", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    demand = resp.json()["demand"]

    # party_engine always adds a baseline per-guest water demand
    # (PartyConfig.water_l_per_guest=1.5, scaled by the derived context's
    # water_multiplier and water's own 0.15 reserve_pct) ON TOP OF the
    # explicitly chosen beer - both "water" and "beer" are cold families, so
    # BOTH correctly count toward real cooler capacity (verified by running
    # the real pipeline directly against this exact response: water =
    # 2.61625L, beer_pils = 0.84L). This is real, comprehensive integration,
    # not a manually-typed override.
    cooler = demand["large_beverage_cooler"]
    assert cooler["raw_quantity"] == pytest.approx((2.61625 + 0.84) / 30.0)

    assert demand["cake_knife"]["raw_quantity"] == 1.0
    assert demand["cake_server"]["raw_quantity"] == 1.0
