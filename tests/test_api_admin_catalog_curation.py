"""API-Tests für `/api/v1/parties/{party_id}/admin/catalog-curation` (Phase-4-
Plan: Multi-Tenant Admin Router, mirroring `render_catalog_curation_section`)."""

from __future__ import annotations


def test_get_curation_liefert_default_settings(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/catalog-curation", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["curated_item_ids"] == []


def test_save_und_get_curation_roundtrip(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    payload = {"enabled": True, "curated_item_ids": ["beer_pils", "cola"]}
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/catalog-curation", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    get_resp = api_client.get(f"/api/v1/parties/{party_id}/admin/catalog-curation", headers=headers)
    saved = get_resp.json()
    assert saved["enabled"] is True
    assert set(saved["curated_item_ids"]) == {"beer_pils", "cola"}


def test_get_items_liefert_ungefilterten_katalog_auch_wenn_kuration_aktiv(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    # Kuration aktivieren + auf ein einzelnes Item einschränken ...
    payload = {"enabled": True, "curated_item_ids": ["cola"]}
    resp = api_client.post(f"/api/v1/parties/{party_id}/admin/catalog-curation", json=payload, headers=headers)
    assert resp.status_code == 200

    # ... der Admin muss trotzdem den VOLLEN Katalog sehen, um die
    # Einschränkung erweitern zu können (mirroring `apply_curation=False` in
    # `_drink_items`/`_food_items`).
    items_resp = api_client.get(f"/api/v1/parties/{party_id}/admin/catalog-curation/items", headers=headers)
    assert items_resp.status_code == 200
    body = items_resp.json()
    assert len(body["drinks"]) > 1
    assert len(body["food"]) > 1

    drink_ids = {item["id"] for item in body["drinks"]}
    assert "cola" in drink_ids

    # Gegenprobe: der Gäste-Katalog-Endpunkt wendet die Kuration weiterhin an.
    guest_resp = api_client.get(f"/api/v1/guest/{party_id}/catalog/drinks")
    guest_drink_ids = {item["id"] for item in guest_resp.json()}
    assert guest_drink_ids == {"cola"}
