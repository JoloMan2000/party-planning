"""API-Tests für `/api/v1/admin/recommendations` (Phase-3-Plan: Flutter-
Admin-Recommendations-Sektion)."""

from __future__ import annotations


def test_get_admin_recommendations_liefert_occasion_label_und_items(api_client, admin_headers):
    resp = api_client.get("/api/v1/admin/recommendations", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["occasion_label"], str) and body["occasion_label"]
    assert len(body["items"]) > 1

    first = body["items"][0]
    assert set(first.keys()) == {"item", "score", "explanation"}
    assert "id" in first["item"] and "name" in first["item"]
    assert "total_score" in first["score"]
    assert "Gesamt-Score" in first["explanation"]
