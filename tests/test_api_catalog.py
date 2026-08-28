"""API-Tests für die anonymen Katalog-Endpunkte (Phase-1-Plan Schritt 7)."""

from __future__ import annotations

from party_engine.catalog_curation import save_catalog_curation_settings
from party_engine.domain import CatalogCurationSettings


def test_drinks_endpoint_liefert_nichtleere_liste(api_client):
    resp = api_client.get("/api/v1/catalog/drinks")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    assert all("id" in item for item in items)


def test_food_endpoint_liefert_nichtleere_liste(api_client):
    resp = api_client.get("/api/v1/catalog/food")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0


def test_occasions_endpoint_liefert_nichtleere_liste(api_client):
    resp = api_client.get("/api/v1/catalog/occasions")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_drinks_endpoint_liefert_uebersetzten_display_name(api_client):
    de_items = {item["id"]: item for item in api_client.get("/api/v1/catalog/drinks?lang=de").json()}
    en_items = {item["id"]: item for item in api_client.get("/api/v1/catalog/drinks?lang=en").json()}

    assert de_items["beer_pils"]["display_name"] == de_items["beer_pils"]["name"]
    assert en_items["beer_pils"]["display_name"] != ""
    assert en_items["beer_pils"]["name"] == de_items["beer_pils"]["name"]


def test_curation_filter_wird_von_drinks_endpoint_respektiert(api_client):
    all_drinks = api_client.get("/api/v1/catalog/drinks").json()
    assert len(all_drinks) > 1
    keep_id = all_drinks[0]["id"]

    save_catalog_curation_settings(
        api_client.db_path,
        CatalogCurationSettings(enabled=True, curated_item_ids={keep_id}),
    )

    curated_drinks = api_client.get("/api/v1/catalog/drinks").json()
    assert [item["id"] for item in curated_drinks] == [keep_id]
