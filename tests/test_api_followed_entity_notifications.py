"""API-Tests für die Followed-Entity-Update-Notifications
(Social-Graph-Phase-8, Spec §63-65/§72/§90-91/§106/§109/§144)."""

from __future__ import annotations

import uuid

import organizers.storage as organizers_storage
from organizers.domain import OrganizerVerificationStatus


def _make_verified_org(api_client, owner_user_id: str, name: str = "Boiler Room") -> str:
    org = organizers_storage.create_organizer(api_client.db_path, uuid.uuid4().hex, owner_user_id, name)
    organizers_storage.set_verification_status(api_client.db_path, org.id, OrganizerVerificationStatus.VERIFIED)
    return org.id


def _create_and_publish(api_client, host_headers, name: str = "Fest") -> str:
    """Host muss VORHER schon Mitglied eines verifizierten Organizers sein."""
    party_id = api_client.post("/api/v1/parties", json={"name": name}, headers=host_headers).json()["id"]
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "interest_tags": [], "max_guests": 0},
        headers=host_headers,
    )
    assert resp.status_code == 200, resp.text
    return party_id


def _kinds(api_client, headers) -> list[str]:
    return [n["kind"] for n in api_client.get("/api/v1/me/notifications", headers=headers).json()]


def _set_notif(api_client, headers, **kwargs) -> None:
    resp = api_client.put("/api/v1/me/notification-settings", json=kwargs, headers=headers)
    assert resp.status_code == 200, resp.text


# --- New publication -> organizer followers ----------------------------


def test_neue_publikation_benachrichtigt_organizer_follower(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host1@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower1@example.com")
    org_id = _make_verified_org(api_client, host["id"], name="Boiler Room One")
    assert api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=follower_headers).status_code == 200

    party_id = _create_and_publish(api_client, host_headers, name="First Fest")

    notes = api_client.get("/api/v1/me/notifications", headers=follower_headers).json()
    new_event = [n for n in notes if n["kind"] == "organizer_new_event"]
    assert len(new_event) == 1
    assert new_event[0]["party_id"] == party_id
    assert "Boiler Room One" in new_event[0]["message"]
    # Der Host selbst bekommt nichts.
    assert "organizer_new_event" not in _kinds(api_client, host_headers)


def test_settings_gate_organizer_updates_off_unterdrueckt(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host2@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower2@example.com")
    org_id = _make_verified_org(api_client, host["id"], name="Gate Room")
    api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=follower_headers)
    _set_notif(api_client, follower_headers, organizer_updates=False)

    _create_and_publish(api_client, host_headers, name="Gated Fest")

    assert "organizer_new_event" not in _kinds(api_client, follower_headers)
    # Follow + Boost bleiben intakt.
    following = api_client.get("/api/v1/me/following/organizers", headers=follower_headers).json()
    assert [o["id"] for o in following] == [org_id]


def test_republish_erzeugt_keine_zweite_notification(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host3@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower3@example.com")
    org_id = _make_verified_org(api_client, host["id"], name="Repub Room")
    api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=follower_headers)

    party_id = _create_and_publish(api_client, host_headers, name="Repub Fest")
    # Re-Publish (z.B. um Tags zu ändern).
    api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "warehouse", "interest_tags": ["techno"], "max_guests": 0},
        headers=host_headers,
    )
    assert _kinds(api_client, follower_headers).count("organizer_new_event") == 1


