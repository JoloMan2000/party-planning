"""API-Tests für /me/discovery-preferences (+ music/artists/event-interests)
und /me/onboarding/complete (Onboarding-Spec, Phase 6)."""

from __future__ import annotations

import datetime

import accounts.discover_learning as discover_learning


def test_get_discovery_preferences_liefert_defaults_wenn_nie_gesetzt(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.get("/api/v1/me/discovery-preferences", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["discovery_radius_km"] == 25.0
    assert body["personalized_recommendations_enabled"] is True


def test_put_discovery_preferences_persistiert_und_ist_pro_user_isoliert(api_client, auth_headers_factory):
    headers_a, _user_a, _ = auth_headers_factory(email="discover-a@example.com")
    headers_b, _user_b, _ = auth_headers_factory(email="discover-b@example.com")

    resp = api_client.put(
        "/api/v1/me/discovery-preferences",
        json={
            "discovery_radius_km": 15.0,
            "discovery_city": "Berlin",
            "preferred_days": ["friday", "saturday"],
            "mainstream_discovery": 0.3,
            "personalized_recommendations_enabled": False,
        },
        headers=headers_a,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["discovery_radius_km"] == 15.0
    assert body["discovery_city"] == "Berlin"
    assert body["preferred_days"] == ["friday", "saturday"]
    assert body["personalized_recommendations_enabled"] is False

    # Anderer User darf davon nichts sehen.
    resp_b = api_client.get("/api/v1/me/discovery-preferences", headers=headers_b)
    assert resp_b.json()["discovery_city"] == ""


def test_put_music_preferences_ersetzt_vollstaendig(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()

    resp = api_client.put(
        "/api/v1/me/discovery-preferences/music",
        json={"preferences": [{"genre_id": "tech_house", "preference_level": "love"}]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = api_client.put(
        "/api/v1/me/discovery-preferences/music",
        json={"preferences": [{"genre_id": "jazz", "preference_level": "neutral"}]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["genre_id"] == "jazz"


def test_put_artist_preferences(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.put(
        "/api/v1/me/discovery-preferences/artists",
        json={
            "preferences": [
                {"artist_reference": "manual:daft-punk", "display_name": "Daft Punk", "preference_level": "love"}
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["display_name"] == "Daft Punk"
    assert body[0]["preference_level"] == "love"


def test_put_event_interests(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.put(
        "/api/v1/me/discovery-preferences/event-interests",
        json={"item_ids": ["concert", "festival"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert set(resp.json()) == {"concert", "festival"}


def _complete_onboarding_prereqs(api_client, headers):
    today = datetime.date.today()
    birth_date = today.replace(year=today.year - 25)
    api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": birth_date.isoformat()}, headers=headers
    )
    api_client.put(
        "/api/v1/me/discovery-preferences", json={"discovery_city": "Berlin"}, headers=headers
    )
    api_client.put(
        "/api/v1/me/discovery-preferences/event-interests", json={"item_ids": ["concert"]}, headers=headers
    )


def test_onboarding_complete_gibt_422_wenn_pflichtfelder_fehlen(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.post("/api/v1/me/onboarding/complete", headers=headers)
    assert resp.status_code == 422


def test_onboarding_complete_erfolgreich_wenn_pflichtfelder_gesetzt(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory(display_name="Complete User")
    _complete_onboarding_prereqs(api_client, headers)

    resp = api_client.post("/api/v1/me/onboarding/complete", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarding_completed_at"] is not None
    assert body["profile_completion_version"] == 1

    profile_resp = api_client.get("/api/v1/me/profile", headers=headers)
    assert profile_resp.json()["onboarding_completed_at"] is not None


def test_onboarding_complete_ohne_event_interesse_gibt_422(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    today = datetime.date.today()
    birth_date = today.replace(year=today.year - 25)
    api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": birth_date.isoformat()}, headers=headers
    )
    api_client.put("/api/v1/me/discovery-preferences", json={"discovery_city": "Berlin"}, headers=headers)

    resp = api_client.post("/api/v1/me/onboarding/complete", headers=headers)
    assert resp.status_code == 422


def test_reset_learning_ohne_auth_gibt_401(api_client):
    resp = api_client.post("/api/v1/me/discovery-profile/reset-learning")
    assert resp.status_code == 401


def test_reset_learning_loescht_learned_affinity(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory()
    discover_learning.apply_signal(
        api_client.db_path, user["id"], "event_type", "club_event", target_fit=1.0, weight=5.0
    )
    assert discover_learning.get_learned_affinities_for_user(api_client.db_path, user["id"]) != {}

    resp = api_client.post("/api/v1/me/discovery-profile/reset-learning", headers=headers)
    assert resp.status_code == 204
    assert discover_learning.get_learned_affinities_for_user(api_client.db_path, user["id"]) == {}


def test_reset_learning_ohne_bestehende_signale_ist_no_op(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory()
    resp = api_client.post("/api/v1/me/discovery-profile/reset-learning", headers=headers)
    assert resp.status_code == 204
