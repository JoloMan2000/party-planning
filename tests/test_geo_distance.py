"""Tests für ``geo/distance.py`` - echte geodätische Distanz (Spec §46-47)
gegen bekannte Stadt-Paare, sowie Sanity-Checks fürs SQL-Prefilter
``bounding_box`` (Spec §50: nie die finale Eligibility-Entscheidung)."""

from __future__ import annotations

from geo.distance import bounding_box, haversine_km
from geo.domain import GeoPoint

HAMBURG = GeoPoint(latitude=53.5511, longitude=9.9937)
BERLIN = GeoPoint(latitude=52.5200, longitude=13.4050)
MUNICH = GeoPoint(latitude=48.1351, longitude=11.5820)


def test_haversine_hamburg_berlin_rund_255km():
    distance = haversine_km(HAMBURG, BERLIN)
    assert 240 <= distance <= 270


def test_haversine_ist_symmetrisch():
    assert haversine_km(HAMBURG, BERLIN) == haversine_km(BERLIN, HAMBURG)


def test_haversine_gleicher_punkt_ist_null():
    assert haversine_km(HAMBURG, HAMBURG) == 0.0


def test_haversine_hamburg_muenchen_groesser_als_hamburg_berlin():
    assert haversine_km(HAMBURG, MUNICH) > haversine_km(HAMBURG, BERLIN)


def test_bounding_box_umschliesst_zentrum():
    lat_min, lat_max, lon_min, lon_max = bounding_box(HAMBURG, 50.0)
    assert lat_min < HAMBURG.latitude < lat_max
    assert lon_min < HAMBURG.longitude < lon_max


def test_bounding_box_deckt_tatsaechlichen_distanz_treffer_ab():
    """Ein Punkt, der laut haversine_km innerhalb des Radius liegt, muss auch
    innerhalb der bounding_box liegen (das SQL-Prefilter darf niemals einen
    echten Treffer herausfiltern)."""
    radius_km = 30.0
    lat_min, lat_max, lon_min, lon_max = bounding_box(HAMBURG, radius_km)

    # Punkt ca. 20km nördlich von Hamburg.
    nearby = GeoPoint(latitude=HAMBURG.latitude + 0.18, longitude=HAMBURG.longitude)
    assert haversine_km(HAMBURG, nearby) < radius_km
    assert lat_min <= nearby.latitude <= lat_max
    assert lon_min <= nearby.longitude <= lon_max


def test_bounding_box_pol_naehe_gibt_volle_longitude_spanne():
    near_pole = GeoPoint(latitude=89.999999, longitude=0.0)
    _lat_min, _lat_max, lon_min, lon_max = bounding_box(near_pole, 50.0)
    assert lon_min == -180.0
    assert lon_max == 180.0


def test_bounding_box_groesserer_radius_ergibt_groessere_box():
    small = bounding_box(HAMBURG, 10.0)
    large = bounding_box(HAMBURG, 100.0)
    assert large[1] - large[0] > small[1] - small[0]
    assert large[3] - large[2] > small[3] - small[2]
