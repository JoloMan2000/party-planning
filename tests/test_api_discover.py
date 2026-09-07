"""API-Tests für das Discover-Events-MVP (``GET /api/v1/discover/deck``,
``POST /api/v1/discover/{party_id}/action``, sowie die Publish/Cover-Image-
Endpoints in ``parties.py``)."""

from __future__ import annotations

import io

from PIL import Image


def _make_party(api_client, headers, name: str = "P") -> str:
    return api_client.post("/api/v1/parties", json={"name": name}, headers=headers).json()["id"]


def _publish(api_client, headers, party_id: str, event_type: str = "club_event") -> None:
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish", json={"event_type": event_type, "interest_tags": []}, headers=headers
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
    headers, _user, _ = auth_headers_factory(email="publishfieldshost@example.com")
    party_id = _make_party(api_client, headers)
    resp = api_client.post(
        f"/api/v1/parties/{party_id}/publish",
        json={"event_type": "club_event", "interest_tags": ["techno"]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is True
    assert body["event_type"] == "club_event"
    assert body["interest_tags"] == ["techno"]


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
