"""API-Tests für die anonymen Gäste-Endpunkte (Phase-1-Plan Schritt 7)."""

from __future__ import annotations

import party_engine.response_storage as response_storage


def test_party_info_liefert_titel_und_theme(api_client):
    resp = api_client.get("/api/v1/guest/party-info?lang=de")
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_type"]
    assert body["title"]
    assert "hero_subtitle" in body
    assert body["occasion_label"]


def test_party_info_occasion_label_ist_sprachabhaengig(api_client):
    de_body = api_client.get("/api/v1/guest/party-info?lang=de").json()
    en_body = api_client.get("/api/v1/guest/party-info?lang=en").json()
    assert de_body["occasion_label"] != en_body["occasion_label"]


def test_submit_response_landet_in_db(api_client):
    payload = {
        "name": "Max",
        "start_time": "19:00",
        "drinks": ["beer_pils"],
        "drinks_freetext": "",
        "food": ["pizza_margherita"],
        "food_freetext": "",
        "songs": [{"artist": "Queen", "title": "Bohemian Rhapsody"}],
    }
    resp = api_client.post("/api/v1/guest/responses", json=payload)
    assert resp.status_code == 201

    rows = response_storage.load_responses(api_client.db_path)
    assert len(rows) == 1
    assert rows[0]["name"] == "Max"
    import json

    assert json.loads(rows[0]["drinks"]) == ["beer_pils"]
    assert json.loads(rows[0]["songs"])[0]["artist"] == "Queen"


def test_recommendations_endpoint_liefert_item_id_liste(api_client):
    resp = api_client.post(
        "/api/v1/guest/recommendations",
        json={"name": "Test", "drinks": [], "food": [], "top_n": 5},
    )
    assert resp.status_code == 200
    ids = resp.json()
    assert isinstance(ids, list)
    assert len(ids) <= 5


def test_calendar_ics_ohne_datum_gibt_404(api_client):
    resp = api_client.get("/api/v1/guest/calendar.ics")
    assert resp.status_code == 404
