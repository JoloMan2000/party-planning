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


def _onboard(api_client, headers, years_ago: int = 25) -> None:
    today = datetime.date.today()
    birth_date = today.replace(year=today.year - years_ago)
    resp = api_client.post(
        "/api/v1/me/profile/birth-date-correction", json={"birth_date": birth_date.isoformat()}, headers=headers
    )
    assert resp.status_code == 200, resp.text


def test_patch_profile_setzt_username(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    _onboard(api_client, headers)
    resp = api_client.patch("/api/v1/me/profile", json={"username": "MaxM"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "MaxM"


def test_patch_profile_username_bereits_vergeben_gibt_409(api_client, auth_headers_factory):
    headers_a, _a, _ = auth_headers_factory(email="usernamea@example.com")
    headers_b, _b, _ = auth_headers_factory(email="usernameb@example.com")
    _onboard(api_client, headers_a)
    _onboard(api_client, headers_b)
    assert api_client.patch("/api/v1/me/profile", json={"username": "MaxM"}, headers=headers_a).status_code == 200

    resp = api_client.patch("/api/v1/me/profile", json={"username": "maxm"}, headers=headers_b)
    assert resp.status_code == 409


def test_patch_profile_ungueltiges_username_format_gibt_422(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    _onboard(api_client, headers)
    resp = api_client.patch("/api/v1/me/profile", json={"username": "a"}, headers=headers)
    assert resp.status_code == 422


def test_patch_profile_ohne_username_laesst_bestehenden_unveraendert(api_client, auth_headers_factory):
    headers, _user, _refresh_token = auth_headers_factory()
    _onboard(api_client, headers)
    api_client.patch("/api/v1/me/profile", json={"username": "MaxM"}, headers=headers)
    resp = api_client.patch("/api/v1/me/profile", json={"bio": "Loves techno."}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "MaxM"
