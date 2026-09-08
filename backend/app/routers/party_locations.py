"""Strukturierte, privacy-gegatete Party-Location (Spec §18-29) - komplett
additiv zur bestehenden ``parties.location``-Freitextspalte (siehe Plan:
Backward-Compat-Entscheidung). Eigener Router statt Erweiterung von
``parties.py`` (mirroring den Trennungs-Stil von z.B.
``admin_shopping_list.py``)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.notification_storage as notification_storage
import accounts.party_storage as party_storage
import geo.storage as geo_storage
from accounts.domain import PartyRole, RsvpStatus, User
from backend.app.core.auth import get_current_user, require_party_role
from backend.app.core.deps import get_db_path
from backend.app.schemas.geo import GeoPointPublic, PartyLocationSetRequest, PartyLocationViewPublic
from geo.domain import GeoAddress, GeoPoint, LocationPrecision, LocationSource, VisibilityPolicy
from geo.privacy import build_party_location_view

router = APIRouter(prefix="/api/v1/parties", tags=["party-locations"])


def _safe_label(payload: PartyLocationSetRequest) -> str:
    """Wert, der ins bestehende (immer sichtbare) ``Party.location``-Feld
    gespiegelt wird - NIE die volle Adresse, nur das explizite Label oder
    (falls keins gesetzt) die Stadt aus der strukturierten Adresse."""
    if payload.public_location_label:
        return payload.public_location_label
    if payload.address and payload.address.city:
        return payload.address.city
    return payload.place_name or ""


@router.put("/{party_id}/location", response_model=PartyLocationViewPublic)
def set_party_location(
    party_id: str,
    payload: PartyLocationSetRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> PartyLocationViewPublic:
    existing = geo_storage.get_party_location(db_path, party_id)

    address = (
        GeoAddress(
            street=payload.address.street,
            house_number=payload.address.house_number,
            postal_code=payload.address.postal_code,
            city=payload.address.city,
            district=payload.address.district,
            region=payload.address.region,
            country_code=payload.address.country_code,
            country_name=payload.address.country_name,
            formatted_address=payload.address.formatted_address,
        )
        if payload.address
        else None
    )
    point = GeoPoint(latitude=payload.point.latitude, longitude=payload.point.longitude) if payload.point else None

    try:
        precision = LocationPrecision(payload.precision)
        visibility_policy = VisibilityPolicy(payload.visibility_policy)
        source = LocationSource(payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    location = geo_storage.upsert_party_location(
        db_path,
        party_id,
        place_name=payload.place_name,
        address=address,
        point=point,
        precision=precision,
        provider=payload.provider,
        provider_place_id=payload.provider_place_id,
        public_location_label=payload.public_location_label,
        visibility_policy=visibility_policy,
        arrival_instructions=payload.arrival_instructions,
        source=source,
        manually_adjusted=payload.manually_adjusted,
    )

    # Sync des sicheren Labels ins bestehende, unangetastete Legacy-Feld -
    # hält _city_fit/Kalender-Export/etc. lauffähig, ohne diese Codepfade
    # anzufassen (siehe Plan).
    party_storage.update_party(db_path, party_id, location=_safe_label(payload))

    # Benachrichtigung nur bei einer ECHTEN Änderung NACH dem allerersten
    # Speichern (Spec §79 - volle Schwere-Klassifikation bewusst deferred,
    # hier nur ein binäres "hat sich geändert"-Signal).
    if existing is not None:
        for member in party_storage.list_memberships_for_party(db_path, party_id):
            if member.user_id == current_user.id:
                continue
            if member.rsvp_status not in (RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE):
                continue
            party = party_storage.get_party(db_path, party_id)
            party_name = party.name if party is not None else party_id
            notification_storage.create_notification(
                db_path, uuid.uuid4().hex, member.user_id, party_id, "location_changed",
                f"\U0001F4CD {party_name} has a new location.",
            )

    view = build_party_location_view(location, membership)
    return _to_view_public(view)


@router.get("/{party_id}/location", response_model=PartyLocationViewPublic)
def get_party_location(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST, PartyRole.GUEST})),
) -> PartyLocationViewPublic:
    location = geo_storage.get_party_location(db_path, party_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No structured location set for this party.")
    view = build_party_location_view(location, membership)
    return _to_view_public(view)


def _to_view_public(view) -> PartyLocationViewPublic:
    return PartyLocationViewPublic(
        visibility_level=view.visibility_level,
        display_label=view.display_label,
        formatted_address=view.formatted_address,
        point=GeoPointPublic(latitude=view.point.latitude, longitude=view.point.longitude) if view.point else None,
        arrival_instructions=view.arrival_instructions,
    )
