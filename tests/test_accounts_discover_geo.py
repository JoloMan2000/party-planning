"""Tests für die Geo-Eligibility-Erweiterung von
``accounts/discover_storage.py::list_candidate_publications``/``get_discover_deck``
(Spec §40-51, §123-124) - Radius-Hard-Filter, Major-Event-Override, und die
kritische Rückwärtskompatibilitätsregel: fehlen auf einer Seite Koordinaten,
bleibt das Verhalten exakt wie vor der Geo Platform (nur das weiche
``_city_fit``-Signal)."""

from __future__ import annotations

import uuid

import pytest

import accounts.discover_storage as discover_storage
import accounts.discovery_storage as discovery_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import geo.storage as geo_storage
from accounts.domain import UserDiscoveryPreferences
from geo.domain import GeoAddress, GeoPoint

HAMBURG = GeoPoint(latitude=53.5511, longitude=9.9937)
# ~22km von Hamburg entfernt (Buxtehude-artige Distanz).
NEARBY_22KM = GeoPoint(latitude=53.5511, longitude=10.30)
# ~80km von Hamburg entfernt - ausserhalb eines 20km-Radius, aber innerhalb
# des erweiterten MAJOR_EVENT_RADIUS_KM (100km).
WITHIN_MAJOR_EVENT_RADIUS_80KM = GeoPoint(latitude=53.5511, longitude=11.20)
# Weit entfernt (Berlin, ~255km) - ausserhalb auch des Major-Event-Radius.
BERLIN = GeoPoint(latitude=52.5200, longitude=13.4050)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "discover_geo_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    discover_storage.init_discover_storage(path)
    discovery_storage.init_discovery_storage(path)
    return path


@pytest.fixture()
def host(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "geohost@example.com", "hash", "Host")


@pytest.fixture()
def guest(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "geoguest@example.com", "hash", "Guest")


def _set_guest_prefs(db_path, guest_id, *, radius_km=25.0, point=HAMBURG, allow_major_events=False):
    discovery_storage.upsert_discovery_preferences(
        db_path, guest_id,
        UserDiscoveryPreferences(
            user_id=guest_id, discovery_radius_km=radius_km,
            allow_major_events_outside_radius=allow_major_events,
            discovery_lat=point.latitude, discovery_lon=point.longitude,
        ),
    )


def _publish_party_with_location(db_path, host_id, point: GeoPoint, *, name="Party", is_major_event=False):
    party = party_storage.create_party(db_path, uuid.uuid4().hex, host_id, name)
    discover_storage.publish_party(db_path, party.id, event_type="club_event", is_major_event=is_major_event)
    geo_storage.upsert_party_location(
        db_path, party.id, point=point, address=GeoAddress(formatted_address="Somewhere"),
    )
    return party


def test_kandidat_ausserhalb_des_radius_wird_gefiltert(db_path, host, guest):
    _set_guest_prefs(db_path, guest.id, radius_km=20.0, point=HAMBURG)
    party = _publish_party_with_location(db_path, host.id, NEARBY_22KM)

    candidates = discover_storage.list_candidate_publications(
        db_path, guest.id, user_point=HAMBURG, user_radius_km=20.0
    )
    assert all(p.id != party.id for p, _pe in candidates)


def test_kandidat_innerhalb_des_radius_bleibt_drin(db_path, host, guest):
    party = _publish_party_with_location(db_path, host.id, NEARBY_22KM)

    candidates = discover_storage.list_candidate_publications(
        db_path, guest.id, user_point=HAMBURG, user_radius_km=30.0
    )
    assert any(p.id == party.id for p, _pe in candidates)


def test_major_event_override_bei_deaktiviertem_flag_bleibt_gefiltert(db_path, host, guest):
    party = _publish_party_with_location(db_path, host.id, BERLIN, is_major_event=True)

    candidates = discover_storage.list_candidate_publications(
        db_path, guest.id, user_point=HAMBURG, user_radius_km=20.0, allow_major_events_outside_radius=False,
    )
    assert all(p.id != party.id for p, _pe in candidates)


def test_major_event_override_erlaubt_weiteren_radius(db_path, host, guest):
    party = _publish_party_with_location(db_path, host.id, WITHIN_MAJOR_EVENT_RADIUS_80KM, is_major_event=True)

    candidates = discover_storage.list_candidate_publications(
        db_path, guest.id, user_point=HAMBURG, user_radius_km=20.0, allow_major_events_outside_radius=True,
    )
    assert any(p.id == party.id for p, _pe in candidates)


def test_normales_event_profitiert_nicht_vom_major_event_radius(db_path, host, guest):
    """allow_major_events_outside_radius gilt NUR für is_major_event=True -
    ein normales, weit entferntes Event bleibt trotzdem gefiltert."""
    party = _publish_party_with_location(db_path, host.id, BERLIN, is_major_event=False)

    candidates = discover_storage.list_candidate_publications(
        db_path, guest.id, user_point=HAMBURG, user_radius_km=20.0, allow_major_events_outside_radius=True,
    )
    assert all(p.id != party.id for p, _pe in candidates)


def test_ohne_user_point_bleibt_verhalten_unveraendert(db_path, host, guest):
    """Regressions-Kern: hat der User KEINE Discovery-Koordinaten, greift der
    Geo-Filter überhaupt nicht - eine weit entfernte Party bleibt sichtbar
    (nur das weiche city_fit-Ranking-Signal existiert dafür, kein Hard-Filter)."""
    party = _publish_party_with_location(db_path, host.id, BERLIN, is_major_event=False)

    candidates = discover_storage.list_candidate_publications(db_path, guest.id)
    assert any(p.id == party.id for p, _pe in candidates)


def test_kandidat_ohne_koordinaten_bleibt_trotz_user_point_sichtbar(db_path, host, guest):
    """Fehlt einer Party die strukturierte Location komplett (kein
    ``party_locations``-Eintrag), greift der Geo-Filter NICHT für sie -
    Backward-Compat für alle bestehenden, nur-Freitext-Parties."""
    party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "No-Geo Party")
    discover_storage.publish_party(db_path, party.id, event_type="club_event")

    candidates = discover_storage.list_candidate_publications(
        db_path, guest.id, user_point=HAMBURG, user_radius_km=5.0,
    )
    assert any(p.id == party.id for p, _pe in candidates)


def test_get_discover_deck_liefert_distance_km_wenn_beide_seiten_koordinaten_haben(db_path, host, guest):
    _set_guest_prefs(db_path, guest.id, radius_km=50.0, point=HAMBURG)
    party = _publish_party_with_location(db_path, host.id, NEARBY_22KM)

    deck = discover_storage.get_discover_deck(db_path, guest.id)
    entry = next(e for e in deck if e[0].id == party.id)
    _ranked_party, _publication, _score, distance_km, _why = entry
    assert distance_km is not None
    assert 0 < distance_km < 50


def test_get_discover_deck_distance_km_ist_none_ohne_user_koordinaten(db_path, host, guest):
    party = _publish_party_with_location(db_path, host.id, NEARBY_22KM)

    deck = discover_storage.get_discover_deck(db_path, guest.id)
    entry = next(e for e in deck if e[0].id == party.id)
    _ranked_party, _publication, _score, distance_km, _why = entry
    assert distance_km is None
