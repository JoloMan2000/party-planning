"""API-Tests für das Discover-Events-MVP (``GET /api/v1/discover/deck``,
``POST /api/v1/discover/{party_id}/action``, sowie die Publish/Cover-Image-
Endpoints in ``parties.py``)."""

from __future__ import annotations

import io

from PIL import Image

import accounts.user_storage as user_storage


def _make_party(api_client, headers, name: str = "P") -> str:
    return api_client.post("/api/v1/parties", json={"name": name}, headers=headers).json()["id"]


def _verify(api_client, user_id: str) -> None:
    """Setzt ``is_verified`` direkt über die Storage-Schicht (kein HTTP-
    Admin-Roundtrip nötig, mirroring ``conftest.py::co_host_headers_factory``'s
    Direkt-Storage-Setup-Konvention) - Publish erfordert seit der Organizer-
    Verification einen verifizierten Host."""
    user_storage.set_user_verified(api_client.db_path, user_id, True)


def _publish(
    api_client, headers, party_id: str, event_type: str = "club_event", max_guests: int = 0
) -> None:
    me = api_client.get("/api/v1/me", headers=headers)
    _verify(api_client, me.json()["id"])
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": event_type, "interest_tags": [], "max_guests": max_guests},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buf, format="PNG")
    return buf.getvalue()


def test_deck_ohne_auth_gibt_401(api_client):
    resp = api_client.get("/api/v1/discover/deck")
    assert resp.status_code == 401


def test_deck_zeigt_veroeffentlichte_party_eines_anderen_hosts(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="deckhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="deckguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.get("/api/v1/discover/deck", headers=guest_headers)
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    assert any(c["party_id"] == party_id for c in cards)


def test_deck_schliesst_eigene_party_aus(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="ownparty@example.com")
    party_id = _make_party(api_client, headers)
    _publish(api_client, headers, party_id)

    resp = api_client.get("/api/v1/discover/deck", headers=headers)
    cards = resp.json()["cards"]
    assert all(c["party_id"] != party_id for c in cards)


def test_deck_schliesst_unveroeffentlichte_party_aus(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="unpubhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="unpubguest@example.com")
    party_id = _make_party(api_client, host_headers)

    resp = api_client.get("/api/v1/discover/deck", headers=guest_headers)
    cards = resp.json()["cards"]
    assert all(c["party_id"] != party_id for c in cards)


def test_going_joint_sofort_als_guest(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="goinghost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="goingguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["membership_role"] == "guest"
    assert body["membership_rsvp_status"] == "accepted"

    guests_resp = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers)
    assert any(g["user_id"] == guest["id"] for g in guests_resp.json()["guests"])


def test_maybe_joint_als_tentative(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="maybehost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="maybeguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "maybe"}, headers=guest_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["membership_rsvp_status"] == "tentative"


def test_not_interested_erzeugt_keine_mitgliedschaft(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="notinthost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="notintguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.post(
        f"/api/v1/discover/{party_id}/action", json={"action": "not_interested"}, headers=guest_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["membership_role"] is None
    assert body["membership_rsvp_status"] is None


def test_geswipte_party_verschwindet_aus_folgendem_deck(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="vanishhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="vanishguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "not_interested"}, headers=guest_headers)

    resp = api_client.get("/api/v1/discover/deck", headers=guest_headers)
    cards = resp.json()["cards"]
    assert all(c["party_id"] != party_id for c in cards)


def test_action_auf_unveroeffentlichte_party_gibt_404(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="unpubactionhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="unpubactionguest@example.com")
    party_id = _make_party(api_client, host_headers)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest_headers)
    assert resp.status_code == 404


def test_action_auf_eigene_party_gibt_403(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="ownactionhost@example.com")
    party_id = _make_party(api_client, headers)
    _publish(api_client, headers, party_id)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=headers)
    assert resp.status_code == 403


def test_action_ungueltig_gibt_422(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="invalidactionhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="invalidactionguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "nonsense"}, headers=guest_headers)
    assert resp.status_code == 422


def test_publish_setzt_felder_auf_party_public(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="publishfieldshost@example.com")
    party_id = _make_party(api_client, headers)
    _verify(api_client, user["id"])
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "interest_tags": ["techno"], "max_guests": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is True
    assert body["event_type"] == "club_event"
    assert body["interest_tags"] == ["techno"]
    assert body["max_guests"] == 5
    assert body["host_is_verified"] is True


def test_publish_negative_max_guests_gibt_422(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="negativemaxguests@example.com")
    party_id = _make_party(api_client, headers)
    _verify(api_client, user["id"])
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "max_guests": -1},
        headers=headers,
    )
    assert resp.status_code == 422


