"""API-Tests für die Following-Domain-Endpunkte
(``/api/v1/organizers/{id}/follow``, ``/api/v1/events/{party_id}/follow``,
``/api/v1/me/following/*``, ``backend/app/routers/follows.py``,
Social-Graph-Phase-5). Backend-only diese Phase, siehe Plan."""

from __future__ import annotations

import uuid

import organizers.storage as organizers_storage
from organizers.domain import OrganizerVerificationStatus


def _make_organizer(api_client, owner_user_id: str, *, verified: bool, name: str = "Boiler Room") -> str:
    """Legt direkt über die Storage-Schicht einen Organizer an (kein
    HTTP-Roundtrip nötig, mirrort ``tests/test_api_discover.py::_verify``)."""
    organizer = organizers_storage.create_organizer(api_client.db_path, uuid.uuid4().hex, owner_user_id, name)
    if verified:
        organizers_storage.set_verification_status(
            api_client.db_path, organizer.id, OrganizerVerificationStatus.VERIFIED
        )
    return organizer.id


def _publish_party(api_client, headers, user_id: str, name: str = "Summer Sound") -> str:
    """Erstellt eine Party und veröffentlicht sie (Publish erfordert
    Mitgliedschaft in einem verifizierten Organizer - identischer Aufbau
    wie ``tests/test_api_discover.py::_publish``)."""
    party_id = api_client.post("/api/v1/parties", json={"name": name}, headers=headers).json()["id"]
    _make_organizer(api_client, user_id, verified=True, name=f"Org for {name}")
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return party_id


# --- Organizer follows -------------------------------------------------


def test_follow_organizer_ohne_auth_gibt_401(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner0@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=True)
    resp = api_client.post(f"/api/v1/organizers/{organizer_id}/follow")
    assert resp.status_code == 401


def test_follow_verifizierten_organizer(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner1@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower1@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=True)

    resp = api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=follower_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["organizer_id"] == organizer_id
    assert body["following"] is True
    assert body["follower_count"] == 1


def test_follow_organizer_ist_idempotent(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner2@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower2@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=True)

    first = api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=follower_headers)
    second = api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=follower_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["follower_count"] == 1


def test_follow_unverifizierten_organizer_gibt_404(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner3@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower3@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=False)

    resp = api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=follower_headers)
    assert resp.status_code == 404


def test_follow_unbekannten_organizer_gibt_404(api_client, auth_headers_factory):
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower4@example.com")
    resp = api_client.post("/api/v1/organizers/unknown-id/follow", headers=follower_headers)
    assert resp.status_code == 404


def test_follow_eigenen_organizer_gibt_422(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner5@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=True)
    resp = api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=owner_headers)
    assert resp.status_code == 422


def test_unfollow_organizer_und_status(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner6@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower6@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=True)
    api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=follower_headers)

    resp = api_client.delete(f"/api/v1/organizers/{organizer_id}/follow", headers=follower_headers)
    assert resp.status_code == 204

    followers = api_client.get(f"/api/v1/organizers/{organizer_id}/followers", headers=follower_headers)
    assert followers.status_code == 200
    assert followers.json()["following"] is False
    assert followers.json()["follower_count"] == 0


def test_unfollow_unbekannten_organizer_ist_no_op_204(api_client, auth_headers_factory):
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower7@example.com")
    resp = api_client.delete("/api/v1/organizers/unknown-id/follow", headers=follower_headers)
    assert resp.status_code == 204


def test_organizer_followers_zaehlt_distinct_users(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner8@example.com")
    a_headers, _a, _ = auth_headers_factory(email="folfollower8a@example.com")
    b_headers, _b, _ = auth_headers_factory(email="folfollower8b@example.com")
    organizer_id = _make_organizer(api_client, owner["id"], verified=True)

    api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=a_headers)
    api_client.post(f"/api/v1/organizers/{organizer_id}/follow", headers=b_headers)

    a_view = api_client.get(f"/api/v1/organizers/{organizer_id}/followers", headers=a_headers).json()
    assert a_view["follower_count"] == 2
    assert a_view["following"] is True

    owner_view = api_client.get(f"/api/v1/organizers/{organizer_id}/followers", headers=owner_headers).json()
    assert owner_view["follower_count"] == 2
    assert owner_view["following"] is False


def test_organizer_followers_unbekannt_gibt_404(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="folfollower9@example.com")
    resp = api_client.get("/api/v1/organizers/unknown-id/followers", headers=headers)
    assert resp.status_code == 404


def test_me_following_organizers_neueste_zuerst_ohne_status_filter(api_client, auth_headers_factory):
    owner_headers, owner, _ = auth_headers_factory(email="folorgowner10@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="folfollower10@example.com")
    org_a = _make_organizer(api_client, owner["id"], verified=True, name="Org A")
    org_b = _make_organizer(api_client, owner["id"], verified=True, name="Org B")

    api_client.post(f"/api/v1/organizers/{org_a}/follow", headers=follower_headers)
    api_client.post(f"/api/v1/organizers/{org_b}/follow", headers=follower_headers)

    # org_a verliert nachträglich sein Badge - bleibt trotzdem in der Liste.
    organizers_storage.set_verification_status(api_client.db_path, org_a, OrganizerVerificationStatus.UNVERIFIED)

    resp = api_client.get("/api/v1/me/following/organizers", headers=follower_headers)
    assert resp.status_code == 200
    ids = [o["id"] for o in resp.json()]
    assert ids == [org_b, org_a]


# --- Event follows ---------------------------------------------------


def test_follow_veroeffentlichtes_event(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="folhost1@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower1@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"])

    resp = api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["party_id"] == party_id
    assert body["following"] is True
    assert body["follower_count"] == 1


