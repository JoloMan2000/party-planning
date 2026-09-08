"""Zentrale Autorisierungslogik der Geo Platform (Spec §26-29, §74-75).

Eine EINZIGE ``GeoPrivacyPolicy`` statt verstreuter ``if rsvp_status ==
ACCEPTED``-Checks in Screens/Endpoints - schließt die aktuell bestehende
Lücke, dass ``GET /parties/{id}`` den (bisher freien Text-)Ort unconditional
an jedes Mitglied ausliefert, unabhängig vom RSVP-Status."""

from __future__ import annotations

from accounts.domain import PartyMembership, PartyRole, RsvpStatus
from geo.domain import PartyLocation, PartyLocationView, VisibilityPolicy


class GeoPrivacyPolicy:
    """Reine, zustandslose Autorisierungsfunktionen - kein DB-Zugriff hier,
    Aufrufer übergeben bereits geladene ``PartyMembership``/``PartyLocation``-
    Objekte (analog zum bestehenden ``require_party_role``-Dependency-Muster)."""

    @staticmethod
    def can_view_exact_party_location(membership: PartyMembership | None, location: PartyLocation) -> bool:
        if membership is not None and membership.role in {PartyRole.HOST, PartyRole.CO_HOST}:
            return True

        policy = location.visibility_policy
        if policy == VisibilityPolicy.EXACT_IMMEDIATELY:
            return True
        if policy == VisibilityPolicy.APPROXIMATE_ONLY:
            return False

        if membership is None:
            return False

        if policy == VisibilityPolicy.EXACT_AFTER_ACCEPT:
            return membership.rsvp_status == RsvpStatus.ACCEPTED
        if policy == VisibilityPolicy.EXACT_AFTER_ACCEPT_OR_MAYBE:
            return membership.rsvp_status in {RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE}
        return False


def build_party_location_view(location: PartyLocation, membership: PartyMembership | None) -> PartyLocationView:
    """Baut die für EINEN konkreten Betrachter freigegebene Projektion.

    Unautorisiert: ``formatted_address``/``point``/``arrival_instructions``
    sind IMMER ``None`` - ``display_label`` fällt nur auf das explizit vom
    Host gesetzte ``public_location_label`` zurück (oder Leerstring), leitet
    NIE eine vermeintlich "sichere" Stadt-Näherung aus der echten Adresse ab
    (Spec §29 - kein impliziter Approximate-Leak)."""
    authorized = GeoPrivacyPolicy.can_view_exact_party_location(membership, location)

    if authorized:
        formatted_address = location.address.formatted_address if location.address else None
        return PartyLocationView(
            visibility_level="exact",
            display_label=location.public_location_label or location.place_name or formatted_address or "",
            formatted_address=formatted_address,
            point=location.point,
            arrival_instructions=location.arrival_instructions,
        )

    return PartyLocationView(
        visibility_level="approximate",
        display_label=location.public_location_label or "",
        formatted_address=None,
        point=None,
        arrival_instructions=None,
    )
