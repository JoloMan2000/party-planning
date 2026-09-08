from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.discover_storage as discover_storage
import accounts.notification_storage as notification_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import DiscoverAction, PartyRole, RsvpStatus, User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.discover import (
    DiscoverActionRequest,
    DiscoverActionResponse,
    DiscoverCardPublic,
    DiscoverDeckResponse,
)

router = APIRouter(prefix="/api/v1/discover", tags=["discover"])


@router.get("/deck", response_model=DiscoverDeckResponse)
def get_deck(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> DiscoverDeckResponse:
    ranked = discover_storage.get_discover_deck(db_path, current_user.id)
    cards = []
    for party, publication, score, distance_km in ranked:
        host = user_storage.get_user_by_id(db_path, party.host_user_id)
        cards.append(
            DiscoverCardPublic(
                party_id=party.id, name=party.name, description=party.description,
                starts_at=party.starts_at, location=party.location, cover_image=party.cover_image,
                event_type=publication.event_type, interest_tags=publication.interest_tags,
                host_display_name=host.display_name if host is not None else "",
                match_score=round(score, 3),
                distance_km=distance_km,
            )
        )
    return DiscoverDeckResponse(cards=cards)


@router.post("/{party_id}/action", response_model=DiscoverActionResponse)
def act_on_discover_card(
    party_id: str,
    payload: DiscoverActionRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> DiscoverActionResponse:
    """Swipe-Ergebnis fürs Discover-MVP - GEHT NICHT über die bestehende
    Button-RSVP (``invitations.py``), die weiterhin ausschließlich für per
    E-Mail eingeladene Gäste zuständig bleibt (siehe Plan, Punkt 4/5).
    'going'/'maybe' joinen sofort per ``upsert_membership`` - kein
    Host-Approval-Schritt im MVP."""
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")
    if party.host_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Du kannst deine eigene Party nicht swipen.")
    publication = discover_storage.get_publication(db_path, party_id)
    if publication is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diese Party ist nicht öffentlich sichtbar.")
    try:
        action = DiscoverAction(payload.action)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ungültige Discover-Aktion.")

    membership = None
    if action in (DiscoverAction.GOING, DiscoverAction.MAYBE) and discover_storage.is_party_full(db_path, party_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This party is full.")
    if action == DiscoverAction.GOING:
        membership = party_storage.upsert_membership(db_path, party_id, current_user.id, PartyRole.GUEST, RsvpStatus.ACCEPTED)
    elif action == DiscoverAction.MAYBE:
        membership = party_storage.upsert_membership(db_path, party_id, current_user.id, PartyRole.GUEST, RsvpStatus.TENTATIVE)

    discover_storage.upsert_discover_action(db_path, uuid.uuid4().hex, current_user.id, party_id, action)

    if membership is not None:
        notification_storage.create_notification(
            db_path, uuid.uuid4().hex, party.host_user_id, party_id, "discover_join",
            f"{current_user.display_name} is {membership.rsvp_status.value} for {party.name} (via Discover).",
        )

    return DiscoverActionResponse(
        party_id=party_id,
        action=action.value,
        membership_role=membership.role.value if membership is not None else None,
        membership_rsvp_status=membership.rsvp_status.value if membership is not None else None,
    )


@router.delete("/{party_id}/action", status_code=status.HTTP_204_NO_CONTENT)
def undo_discover_action(
    party_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> None:
    """Undo eines früheren Discover-Swipes ('going'/'maybe') - bewusst KEIN
    Rückwärts-Swipe im Deck (Produktentscheidung), sondern ein expliziter
    Undo-Button im Party-Detail-Screen (siehe Plan). Entfernt sowohl die
    Mitgliedschaft (= Party verlassen) als auch den discover_actions-
    Eintrag, damit die Party bei einem künftigen Deck-Fetch wieder auftauchen
    kann (siehe ``list_candidate_publications`` - beide Filter müssen
    geräumt werden)."""
    record = discover_storage.get_discover_action(db_path, current_user.id, party_id)
    if record is None or record.action not in (DiscoverAction.GOING, DiscoverAction.MAYBE):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Discover join found to undo for this party.",
        )
    party_storage.remove_membership(db_path, party_id, current_user.id)
    discover_storage.delete_discover_action(db_path, current_user.id, party_id)
