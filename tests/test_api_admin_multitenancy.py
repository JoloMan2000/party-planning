"""Cross-Tenant-Isolations-Tests für die party-gescopten Admin-Router und den
anonymen Gast-Wizard (Multi-Tenant-Pivot Phase 4).

Deckt genau die in der Phase-4-Planung geforderten Szenarien ab: Host A darf
nie Host B's Admin-Daten lesen/schreiben, GUEST-Rolle bekommt 403 auf
Admin-Routen, CO_HOST hat dieselben Rechte wie HOST, unbekannte party_id gibt
404, der Gast-Wizard braucht keinen Token und liefert 404 bei unbekannter
party_id."""

from __future__ import annotations

import accounts.party_storage as party_storage
from accounts.domain import PartyRole, RsvpStatus


def _make_guest_headers(api_client, auth_headers_factory, party_id):
    headers, user, _refresh_token = auth_headers_factory()
    party_storage.upsert_membership(api_client.db_path, party_id, user["id"], PartyRole.GUEST, RsvpStatus.ACCEPTED)
    return headers


def test_host_a_kann_nicht_auf_party_settings_von_host_b_zugreifen(api_client, host_party_factory):
    party_a, headers_a, _user_a = host_party_factory("Party A")
    party_b, _headers_b, _user_b = host_party_factory("Party B")

    resp = api_client.get(f"/api/v1/parties/{party_b}/admin/party-settings", headers=headers_a)
    assert resp.status_code == 403

    resp = api_client.post(
        f"/api/v1/parties/{party_b}/admin/party-settings",
        json={"event_type": "birthday", "party_name": "Hijacked"},
        headers=headers_a,
    )
    assert resp.status_code == 403


def test_host_a_kann_nicht_responses_von_party_b_lesen(api_client, host_party_factory):
    party_a, headers_a, _user_a = host_party_factory("Party A")
    party_b, headers_b, _user_b = host_party_factory("Party B")

    api_client.post(
        f"/api/v1/guest/{party_b}/responses",
        json={
            "name": "Ben",
            "start_time": "19:00",
            "drinks": [],
            "drinks_freetext": "",
            "food": [],
            "food_freetext": "",
            "songs": [],
        },
    )

    resp = api_client.get(f"/api/v1/parties/{party_b}/admin/responses", headers=headers_a)
    assert resp.status_code == 403

    own_resp = api_client.get(f"/api/v1/parties/{party_b}/admin/responses", headers=headers_b)
    assert own_resp.status_code == 200
    assert len(own_resp.json()) == 1


def test_guest_rolle_bekommt_403_auf_admin_routen(api_client, host_party_factory, auth_headers_factory):
    party_id, _headers, _user = host_party_factory()
    guest_headers = _make_guest_headers(api_client, auth_headers_factory, party_id)

    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings", headers=guest_headers)
    assert resp.status_code == 403


def test_co_host_hat_gleiche_rechte_wie_host(api_client, host_party_factory, co_host_headers_factory):
    party_id, host_headers, _user = host_party_factory()
    co_host_headers = co_host_headers_factory(party_id)

    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings", headers=co_host_headers)
    assert resp.status_code == 200

    payload = {
        "event_type": "birthday",
        "party_name": "Von Co-Host gespeichert",
        "party_date": "",
        "party_start_time": "20:00",
        "party_duration_hours": 5.0,
        "party_location": "",
    }
    save_resp = api_client.post(
        f"/api/v1/parties/{party_id}/admin/party-settings", json=payload, headers=co_host_headers
    )
    assert save_resp.status_code == 200

    host_resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings", headers=host_headers)
    assert host_resp.json()["party_name"] == "Von Co-Host gespeichert"


def test_unbekannte_party_id_gibt_404_auf_admin_routen(api_client, host_party_factory):
    _party_id, headers, _user = host_party_factory()
    resp = api_client.get("/api/v1/parties/does-not-exist/admin/party-settings", headers=headers)
    assert resp.status_code == 404


def test_ohne_token_gibt_401_oder_403_auf_admin_routen(api_client, host_party_factory):
    party_id, _headers, _user = host_party_factory()
    resp = api_client.get(f"/api/v1/parties/{party_id}/admin/party-settings")
    assert resp.status_code in (401, 403)


def test_guest_wizard_braucht_keinen_token_und_404_bei_unbekannter_party(api_client, host_party_factory):
    party_id, _headers, _user = host_party_factory()

    ok_resp = api_client.get(f"/api/v1/guest/{party_id}/party-info")
    assert ok_resp.status_code == 200

    unknown_resp = api_client.get("/api/v1/guest/does-not-exist/party-info")
    assert unknown_resp.status_code == 404


def test_freeze_and_reset_loescht_nur_responses_der_ausloesenden_party(api_client, host_party_factory):
    party_a, headers_a, _user_a = host_party_factory("Party A")
    party_b, headers_b, _user_b = host_party_factory("Party B")

    # party_date wird zunächst auf ein Datum in der Vergangenheit gesetzt -
    # das löst noch KEINEN Reset aus (existing party_date war "", siehe
    # maybe_freeze_and_reset_party: geprüft wird das BISHER gespeicherte
    # Datum, nicht das neu übergebene).
    initial_payload = {
        "event_type": "birthday",
        "party_name": "Vergangene Party",
        "party_date": "2019-06-01",
        "party_start_time": "19:00",
        "party_duration_hours": 4.0,
        "party_location": "",
    }
    for party_id, headers in ((party_a, headers_a), (party_b, headers_b)):
        resp = api_client.post(f"/api/v1/parties/{party_id}/admin/party-settings", json=initial_payload, headers=headers)
        assert resp.json()["reset_happened"] is False

    for party_id in (party_a, party_b):
        api_client.post(
            f"/api/v1/guest/{party_id}/responses",
            json={
                "name": "Gast",
                "start_time": "19:00",
                "drinks": [],
                "drinks_freetext": "",
                "food": [],
                "food_freetext": "",
                "songs": [],
            },
        )

    # Jetzt wird ein NEUES Datum für party_a gespeichert - das BISHERIGE
    # Datum (2019-06-01) liegt in der Vergangenheit und Responses liegen vor
    # -> löst den Freeze-and-Reset-Lifecycle für party_a aus.
    new_date_payload = dict(initial_payload, party_date="2020-01-01")
    resp = api_client.post(f"/api/v1/parties/{party_a}/admin/party-settings", json=new_date_payload, headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["reset_happened"] is True

    resp_after_a = api_client.get(f"/api/v1/parties/{party_a}/admin/responses", headers=headers_a)
    assert resp_after_a.json() == []

    resp_after_b = api_client.get(f"/api/v1/parties/{party_b}/admin/responses", headers=headers_b)
    assert len(resp_after_b.json()) == 1
