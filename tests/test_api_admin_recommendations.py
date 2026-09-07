"""API-Tests für `/api/v1/parties/{party_id}/admin/recommendations` (Phase-4-
Plan: Multi-Tenant Admin Router)."""

from __future__ import annotations


def test_get_admin_recommendations_liefert_occasion_label_und_items(api_client, host_party_factory):
    party_id, headers, _user = host_party_factory()
    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/recommendations", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["occasion_label"], str) and body["occasion_label"]
    assert len(body["items"]) > 1

    first = body["items"][0]
    assert set(first.keys()) == {"item", "score", "explanation"}
    assert "id" in first["item"] and "name" in first["item"]
    assert "total_score" in first["score"]
    assert "Gesamt-Score" in first["explanation"]