def test_publish_als_unverifizierter_host_gibt_403(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="unverifiedhost@example.com")
    party_id = _make_party(api_client, headers)
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish", json={"event_type": "club_event"}, headers=headers
    )
    assert resp.status_code == 403


def test_publish_nach_admin_verifizierung_klappt(api_client, auth_headers_factory, monkeypatch):
    from backend.app.core.config import settings

    headers, user, _ = auth_headers_factory(email="toverify@example.com")
    party_id = _make_party(api_client, headers)

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish", json={"event_type": "club_event"}, headers=headers
    )
    assert resp.status_code == 403

    admin_headers, _admin, _ = auth_headers_factory(email="theadmin@example.com")
    monkeypatch.setattr(settings, "admin_emails", "theadmin@example.com")
    verify_resp = api_client.post(f"/api/v1/admin/users/{user['id']}/verify", headers=admin_headers)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish", json={"event_type": "club_event"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["host_is_verified"] is True


def test_host_is_verified_auf_party_und_me_parties(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="hostverifiedflag@example.com")
    party_id = _make_party(api_client, headers)

    get_resp = api_client.get(f"/api/v1/parties/{party_id}", headers=headers)
    assert get_resp.json()["host_is_verified"] is False
    my_parties_resp = api_client.get("/api/v1/me/parties", headers=headers)
    assert next(p for p in my_parties_resp.json() if p["id"] == party_id)["host_is_verified"] is False

    _verify(api_client, user["id"])

    get_resp = api_client.get(f"/api/v1/parties/{party_id}", headers=headers)
    assert get_resp.json()["host_is_verified"] is True
    my_parties_resp = api_client.get("/api/v1/me/parties", headers=headers)
    assert next(p for p in my_parties_resp.json() if p["id"] == party_id)["host_is_verified"] is True


def test_unpublish_entfernt_publikation(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="unpublishhost@example.com")
    party_id = _make_party(api_client, headers)
    _publish(api_client, headers, party_id)

    resp = api_client.delete(f"/api/v1/parties/{party_id}/publish", headers=headers)
    assert resp.status_code == 204

    get_resp = api_client.get(f"/api/v1/parties/{party_id}", headers=headers)
    assert get_resp.json()["is_published"] is False


def test_publish_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="publishguesthost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="publishguestguest@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "publishguestguest@example.com"},
        headers=host_headers,
    )
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish", json={"event_type": "club_event"}, headers=guest_headers
    )
    assert resp.status_code == 403


def test_cover_image_upload_und_ungueltiges_bild(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="coverimagehost@example.com")
    party_id = _make_party(api_client, headers)

    resp = api_client.post(
        f"/api/v1/parties/{party_id}/cover-image",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["cover_image"] == f"party_images/{party_id}.jpg"

    invalid_resp = api_client.post(
        f"/api/v1/parties/{party_id}/cover-image",
        files={"file": ("not-an-image.txt", b"not an image", "text/plain")},
        headers=headers,
    )
    assert invalid_resp.status_code == 400


def test_cover_image_als_guest_gibt_403(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="coverimageguesthost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="coverimageguestguest@example.com")
    party_id = _make_party(api_client, host_headers)
    api_client.post(
        f"/api/v1/parties/{party_id}/invitations",
        json={"invited_user_email": "coverimageguestguest@example.com"},
        headers=host_headers,
    )
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/cover-image",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
        headers=guest_headers,
    )
    assert resp.status_code == 403


def test_volle_party_verschwindet_aus_dem_deck(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="capacityhost@example.com")
    guest1_headers, _guest1, _ = auth_headers_factory(email="capacityguest1@example.com")
    guest2_headers, _guest2, _ = auth_headers_factory(email="capacityguest2@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id, max_guests=1)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest1_headers)
    assert resp.status_code == 200

    deck_resp = api_client.get("/api/v1/discover/deck", headers=guest2_headers)
    cards = deck_resp.json()["cards"]
    assert all(c["party_id"] != party_id for c in cards)


def test_going_auf_volle_party_gibt_409(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="capacitygoinghost@example.com")
    guest1_headers, _guest1, _ = auth_headers_factory(email="capacitygoingguest1@example.com")
    guest2_headers, _guest2, _ = auth_headers_factory(email="capacitygoingguest2@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id, max_guests=1)

    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest1_headers)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest2_headers)
    assert resp.status_code == 409


def test_maybe_auf_volle_party_gibt_409(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="capacitymaybehost@example.com")
    guest1_headers, _guest1, _ = auth_headers_factory(email="capacitymaybeguest1@example.com")
    guest2_headers, _guest2, _ = auth_headers_factory(email="capacitymaybeguest2@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id, max_guests=1)

    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest1_headers)

    resp = api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "maybe"}, headers=guest2_headers)
    assert resp.status_code == 409


