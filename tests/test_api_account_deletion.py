"""API-Tests für ``DELETE /api/v1/me`` (Social-Graph-Phase-10, Spec §104)."""

from __future__ import annotations

import uuid

import organizers.storage as organizers_storage
import social.friendships as friendships
from organizers.domain import OrganizerVerificationStatus

_PW = "TestPassw0rd!23"  # conftest.user_factory-Default


def _make_verified_org(api_client, owner_user_id: str, name: str) -> str:
    org = organizers_storage.create_organizer(api_client.db_path, uuid.uuid4().hex, owner_user_id, name)
    organizers_storage.set_verification_status(api_client.db_path, org.id, OrganizerVerificationStatus.VERIFIED)
    return org.id


def test_delete_me_ohne_auth_gibt_401(api_client):
    resp = api_client.request("DELETE", "/api/v1/me", json={"password": _PW})
    assert resp.status_code == 401


def test_delete_me_falsches_passwort_gibt_403_und_loescht_nichts(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="delwrongpw@example.com")
    resp = api_client.request("DELETE", "/api/v1/me", json={"password": "nope-not-it"}, headers=headers)
    assert resp.status_code == 403
    assert api_client.get("/api/v1/me", headers=headers).status_code == 200


def test_delete_me_happy_path_loescht_alles_und_isoliert_andere(api_client, auth_headers_factory):
    a_headers, a, a_refresh = auth_headers_factory(email="deletea@example.com")
    b_headers, b, _ = auth_headers_factory(email="deleteb@example.com")

    # A hostet + veröffentlicht eine Party über einen verifizierten Organizer.
    org_id = _make_verified_org(api_client, a["id"], "Deletion Org A")
    party_id = api_client.post("/api/v1/parties", json={"name": "Deletion Fest A"}, headers=a_headers).json()["id"]
    assert api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
        headers=a_headers,
    ).status_code == 200

    # B folgt A's Organizer, wird zu A's Party eingeladen, A und B sind Freunde.
    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=b_headers).status_code == 200
    assert api_client.post(
        f"/api/v1/parties/{party_id}/invitations", json={"invited_user_email": "deleteb@example.com"}, headers=a_headers
    ).status_code == 201
    friendships.create_friendship(api_client.db_path, uuid.uuid4().hex, a["id"], b["id"])

    # === A löscht den Account ===
    resp = api_client.request("DELETE", "/api/v1/me", json={"password": _PW}, headers=a_headers)
    assert resp.status_code == 204

    # A's Sessions sind tot.
    assert api_client.get("/api/v1/me", headers=a_headers).status_code == 401
    assert api_client.post("/api/v1/auth/refresh", json={"refresh_token": a_refresh}).status_code == 401
    assert api_client.post(
        "/api/v1/auth/login", json={"email": "deletea@example.com", "password": _PW}
    ).status_code == 401
    # E-Mail ist wieder frei.
    assert api_client.post(
        "/api/v1/auth/signup",
        json={"email": "deletea@example.com", "password": _PW, "display_name": "New A"},
    ).status_code == 201

    # B sieht nichts mehr von A.
    assert api_client.get("/api/v1/me/following/organizers", headers=b_headers).json() == []
    assert api_client.get("/api/v1/me/invitations", headers=b_headers).json() == []
    assert api_client.get("/api/v1/search?q=deletion fest a", headers=b_headers).json()["events"] == []
    assert api_client.get("/api/v1/me/friends", headers=b_headers).json() == []

    # B selbst ist unangetastet.
    assert api_client.get("/api/v1/me", headers=b_headers).status_code == 200


def test_delete_me_laesst_eigene_gehostete_party_von_b_unberuehrt(api_client, auth_headers_factory):
    a_headers, _a, _ = auth_headers_factory(email="delisoa@example.com")
    b_headers, b, _ = auth_headers_factory(email="delisob@example.com")
    b_party = api_client.post("/api/v1/parties", json={"name": "B eigene Party"}, headers=b_headers).json()["id"]

    assert api_client.request("DELETE", "/api/v1/me", json={"password": _PW}, headers=a_headers).status_code == 204

    my = api_client.get("/api/v1/me/parties", headers=b_headers).json()
    assert [p["id"] for p in my] == [b_party]