def test_follow_unveroeffentlichte_party_gibt_404(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="folhost2@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower2@example.com")
    party_id = api_client.post("/api/v1/parties", json={"name": "Private"}, headers=host_headers).json()["id"]

    resp = api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    assert resp.status_code == 404


def test_follow_unbekannte_party_gibt_404(api_client, auth_headers_factory):
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower3@example.com")
    resp = api_client.post("/api/v1/events/unknown-party/follow", headers=follower_headers)
    assert resp.status_code == 404


def test_follow_eigenes_event_gibt_422(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="folhost4@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"])
    resp = api_client.post(f"/api/v1/events/{party_id}/follow", headers=host_headers)
    assert resp.status_code == 422


def test_follow_event_ist_idempotent(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="folhost5@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower5@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"])

    first = api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    second = api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["follower_count"] == 1


def test_unfollow_event_ist_no_op_204(api_client, auth_headers_factory):
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower6@example.com")
    resp = api_client.delete("/api/v1/events/unknown-party/follow", headers=follower_headers)
    assert resp.status_code == 204


def test_me_following_events_blendet_unveroeffentlichte_aus_ohne_zu_loeschen(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="folhost7@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower7@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"], name="Followed Fest")

    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    listed = api_client.get("/api/v1/me/following/events", headers=follower_headers).json()
    assert [e["party_id"] for e in listed] == [party_id]
    assert listed[0]["name"] == "Followed Fest"
    assert listed[0]["event_type"] == "club_event"

    # Unpublish -> aus der Liste raus, aber Follow-Zeile bleibt.
    assert api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=host_headers).status_code == 204
    assert api_client.get("/api/v1/me/following/events", headers=follower_headers).json() == []

    # Re-publish -> wieder da (Zeile war nie weg).
    assert (
        api_client.post(
            f"/api/v1/parties/{party_id}/publish",
            json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
            headers=host_headers,
        ).status_code
        == 200
    )
    relisted = api_client.get("/api/v1/me/following/events", headers=follower_headers).json()
    assert [e["party_id"] for e in relisted] == [party_id]


def test_event_followers_endpoint(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="folhost8@example.com")
    follower_headers, _follower, _ = auth_headers_factory(email="foleventfollower8@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"])
    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)

    follower_view = api_client.get(f"/api/v1/events/{party_id}/followers", headers=follower_headers).json()
    assert follower_view["follower_count"] == 1
    assert follower_view["following"] is True

    host_view = api_client.get(f"/api/v1/events/{party_id}/followers", headers=host_headers).json()
    assert host_view["follower_count"] == 1
    assert host_view["following"] is False


def test_event_followers_unbekannt_gibt_404(api_client, auth_headers_factory):
    headers, _u, _ = auth_headers_factory(email="foleventfollower9@example.com")
    resp = api_client.get("/api/v1/events/unknown-party/followers", headers=headers)
    assert resp.status_code == 404


# --- Social-Graph-Phase-9: block cascade + block-gate on follow -------


def test_follow_organizer_von_geblocktem_owner_gibt_403(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="p9blkorg_me@example.com")
    owner_headers, owner, _ = auth_headers_factory(email="p9blkorg_owner@example.com")
    org_id = _make_organizer(api_client, owner["id"], verified=True, name="Blocked Owner Org")
    assert api_client.post(f"/api/v1/users/{owner['id']}/block", headers=me_headers).status_code == 200

    resp = api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=me_headers)
    assert resp.status_code == 403


def test_follow_event_von_geblocktem_host_gibt_403(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="p9blkevt_me@example.com")
    host_headers, host, _ = auth_headers_factory(email="p9blkevt_host@example.com")
    party_id = _publish_party(api_client, host_headers, host["id"], name="Blocked Host Party")
    assert api_client.post(f"/api/v1/users/{host['id']}/block", headers=me_headers).status_code == 200

    resp = api_client.post(f"/api/v1/events/{party_id}/follow", headers=me_headers)
    assert resp.status_code == 403


def test_block_entfernt_organizer_und_event_follow(api_client, auth_headers_factory):
    me_headers, _me, _ = auth_headers_factory(email="p9casc_me@example.com")
    b_headers, b, _ = auth_headers_factory(email="p9casc_b@example.com")
    org_id = _make_organizer(api_client, b["id"], verified=True, name="Cascade Org")
    party_id = _publish_party(api_client, b_headers, b["id"], name="Cascade Party")

    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=me_headers).status_code == 200
    assert api_client.post(f"/api/v1/events/{party_id}/follow", headers=me_headers).status_code == 200
    assert api_client.get(f"/api/v1/organizers/{org_id}/followers", headers=me_headers).json()["follower_count"] == 1

    assert api_client.post(f"/api/v1/users/{b['id']}/block", headers=me_headers).status_code == 200

    assert api_client.get("/api/v1/me/following/organizers", headers=me_headers).json() == []
    assert api_client.get("/api/v1/me/following/events", headers=me_headers).json() == []
    assert api_client.get(f"/api/v1/organizers/{org_id}/followers", headers=me_headers).json()["follower_count"] == 0
