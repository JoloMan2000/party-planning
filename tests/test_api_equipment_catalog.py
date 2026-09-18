"""API-Tests für ``GET /api/v1/equipment/catalog`` (Mobile-UI-Phase)."""

from __future__ import annotations


def test_requires_authentication(api_client):
    resp = api_client.get("/api/v1/equipment/catalog")
    assert resp.status_code == 401


def test_returns_all_active_items_with_resolved_category_names(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="equipcatalog@example.com")
    resp = api_client.get("/api/v1/equipment/catalog", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 66  # 59 (Phase 1) + 7 (Phase 2: furniture + weather_outdoor)

    by_id = {row["id"]: row for row in body}
    cooler = by_id["large_beverage_cooler"]
    assert cooler["equipment_type"] == "rental"
    assert cooler["category_id"] == "bar_equipment"
    assert cooler["category_name"] == "Bar Equipment"
    assert cooler["subcategory_id"] == "ice_cooling"
    assert cooler["subcategory_name"] == "Ice & Cooling"

    # Ein Item ohne Subkategorie (cleaning_hygiene hat keine Subs).
    trash_bag = by_id["trash_bag"]
    assert trash_bag["subcategory_id"] is None
    assert trash_bag["subcategory_name"] is None

    # Sortiert nach Name.
    names = [row["name"] for row in body]
    assert names == sorted(names)


def test_tags_are_sorted(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="equipcatalogtags@example.com")
    resp = api_client.get("/api/v1/equipment/catalog", headers=headers)
    by_id = {row["id"]: row for row in resp.json()}
    wine_glass = by_id["wine_glass"]
    assert wine_glass["tags"] == sorted(wine_glass["tags"])
    assert wine_glass["tags"] == ["bar", "tableware"]
