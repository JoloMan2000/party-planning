"""Tests für ``geo/privacy.py`` - volle Matrix aus Sichtbarkeitspolicy x
RSVP-Status x Rolle (Spec §26-29, §74-75)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from accounts.domain import PartyMembership, PartyRole, RsvpStatus
from geo.domain import GeoAddress, GeoPoint, PartyLocation, VisibilityPolicy
from geo.privacy import GeoPrivacyPolicy, build_party_location_view


def _membership(role: PartyRole, rsvp_status: RsvpStatus) -> PartyMembership:
    return PartyMembership(
        id="membership-1", party_id="party-1", user_id="user-1", role=role, rsvp_status=rsvp_status,
        joined_at=datetime.now(timezone.utc),
    )


def _location(policy: VisibilityPolicy) -> PartyLocation:
    return PartyLocation(
        id="loc:party-1", party_id="party-1", place_name="Elbphilharmonie",
        address=GeoAddress(city="Hamburg", formatted_address="Platz der Deutschen Einheit 1, Hamburg"),
        point=GeoPoint(latitude=53.5411, longitude=9.9844),
        visibility_policy=policy, public_location_label="Somewhere in Hamburg",
    )


RSVP_STATUSES = [RsvpStatus.PENDING, RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED]
POLICIES = list(VisibilityPolicy)


@pytest.mark.parametrize("policy", POLICIES)
def test_host_sieht_immer_exakt_unabhaengig_von_policy(policy):
    membership = _membership(PartyRole.HOST, RsvpStatus.PENDING)
    location = _location(policy)
    assert GeoPrivacyPolicy.can_view_exact_party_location(membership, location) is True


@pytest.mark.parametrize("policy", POLICIES)
def test_co_host_sieht_immer_exakt_unabhaengig_von_policy(policy):
    membership = _membership(PartyRole.CO_HOST, RsvpStatus.PENDING)
    location = _location(policy)
    assert GeoPrivacyPolicy.can_view_exact_party_location(membership, location) is True


@pytest.mark.parametrize("rsvp_status", RSVP_STATUSES)
def test_exact_immediately_gilt_fuer_jeden_rsvp_status(rsvp_status):
    membership = _membership(PartyRole.GUEST, rsvp_status)
    location = _location(VisibilityPolicy.EXACT_IMMEDIATELY)
    assert GeoPrivacyPolicy.can_view_exact_party_location(membership, location) is True


def test_exact_immediately_gilt_auch_ohne_membership():
    location = _location(VisibilityPolicy.EXACT_IMMEDIATELY)
    assert GeoPrivacyPolicy.can_view_exact_party_location(None, location) is True


@pytest.mark.parametrize("rsvp_status", RSVP_STATUSES)
def test_approximate_only_gilt_fuer_keinen_rsvp_status(rsvp_status):
    membership = _membership(PartyRole.GUEST, rsvp_status)
    location = _location(VisibilityPolicy.APPROXIMATE_ONLY)
    assert GeoPrivacyPolicy.can_view_exact_party_location(membership, location) is False


def test_approximate_only_gilt_auch_ohne_membership_als_false():
    location = _location(VisibilityPolicy.APPROXIMATE_ONLY)
    assert GeoPrivacyPolicy.can_view_exact_party_location(None, location) is False


@pytest.mark.parametrize(
    "rsvp_status,expected",
    [
        (RsvpStatus.PENDING, False),
        (RsvpStatus.ACCEPTED, True),
        (RsvpStatus.TENTATIVE, False),
        (RsvpStatus.DECLINED, False),
    ],
)
def test_exact_after_accept_nur_bei_accepted(rsvp_status, expected):
    membership = _membership(PartyRole.GUEST, rsvp_status)
    location = _location(VisibilityPolicy.EXACT_AFTER_ACCEPT)
    assert GeoPrivacyPolicy.can_view_exact_party_location(membership, location) is expected


def test_exact_after_accept_ohne_membership_ist_false():
    location = _location(VisibilityPolicy.EXACT_AFTER_ACCEPT)
    assert GeoPrivacyPolicy.can_view_exact_party_location(None, location) is False


@pytest.mark.parametrize(
    "rsvp_status,expected",
    [
        (RsvpStatus.PENDING, False),
        (RsvpStatus.ACCEPTED, True),
        (RsvpStatus.TENTATIVE, True),
        (RsvpStatus.DECLINED, False),
    ],
)
def test_exact_after_accept_or_maybe(rsvp_status, expected):
    membership = _membership(PartyRole.GUEST, rsvp_status)
    location = _location(VisibilityPolicy.EXACT_AFTER_ACCEPT_OR_MAYBE)
    assert GeoPrivacyPolicy.can_view_exact_party_location(membership, location) is expected


# --- build_party_location_view ---------------------------------------------


def test_view_autorisiert_liefert_volle_daten():
    membership = _membership(PartyRole.GUEST, RsvpStatus.ACCEPTED)
    location = _location(VisibilityPolicy.EXACT_AFTER_ACCEPT)
    view = build_party_location_view(location, membership)
    assert view.visibility_level == "exact"
    assert view.formatted_address == location.address.formatted_address
    assert view.point == location.point
    assert view.display_label == location.public_location_label


def test_view_unautorisiert_verbirgt_alles_ausser_label():
    membership = _membership(PartyRole.GUEST, RsvpStatus.PENDING)
    location = _location(VisibilityPolicy.EXACT_AFTER_ACCEPT)
    view = build_party_location_view(location, membership)
    assert view.visibility_level == "approximate"
    assert view.formatted_address is None
    assert view.point is None
    assert view.arrival_instructions is None
    assert view.display_label == location.public_location_label


def test_view_unautorisiert_ohne_label_ist_leerstring_kein_adress_leak():
    membership = _membership(PartyRole.GUEST, RsvpStatus.PENDING)
    location = _location(VisibilityPolicy.EXACT_AFTER_ACCEPT)
    location.public_location_label = ""
    view = build_party_location_view(location, membership)
    assert view.display_label == ""
