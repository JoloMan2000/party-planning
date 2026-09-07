"""API-Tests für `/api/v1/parties/{party_id}/admin/responses` (Phase-4-Plan:
Multi-Tenant Admin Router)."""

from __future__ import annotations

import party_engine.response_storage as response_storage


def _seed_response(api_client, party_id):
    response_storage.save_response(
        api_client.db_path,
        party_id,
        name="Anna",
        start_time="18:30",
        drinks=[],
        drinks_freetext="Mineralwasser",
        food=[],
        food_freetext="",
        songs=[{"artist": "Queen", "title": "Bohemian Rhapsody"}],
    )


def test_list_responses_liefert_vorformatierte_anzeige_felder(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    _seed_response(api_client, party_id)

    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/responses", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1

    row = body[0]
    assert row["name"] == "Anna"
    assert row["drinks_freetext"] == "Mineralwasser"
    assert row["drinks_display"] == []
    assert row["food_display"] == []
    assert row["songs_display"] == "Queen – Bohemian Rhapsody"


def test_export_responses_csv_liefert_csv_mit_seeded_response(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    _seed_response(api_client, party_id)

    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/responses/csv", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Anna" in resp.text
    assert "Bohemian Rhapsody" in resp.text
