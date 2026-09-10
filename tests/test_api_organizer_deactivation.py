"""API-Tests für Organizer-Deaktivierung (Social-Graph-Phase-9, Spec §105).

Prüft, dass ein auf ``suspended`` gesetzter Organizer funktional
deaktiviert ist - die eigentlichen Effekte sind schon in Phasen 4/6/8
implementiert (Publish-Gate / Suche / Notifications verlangen alle
``verified``), hier nur die End-to-End-Absicherung."""

from __future__ import annotations

import uuid

import organizers.storage as organizers_storage
from organizers.domain import OrganizerVerificationStatus


def _make_verified_org(api_client, owner_user_id: str, name: str) -> str:
    org = organizers_storage.create_organizer(api_client.db_path, uuid.uuid4().hex, owner_user_id, name)
    organizers_storage.set_verification_status(api_client.db_path, org.id, OrganizerVerificationStatus.VERIFIED)
    return org.id


def _suspend(api_client, organizer_id: str) -> None:
    organizers_storage.set_verification_status(api_client.db_path, organizer_id, OrganizerVerificationStatus.SUSPENDED)


def test_suspendierter_organizer_faellt_aus_der_suche(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="deact_search_me@example.com")
    _owner_headers, owner, _ = auth_headers_factory(email="deact_search_owner@example.com")
    org_id = _make_verified_org(api_client, owner["id"], "Deactivation Search Org")

    hits = api_client.get("/api/v1/search?q=deactivation search", headers=me_headers).json()["organizers"]
    assert [o["organizer_id"] for o in hits] == [org_id]

    _suspend(api_client, org_id)
    assert api_client.get("/api/v1/search?q=deactivation search", headers=me_headers).json()["organizers"] == []


def test_suspendierter_organizer_bleibt_in_der_following_liste_mit_status(api_client, auth_headers_factory):
    follower_headers, _f, _ = auth_headers_factory(email="deact_follow_me@example.com")
    _owner_headers, owner, _ = auth_headers_factory(email="deact_follow_owner@example.com")
    org_id = _make_verified_org(api_client, owner["id"], "Deactivation Follow Org")
    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=follower_headers).status_code == 200

    _suspend(api_client, org_id)

    listed = api_client.get("/api/v1/me/following/organizers", headers=follower_headers).json()
    assert [o["id"] for o in listed] == [org_id]
    assert listed[0]["verification_status"] == "suspended"


def test_member_eines_suspendierten_organizers_kann_nicht_publishen(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="deact_pub_host@example.com")
    org_id = _make_verified_org(api_client, host["id"], "Deactivation Publish Org")

    p1 = api_client.post("/api/v1/parties", json={"name": "Before Suspend"}, headers=host_headers).json()["id"]
    assert api_client.post(
        f"/api/v1/parties/{p1}/publish",
        json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
        headers=host_headers,
    ).status_code == 200

    _suspend(api_client, org_id)

    p2 = api_client.post("/api/v1/parties", json={"name": "After Suspend"}, headers=host_headers).json()["id"]
    resp = api_client.post(
        f"/api/v1/parties/{p2}/publish",
        json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
        headers=host_headers,
    )
    assert resp.status_code == 403
