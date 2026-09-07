"""API-Tests für /me/profile + birth-date-correction (Onboarding-Spec,
Phase 6)."""

from __future__ import annotations

import datetime


def test_get_profile_ohne_onboarding_gibt_404(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.get("/api/v1/me/profile", headers=headers)
    assert resp.status_code == 404


def test_patch_profile_ohne_bestehendes_profil_gibt_409(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    resp = api_client.patch("/api/v1/me/profile", json={"bio": "Hi"}, headers=headers)
    assert resp.status_code == 409


def test_birth_date_correction_legt_profil_initial_an_und_berechnet_alter(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    today = datetime.date.today()
    birth_date = today.replace(year=today.year - 30)

    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction",
        json={"birth_date": birth_date.isoformat(), "reason": "Onboarding"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["birth_date"] == birth_date.isoformat()
    assert body["age"] == 30
    assert body["onboarding_completed_at"] is None


def test_birth_date_correction_ablehnung_bei_zukunftsdatum(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    future_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": future_date}, headers=headers
    )
    assert resp.status_code == 422


def test_birth_date_correction_ablehnung_bei_zu_jungem_alter(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    today = datetime.date.today()
    too_young = today.replace(year=today.year - 10).isoformat()
    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": too_young}, headers=headers
    )
    assert resp.status_code == 422


def test_patch_profile_aendert_gender_und_bio_nicht_birth_date(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    today = datetime.date.today()
    birth_date = today.replace(year=today.year - 25)
    api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": birth_date.isoformat()}, headers=headers
    )

    resp = api_client.patch(
        "/api/v1/me/profile", json={"gender": "non-binary", "bio": "Loves techno."}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gender"] == "non-binary"
    assert body["bio"] == "Loves techno."
    assert body["birth_date"] == birth_date.isoformat()  # unveraendert - PATCH kennt kein birth_date-Feld


def test_patch_profile_request_ignoriert_unbekanntes_birth_date_feld(api_client, auth_headers_factory):
    """``ProfileUpdateRequest`` hat gar kein ``birth_date``-Feld - selbst wenn
    ein Client es im Body mitschickt, darf es keine Wirkung haben (Pydantic
    ignoriert unbekannte Felder standardmäßig)."""
    headers, _user, _refresh_token = auth_headers_factory()
    today = datetime.date.today()
    birth_date = today.replace(year=today.year - 25)
    api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": birth_date.isoformat()}, headers=headers
    )

    sneaky_date = today.replace(year=today.year - 99).isoformat()
    resp = api_client.patch("/api/v1/me/profile", json={"birth_date": sneaky_date, "bio": "x"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["birth_date"] == birth_date.isoformat()


def test_get_profile_ohne_token_gibt_401(api_client):
    resp = api_client.get("/api/v1/me/profile")
    assert resp.status_code == 401