def test_cross_org_dedupe_ein_follower_eine_notification(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host4@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower4@example.com")
    org_a = _make_verified_org(api_client, host["id"], name="Cross Org A")
    org_b = _make_verified_org(api_client, host["id"], name="Cross Org B")
    api_client.post(f"/api/v1/organizers/{org_a}/follow", headers=follower_headers)
    api_client.post(f"/api/v1/organizers/{org_b}/follow", headers=follower_headers)

    _create_and_publish(api_client, host_headers, name="Cross Fest")

    assert _kinds(api_client, follower_headers).count("organizer_new_event") == 1


# --- Event update / cancellation -> event followers -------------------


def test_datums_aenderung_benachrichtigt_event_follower(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host5@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower5@example.com")
    _make_verified_org(api_client, host["id"], name="EvtUpd Org 5")
    party_id = _create_and_publish(api_client, host_headers, name="Update Fest")
    assert api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers).status_code == 200

    resp = api_client.patch(
        f"/api/v1/parties/{party_id}", json={"starts_at": "2027-06-01T20:00:00"}, headers=host_headers
    )
    assert resp.status_code == 200

    notes = [n for n in api_client.get("/api/v1/me/notifications", headers=follower_headers).json()
             if n["kind"] == "event_updated"]
    assert len(notes) == 1
    assert "date" in notes[0]["message"]
    # Der bearbeitende Host bekommt nichts.
    assert "event_updated" not in _kinds(api_client, host_headers)


def test_dedupe_fenster_unterdrueckt_zweite_aenderung(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host6@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower6@example.com")
    _make_verified_org(api_client, host["id"], name="Dedupe Org 6")
    party_id = _create_and_publish(api_client, host_headers, name="Dedupe Fest")
    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)

    api_client.patch(f"/api/v1/parties/{party_id}", json={"starts_at": "2027-06-01T20:00:00"}, headers=host_headers)
    api_client.patch(f"/api/v1/parties/{party_id}", json={"location": "New Venue"}, headers=host_headers)

    assert _kinds(api_client, follower_headers).count("event_updated") == 1


def test_settings_gate_followed_event_updates_off(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host7@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower7@example.com")
    _make_verified_org(api_client, host["id"], name="EvtGate Org 7")
    party_id = _create_and_publish(api_client, host_headers, name="EvtGate Fest")
    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    _set_notif(api_client, follower_headers, followed_event_updates=False)

    api_client.patch(f"/api/v1/parties/{party_id}", json={"starts_at": "2027-06-01T20:00:00"}, headers=host_headers)
    assert "event_updated" not in _kinds(api_client, follower_headers)


def test_absage_benachrichtigt_event_follower_und_ist_transition_only(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host8@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower8@example.com")
    _make_verified_org(api_client, host["id"], name="Cancel Org 8")
    party_id = _create_and_publish(api_client, host_headers, name="Cancel Fest")
    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)

    assert api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=host_headers).status_code == 204
    notes = [n for n in api_client.get("/api/v1/me/notifications", headers=follower_headers).json()
             if n["kind"] == "event_cancelled"]
    assert len(notes) == 1
    assert "cancelled" in notes[0]["message"].lower()

    # Zweites DELETE -> No-Op, keine weitere Notification.
    api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=host_headers)
    assert _kinds(api_client, follower_headers).count("event_cancelled") == 1


def test_unveroeffentlichtes_event_edit_erzeugt_kein_event_updated(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_host9@example.com")
    follower_headers, _f, _ = auth_headers_factory(email="fen_follower9@example.com")
    _make_verified_org(api_client, host["id"], name="Unpub Org 9")
    party_id = _create_and_publish(api_client, host_headers, name="Unpub Fest")
    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=host_headers)

    api_client.patch(f"/api/v1/parties/{party_id}", json={"starts_at": "2028-01-01T20:00:00"}, headers=host_headers)
    assert "event_updated" not in _kinds(api_client, follower_headers)


# --- Robustness: block-aware suppression ------------------------------


def test_geblockter_follower_bekommt_keine_organizer_new_event(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_blk_host1@example.com")
    follower_headers, follower, _ = auth_headers_factory(email="fen_blk_follower1@example.com")
    org_id = _make_verified_org(api_client, host["id"], name="Blk Org 1")
    api_client.post(f"/api/v1/organizers/{org_id}/follow", headers=follower_headers)
    # Follower blockt den Host.
    assert api_client.post(f"/api/v1/users/{host['id']}/block", headers=follower_headers).status_code == 200

    _create_and_publish(api_client, host_headers, name="Blk Fest 1")
    assert "organizer_new_event" not in _kinds(api_client, follower_headers)


def test_geblockter_follower_bekommt_keine_event_updates(api_client, auth_headers_factory):
    host_headers, host, _ = auth_headers_factory(email="fen_blk_host2@example.com")
    follower_headers, follower, _ = auth_headers_factory(email="fen_blk_follower2@example.com")
    _make_verified_org(api_client, host["id"], name="Blk Org 2")
    party_id = _create_and_publish(api_client, host_headers, name="Blk Fest 2")
    api_client.post(f"/api/v1/events/{party_id}/follow", headers=follower_headers)
    assert api_client.post(f"/api/v1/users/{host['id']}/block", headers=follower_headers).status_code == 200

    api_client.patch(f"/api/v1/parties/{party_id}", json={"starts_at": "2027-06-01T20:00:00"}, headers=host_headers)
    assert "event_updated" not in _kinds(api_client, follower_headers)

    assert api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=host_headers).status_code == 204
    assert "event_cancelled" not in _kinds(api_client, follower_headers)
