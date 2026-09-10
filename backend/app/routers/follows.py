"""Following-Domain-Endpunkte (Social-Graph-Phase-5, AUFGABE-Spec §45-79).

Backend-only diese Phase - keine Flutter-Screens (gleiches Precedent wie
Organizer-Foundation / Admin-User-Verification, die seit jeher curl-only
sind).

Wie ``backend/app/routers/social.py`` trägt jede Route ihren vollen Pfad:
der Follow-Katalog spannt ``/organizers/*``, ``/events/*`` und
``/me/following/*`` ohne gemeinsames Präfix, bleibt aber als eine
zusammenhängende HTTP-Fläche in einer Datei auditierbar.

Statuscode-Regeln (bewusst an bestehende Idiome angelehnt):
- 404 "nicht öffentlich folgbar" (Organizer unverifiziert ODER Event
  unveröffentlicht) - eine Regel für beide, mirrort
  ``discover.py::act_on_discover_card`` ("Diese Party ist nicht öffentlich
  sichtbar").
- 422 Self-Follow (eigener Organizer / eigenes Event) - mirrort
  ``discover.py::block_organizer`` und alle Self-Targets in ``social.py``.
- DELETE = idempotenter No-Op (204, kein Body, keine Existenzprüfung) -
  mirrort ``DELETE /friends/{id}`` / ``DELETE /users/{id}/block`` /
  ``DELETE /discover/organizers/{id}/block``.
- "Schon gefolgt?" wird VOR dem Folgbarkeits-Gate geprüft: wer einem
  später suspendierten Organizer / unveröffentlichten Event folgt, bekommt
  weiterhin einen idempotenten 200 und bleibt konsistent mit
  ``GET /me/following/*`` (das nicht nach aktuellem Status filtert)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.discover_storage as discover_storage
import accounts.party_storage as party_storage
import organizers.storage as organizers_storage
import social.follows as follows
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.following import (
    EventFollowStatusResponse,
    FollowedEventPublic,
    OrganizerFollowStatusResponse,
)
from backend.app.schemas.organizers import OrganizerPublic
from organizers.domain import OrganizerVerificationStatus

router = APIRouter(prefix="/api/v1", tags=["following"])


def _organizer_public(organizer) -> OrganizerPublic:
    return OrganizerPublic(
        id=organizer.id, owner_user_id=organizer.owner_user_id, display_name=organizer.display_name,
        organizer_type=organizer.organizer_type, verification_status=organizer.verification_status.value,
        description=organizer.description, website_url=organizer.website_url, my_role=None,
        created_at=organizer.created_at, updated_at=organizer.updated_at,
    )


def _organizer_follow_status(db_path: Path, user_id: str, organizer_id: str) -> OrganizerFollowStatusResponse:
    return OrganizerFollowStatusResponse(
        organizer_id=organizer_id,
        follower_count=follows.count_organizer_followers(db_path, organizer_id),
        following=follows.is_following_organizer(db_path, user_id, organizer_id),
    )


def _event_follow_status(db_path: Path, user_id: str, party_id: str) -> EventFollowStatusResponse:
    return EventFollowStatusResponse(
        party_id=party_id,
        follower_count=follows.count_event_followers(db_path, party_id),
        following=follows.is_following_event(db_path, user_id, party_id),
    )


# --- Organizer follows -------------------------------------------------


@router.post("/organizers/{organizer_id}/follow", response_model=OrganizerFollowStatusResponse)
def follow_organizer(
    organizer_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> OrganizerFollowStatusResponse:
    """Folgt einem verifizierten ``Organizer`` (Spec §53-57). Sofort aktiv,
    keine Zustimmung des Organizers nötig. Idempotent."""
    organizer = organizers_storage.get_organizer(db_path, organizer_id)
    if organizer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer nicht gefunden.")
    if organizer.owner_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Du kannst deinem eigenen Organizer nicht folgen."
        )
    if not follows.is_following_organizer(db_path, current_user.id, organizer_id):
        if organizer.verification_status != OrganizerVerificationStatus.VERIFIED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dieser Organizer ist noch nicht verifiziert."
            )
        follows.follow_organizer(db_path, uuid.uuid4().hex, current_user.id, organizer_id)
    return _organizer_follow_status(db_path, current_user.id, organizer_id)


@router.delete("/organizers/{organizer_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_organizer(
    organizer_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> None:
    """Hebt einen Organizer-Follow auf. No-Op, falls kein Follow existiert
    (keine Existenzprüfung des Organizers - mirrort ``unblock``-Semantik)."""
    follows.unfollow_organizer(db_path, current_user.id, organizer_id)


@router.get("/organizers/{organizer_id}/followers", response_model=OrganizerFollowStatusResponse)
def get_organizer_followers(
    organizer_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> OrganizerFollowStatusResponse:
    """Serverseitige Follower-Zahl (Spec §59) plus ``following`` aus Sicht
    des Aufrufers. Bewusst NICHT member-gated (anders als
    ``organizers.py::GET /{id}``) - die Follower-Zahl ist öffentliche
    Profil-Information."""
    if organizers_storage.get_organizer(db_path, organizer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer nicht gefunden.")
    return _organizer_follow_status(db_path, current_user.id, organizer_id)


# --- Event follows ---------------------------------------------------


@router.post("/events/{party_id}/follow", response_model=EventFollowStatusResponse)
def follow_event(
    party_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> EventFollowStatusResponse:
    """Folgt einem veröffentlichten Event (Spec §67-72). ``Follow Event`` ist
    strikt getrennt von ``Going``/``Maybe`` - es erzeugt keinen
    Kalendereintrag, nur Update-Interesse. Idempotent."""
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")
    if party.host_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Du kannst deinem eigenen Event nicht folgen."
        )
    if not follows.is_following_event(db_path, current_user.id, party_id):
        if discover_storage.get_publication(db_path, party_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Diese Party ist nicht öffentlich sichtbar."
            )
        follows.follow_event(db_path, uuid.uuid4().hex, current_user.id, party_id)
    return _event_follow_status(db_path, current_user.id, party_id)


@router.delete("/events/{party_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_event(
    party_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> None:
    """Hebt einen Event-Follow auf. No-Op, falls kein Follow existiert."""
    follows.unfollow_event(db_path, current_user.id, party_id)


@router.get("/events/{party_id}/followers", response_model=EventFollowStatusResponse)
def get_event_followers(
    party_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> EventFollowStatusResponse:
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")
    if discover_storage.get_publication(db_path, party_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diese Party ist nicht öffentlich sichtbar.")
    return _event_follow_status(db_path, current_user.id, party_id)


# --- My following lists ---------------------------------------------


@router.get("/me/following/organizers", response_model=list[OrganizerPublic])
def list_my_followed_organizers(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> list[OrganizerPublic]:
    """Gefolgte Organizer, neueste zuerst (Spec §66). Bewusst OHNE Filter
    auf den aktuellen ``verification_status`` - wer einem Organizer gefolgt
    ist, sieht ihn weiter in seiner Liste, auch wenn dessen Badge später
    entzogen wurde (Unfollow bleibt explizite Nutzer-Entscheidung)."""
    result: list[OrganizerPublic] = []
    for follow in follows.list_organizer_follows(db_path, current_user.id):
        organizer = organizers_storage.get_organizer(db_path, follow.organizer_id)
        if organizer is not None:
            result.append(_organizer_public(organizer))
    return result


@router.get("/me/following/events", response_model=list[FollowedEventPublic])
def list_my_followed_events(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> list[FollowedEventPublic]:
    """Gefolgte Events, neueste zuerst (Spec §73 "Saved / Followed Events").
    Follows auf inzwischen unveröffentlichte Partys werden ausgeblendet
    (nicht gelöscht) - ein erneutes Publish bringt sie zurück."""
    result: list[FollowedEventPublic] = []
    for follow in follows.list_event_follows(db_path, current_user.id):
        party = party_storage.get_party(db_path, follow.party_id)
        publication = discover_storage.get_publication(db_path, follow.party_id)
        if party is None or publication is None:
            continue
        result.append(
            FollowedEventPublic(
                party_id=party.id, name=party.name, starts_at=party.starts_at, location=party.location,
                event_type=publication.event_type, followed_at=follow.created_at,
            )
        )
    return result
