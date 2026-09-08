"""Sanity-Tests für die Geo-Platform-Dataclasses/-Enums (``geo/domain.py``)."""

from __future__ import annotations

from geo.domain import (
    GeoAddress,
    GeoPlace,
    GeoPoint,
    GeoSearchContext,
    GeoSuggestion,
    LocationPrecision,
    LocationSource,
    PartyLocation,
    PartyLocationView,
    VisibilityPolicy,
)


def test_geo_point_haelt_lat_lon():
    point = GeoPoint(latitude=53.5511, longitude=9.9937)
    assert point.latitude == 53.5511
    assert point.longitude == 9.9937


def test_geo_address_alle_teile_optional_ausser_formatted_address():
    address = GeoAddress()
    assert address.street is None
    assert address.formatted_address == ""


def test_geo_place_default_precision_ist_approximate():
    place = GeoPlace(
        id="1", name="Elbphilharmonie", place_type="building", address=GeoAddress(),
        point=None, provider="nominatim", provider_place_id="1",
    )
    assert place.precision == LocationPrecision.APPROXIMATE


def test_geo_suggestion_distance_meters_optional():
    suggestion = GeoSuggestion(
        provider_place_id="1", primary_text="Ballindamm", secondary_text="Hamburg",
        place_type="street", provider="nominatim",
    )
    assert suggestion.distance_meters is None


def test_geo_search_context_defaults_sind_none():
    context = GeoSearchContext()
    assert context.bias_point is None
    assert context.bias_country_code is None
    assert context.search_session_id is None


def test_visibility_policy_default_ist_exact_after_accept():
    location = PartyLocation(id="loc:1", party_id="1")
    assert location.visibility_policy == VisibilityPolicy.EXACT_AFTER_ACCEPT


def test_location_source_default_ist_organizer_entry():
    location = PartyLocation(id="loc:1", party_id="1")
    assert location.source == LocationSource.ORGANIZER_ENTRY


def test_party_location_manually_adjusted_default_false():
    location = PartyLocation(id="loc:1", party_id="1")
    assert location.manually_adjusted is False


def test_party_location_view_ist_frozen():
    view = PartyLocationView(
        visibility_level="approximate", display_label="Berlin", formatted_address=None,
        point=None, arrival_instructions=None,
    )
    assert view.visibility_level == "approximate"


def test_visibility_policy_enum_werte():
    assert {p.value for p in VisibilityPolicy} == {
        "exact_after_accept", "exact_after_accept_or_maybe", "exact_immediately", "approximate_only",
    }


def test_location_precision_enum_werte():
    assert {p.value for p in LocationPrecision} == {
        "exact", "address", "street", "neighborhood", "city", "approximate",
    }