def test_not_interested_auf_volle_party_bleibt_erlaubt(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="capacitynotinthost@example.com")
    guest1_headers, _guest1, _ = auth_headers_factory(email="capacitynotintguest1@example.com")
    guest2_headers, _guest2, _ = auth_headers_factory(email="capacitynotintguest2@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id, max_guests=1)

    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest1_headers)

    resp = api_client.post(
        f"/api/v1/discover/{party_id}/action", json={"action": "not_interested"}, headers=guest2_headers
    )
    assert resp.status_code == 200


def test_unbegrenzte_party_bleibt_im_deck_mit_gaesten(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="unlimitedhost@example.com")
    guest1_headers, _guest1, _ = auth_headers_factory(email="unlimitedguest1@example.com")
    guest2_headers, _guest2, _ = auth_headers_factory(email="unlimitedguest2@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id, max_guests=0)

    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest1_headers)

    deck_resp = api_client.get("/api/v1/discover/deck", headers=guest2_headers)
    cards = deck_resp.json()["cards"]
    assert any(c["party_id"] == party_id for c in cards)


def test_undo_going_entfernt_mitgliedschaft_und_gibt_party_frei(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undogoinghost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="undogoingguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)
    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest_headers)

    resp = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    assert resp.status_code == 204

    guests_resp = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers)
    assert all(g["user_id"] != guest["id"] for g in guests_resp.json()["guests"])

    deck_resp = api_client.get("/api/v1/discover/deck", headers=guest_headers)
    cards = deck_resp.json()["cards"]
    assert any(c["party_id"] == party_id for c in cards)


def test_undo_maybe_entfernt_mitgliedschaft(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undomaybehost@example.com")
    guest_headers, guest, _ = auth_headers_factory(email="undomaybeguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)
    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "maybe"}, headers=guest_headers)

    resp = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    assert resp.status_code == 204

    guests_resp = api_client.get(f"/api/v1/parties/{party_id}/guests", headers=host_headers)
    assert all(g["user_id"] != guest["id"] for g in guests_resp.json()["guests"])


def test_undo_nach_not_interested_gibt_404(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undonotinthost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="undonotintguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)
    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "not_interested"}, headers=guest_headers)

    resp = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    assert resp.status_code == 404


def test_undo_ohne_vorherigen_swipe_gibt_404(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undononeverhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="undoneverguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    assert resp.status_code == 404


def test_undo_zweimal_hintereinander_zweiter_aufruf_gibt_404(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undotwicehost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="undotwiceguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)
    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest_headers)

    first = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    assert first.status_code == 204
    second = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    assert second.status_code == 404


def test_undo_ohne_auth_gibt_401(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undonoauthhost@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    resp = api_client.delete(f"/api/v1/discover/{party_id}/action")
    assert resp.status_code == 401


def test_undo_gibt_slot_auf_voller_party_frei(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="undofreeshost@example.com")
    guest1_headers, _guest1, _ = auth_headers_factory(email="undofreesguest1@example.com")
    guest2_headers, _guest2, _ = auth_headers_factory(email="undofreesguest2@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id, max_guests=1)
    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest1_headers)

    blocked = api_client.post(
        f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest2_headers
    )
    assert blocked.status_code == 409

    undo_resp = api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest1_headers)
    assert undo_resp.status_code == 204

    allowed = api_client.post(
        f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest2_headers
    )
    assert allowed.status_code == 200


def test_my_discover_action_auf_party_und_me_parties(api_client, auth_headers_factory):
    host_headers, _host, _ = auth_headers_factory(email="mydiscoveractionhost@example.com")
    guest_headers, _guest, _ = auth_headers_factory(email="mydiscoveractionguest@example.com")
    party_id = _make_party(api_client, host_headers)
    _publish(api_client, host_headers, party_id)

    host_get_resp = api_client.get(f"/api/v1/parties/{party_id}", headers=host_headers)
    assert host_get_resp.json()["my_discover_action"] is None

    api_client.post(f"/api/v1/discover/{party_id}/action", json={"action": "going"}, headers=guest_headers)

    guest_get_resp = api_client.get(f"/api/v1/parties/{party_id}", headers=guest_headers)
    assert guest_get_resp.json()["my_discover_action"] == "going"
    my_parties_resp = api_client.get("/api/v1/me/parties", headers=guest_headers)
    assert next(p for p in my_parties_resp.json() if p["id"] == party_id)["my_discover_action"] == "going"

    api_client.delete(f"/api/v1/discover/{party_id}/action", headers=guest_headers)
    # Membership ist weg -> guest hat keinen Zugriff mehr auf /parties/{id}
    after_undo_resp = api_client.get(f"/api/v1/parties/{party_id}", headers=guest_headers)
    assert after_undo_resp.status_code == 403
