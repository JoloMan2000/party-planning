"""Social-Graph-Endpoints (Social-Graph-Phase-1: Friends-Fundament).

Abweichend vom sonstigen Router-Muster (ein fester Resource-Prefix pro
Router, z.B. ``discover.py`` mit ``/api/v1/discover``) trägt hier jede Route
ihren vollen restlichen Pfad - der Ziel-Endpoint-Katalog spannt vier
URL-Wurzeln (``/me/*``, ``/users/*``, ``/friend-requests/*``,
``/friends/*``), die keinen gemeinsamen Prefix teilen. Alles trotzdem in
EINER Datei hält die HTTP-Oberfläche der neuen Domain auditierbar an einem
Ort - dieselbe Rolle, die ``discover.py`` für seine (kleinere) Domain
spielt."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

import accounts.notification_storage as notification_storage
import accounts.profile_storage as profile_storage
import accounts.user_storage as user_storage
import social.blocks as blocks
import social.follows as follows
import social.friend_requests as friend_requests
import social.friendships as friendships
import social.search as search
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.social import (
    EventSearchResultPublic,
    FriendPublic,
    FriendRequestCreateResponse,
    FriendRequestPublic,
    FriendRequestsInboxResponse,
    OrganizerSearchResultPublic,
    SearchResponse,
    SocialPrivacyPublic,
    SocialPrivacyUpdateRequest,
    SocialProfilePublic,
    UserBlockResponse,
    UserSearchResponse,
    UserSearchResultPublic,
)
from social.domain import FriendRequest

router = APIRouter(prefix="/api/v1", tags=["social"])


def _username_for(db_path: Path, user_id: str) -> str:
    profile = profile_storage.get_user_profile(db_path, user_id)
    return profile.username if profile is not None else ""


def _privacy_for(db_path: Path, user_id: str) -> tuple[str, str, bool, bool]:
    """Social-Graph-Phase-3: liest die vier Privacy-Felder eines Users -
    fällt auf die ``UserProfile``-Dataclass-Defaults zurück, falls noch
    kein Profil existiert (kein 404/leerer Fehlerzustand nötig, mirrort
    ``_username_for``'s graceful-missing-profile-Handling)."""
    profile = profile_storage.get_user_profile(db_path, user_id)
    if profile is None:
        return "friends", "everyone", True, True
    return (
        profile.friend_list_visibility,
        profile.friend_request_privacy,
        profile.discoverable_by_username,
        profile.discoverable_by_name,
    )


def _list_friends_public(db_path: Path, user_id: str) -> list[FriendPublic]:
    """Geteilte Aufbau-Logik zwischen ``get_my_friends`` und dem neuen
    ``GET /users/{id}/friends`` (Social-Graph-Phase-3) - beide bauen
    dieselbe ``FriendPublic``-Liste, nur für unterschiedliche User-IDs."""
    result = []
    for friendship in friendships.list_friends_for_user(db_path, user_id):
        other_id = friendship.user_b_id if friendship.user_a_id == user_id else friendship.user_a_id
        other_user = user_storage.get_user_by_id(db_path, other_id)
        if other_user is None:
            continue
        result.append(
            FriendPublic(
                user_id=other_id,
                username=_username_for(db_path, other_id),
                display_name=other_user.display_name,
                profile_image=other_user.profile_image,
                friends_since=friendship.created_at,
            )
        )
    return result


def _relationship_status(db_path: Path, current_user_id: str, other_user_id: str) -> str:
    """Reihenfolge der Checks ist bewusst: ``self`` und ``blocked`` sind
    endgültig (nichts anderes kann gleichzeitig gelten), danach ``friends``
    vor den pending-Request-Zuständen, da eine bestehende Friendship jede
    veraltete pending-Zeile logisch überschreibt (kann durch Cross-Merge
    ohnehin nicht gleichzeitig existieren)."""
    if current_user_id == other_user_id:
        return "self"
    if blocks.is_blocked(db_path, current_user_id, other_user_id):
        return "blocked"
    if friendships.are_friends(db_path, current_user_id, other_user_id):
        return "friends"
    if friend_requests.get_pending_request(db_path, current_user_id, other_user_id) is not None:
        return "request_sent"
    if friend_requests.get_pending_request(db_path, other_user_id, current_user_id) is not None:
        return "request_received"
    return "none"


def _to_friend_request_public(db_path: Path, request: FriendRequest, current_user_id: str) -> FriendRequestPublic:
    if request.sender_id == current_user_id:
        direction, other_id = "outgoing", request.receiver_id
    else:
        direction, other_id = "incoming", request.sender_id
    other_user = user_storage.get_user_by_id(db_path, other_id)
    return FriendRequestPublic(
        id=request.id,
        direction=direction,
        status=request.status.value,
        version=request.version,
        other_user_id=other_id,
        other_username=_username_for(db_path, other_id),
        other_display_name=other_user.display_name if other_user is not None else "",
        other_profile_image=other_user.profile_image if other_user is not None else "",
        created_at=request.created_at,
        responded_at=request.responded_at,
    )


@router.get("/me/friends", response_model=list[FriendPublic])
def get_my_friends(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[FriendPublic]:
    return _list_friends_public(db_path, current_user.id)


@router.get("/users/{user_id}/friends", response_model=list[FriendPublic])
def get_user_friends(
    user_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[FriendPublic]:
    """Social-Graph-Phase-3: erste Möglichkeit, die Freundesliste eines
    ANDEREN Users zu sehen - ohne diesen Endpoint wäre
    ``friend_list_visibility`` enforced, aber für niemanden je sichtbar
    (siehe Plan). Self-View ist immer erlaubt, unabhängig von der eigenen
    Einstellung - die eigene Privacy-Policy beschränkt nie einen selbst."""
    target = user_storage.get_user_by_id(db_path, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden.")
    if user_id == current_user.id:
        return _list_friends_public(db_path, user_id)
    if blocks.is_blocked(db_path, current_user.id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nicht erlaubt.")
    visibility, _, _, _ = _privacy_for(db_path, user_id)
    if visibility == "nobody":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Diese Freundesliste ist privat.")
    if visibility == "friends" and not friendships.are_friends(db_path, current_user.id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Diese Freundesliste ist privat.")
    return _list_friends_public(db_path, user_id)


@router.get("/me/friend-requests", response_model=FriendRequestsInboxResponse)
def get_my_friend_requests(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> FriendRequestsInboxResponse:
    incoming = friend_requests.list_incoming_requests(db_path, current_user.id)
    outgoing = friend_requests.list_outgoing_requests(db_path, current_user.id)
    return FriendRequestsInboxResponse(
        incoming=[_to_friend_request_public(db_path, r, current_user.id) for r in incoming],
        outgoing=[_to_friend_request_public(db_path, r, current_user.id) for r in outgoing],
    )


@router.get("/me/social-privacy", response_model=SocialPrivacyPublic)
def get_social_privacy(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> SocialPrivacyPublic:
    """Kein 404 bei fehlendem Profil (anders als ``GET /me/profile``) - diese
    Einstellungen sind nicht ans Onboarding-Gate gekoppelt, ein frischer
    User bekommt einfach die Defaults zurück (siehe ``_privacy_for``)."""
    visibility, request_privacy, disc_username, disc_name = _privacy_for(db_path, current_user.id)
    return SocialPrivacyPublic(
        friend_list_visibility=visibility,
        friend_request_privacy=request_privacy,
        discoverable_by_username=disc_username,
        discoverable_by_name=disc_name,
    )


@router.put("/me/social-privacy", response_model=SocialPrivacyPublic)
def update_social_privacy(
    payload: SocialPrivacyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> SocialPrivacyPublic:
    existing = profile_storage.get_user_profile(db_path, current_user.id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profil muss zuerst über birth-date-correction (Onboarding) angelegt werden.",
        )
    profile = profile_storage.upsert_user_profile(
        db_path,
        current_user.id,
        friend_list_visibility=payload.friend_list_visibility,
        friend_request_privacy=payload.friend_request_privacy,
        discoverable_by_username=payload.discoverable_by_username,
        discoverable_by_name=payload.discoverable_by_name,
    )
    return SocialPrivacyPublic(
        friend_list_visibility=profile.friend_list_visibility,
        friend_request_privacy=profile.friend_request_privacy,
        discoverable_by_username=profile.discoverable_by_username,
        discoverable_by_name=profile.discoverable_by_name,
    )


def _user_search_results_public(
    db_path: Path, current_user_id: str, rows: list, my_friend_ids: set[str]
) -> list[UserSearchResultPublic]:
    """Gemeinsame Aufbereitung für ``GET /users/search`` und den People-Teil
    von ``GET /search`` (Social-Graph-Phase-6): Blockierte rausfiltern,
    ``relationship_status`` + ``mutual_friend_count`` je Treffer anreichern.
    ``my_friend_ids`` wird vom Aufrufer EINMAL pro Request geladen (siehe
    ``friendships.mutual_friend_count``-Doku)."""
    return [
        UserSearchResultPublic(
            user_id=r.user_id,
            username=r.username,
            display_name=r.display_name,
            profile_image=r.profile_image,
            relationship_status=_relationship_status(db_path, current_user_id, r.user_id),
            mutual_friend_count=friendships.mutual_friend_count(db_path, my_friend_ids, r.user_id),
        )
        for r in rows
        if not blocks.is_blocked(db_path, current_user_id, r.user_id)
    ]


@router.get("/users/search", response_model=UserSearchResponse)
def search_users(
    q: str = Query(min_length=2),
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> UserSearchResponse:
    rows = search.search_users(db_path, q, exclude_user_id=current_user.id, limit=limit)
    my_friend_ids = friendships.get_friend_user_ids(db_path, current_user.id)
    return UserSearchResponse(results=_user_search_results_public(db_path, current_user.id, rows, my_friend_ids))


@router.get("/search", response_model=SearchResponse)
def unified_search(
    q: str = Query(min_length=2),
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> SearchResponse:
    """Social-Graph-Phase-6 (Spec §82-83, §122-125): eine Suche über People +
    Organizers + Events, jede Kategorie mit eigenem Response-Model. ``limit``
    wirkt PRO Kategorie (max. ``3 * limit`` Items). Nur ``verified``
    Organizer und nur veröffentlichte Events sind auffindbar (in der Query,
    siehe ``social.search``); Block-Filter (symmetrisch, über die echte
    Owner-/Host-User-ID) passiert hier im Router."""
    # People
    user_rows = search.search_users(db_path, q, exclude_user_id=current_user.id, limit=limit)
    my_friend_ids = friendships.get_friend_user_ids(db_path, current_user.id)
    users = _user_search_results_public(db_path, current_user.id, user_rows, my_friend_ids)

    # Organizers - Block-Filter über den echten Owner-User (symmetrisch)
    organizers_out = [
        OrganizerSearchResultPublic(
            organizer_id=o.organizer_id,
            display_name=o.display_name,
            verified=o.verification_status == "verified",
            follower_count=follows.count_organizer_followers(db_path, o.organizer_id),
            is_following=follows.is_following_organizer(db_path, current_user.id, o.organizer_id),
        )
        for o in search.search_organizers(db_path, q, limit=limit)
        if not blocks.is_blocked(db_path, current_user.id, o.owner_user_id)
    ]

    # Events - Block-Filter über den echten Host-User (symmetrisch)
    events_out = []
    for e in search.search_public_events(db_path, q, limit=limit):
        if blocks.is_blocked(db_path, current_user.id, e.host_user_id):
            continue
        host = user_storage.get_user_by_id(db_path, e.host_user_id)
        events_out.append(
            EventSearchResultPublic(
                party_id=e.party_id,
                name=e.name,
                starts_at=e.starts_at,
                location=e.location,
                cover_image=e.cover_image,
                event_type=e.event_type,
                organizer_name=host.display_name if host is not None else "",
                is_following=follows.is_following_event(db_path, current_user.id, e.party_id),
            )
        )

    return SearchResponse(users=users, organizers=organizers_out, events=events_out)


@router.get("/users/{user_id}/social-profile", response_model=SocialProfilePublic)
def get_social_profile(
    user_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> SocialProfilePublic:
    target = user_storage.get_user_by_id(db_path, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden.")
    return SocialProfilePublic(
        user_id=target.id,
        username=_username_for(db_path, target.id),
        display_name=target.display_name,
        profile_image=target.profile_image,
        relationship_status=_relationship_status(db_path, current_user.id, target.id),
        mutual_friend_count=friendships.mutual_friend_count(
            db_path, friendships.get_friend_user_ids(db_path, current_user.id), target.id
        ),
    )


@router.post("/users/{user_id}/friend-request", response_model=FriendRequestCreateResponse)
def send_friend_request(
    user_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> FriendRequestCreateResponse:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Du kannst dir selbst keine Freundschaftsanfrage senden.")
    target = user_storage.get_user_by_id(db_path, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden.")
    _, request_privacy, _, _ = _privacy_for(db_path, user_id)
    if request_privacy == "nobody":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dieser User nimmt aktuell keine Freundschaftsanfragen an."
        )
    try:
        result = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, current_user.id, user_id)
    except friend_requests.SelfFriendRequestError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Du kannst dir selbst keine Freundschaftsanfrage senden.")
    except friend_requests.UserBlockedError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Freundschaftsanfrage nicht möglich.")
    except friend_requests.AlreadyFriendsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ihr seid bereits befreundet.")
    except friend_requests.FriendRequestAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Es gibt bereits eine offene Anfrage.")

    if result.merged:
        notification_storage.create_notification(
            db_path, uuid.uuid4().hex, result.request.sender_id, None, "friend_request_accepted",
            f"{current_user.display_name} accepted your friend request.",
        )
    else:
        notification_storage.create_notification(
            db_path, uuid.uuid4().hex, user_id, None, "friend_request_received",
            f"{current_user.display_name} sent you a friend request.",
        )
    return FriendRequestCreateResponse(
        request=_to_friend_request_public(db_path, result.request, current_user.id), merged=result.merged
    )


@router.post("/friend-requests/{friend_request_id}/accept", response_model=FriendRequestPublic)
def accept_friend_request(
    friend_request_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> FriendRequestPublic:
    try:
        result = friend_requests.accept_friend_request(db_path, friend_request_id, current_user.id)
    except friend_requests.FriendRequestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden.")
    except friend_requests.InvalidFriendRequestActorError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur der Empfänger kann diese Anfrage annehmen.")
    except friend_requests.InvalidFriendRequestTransitionError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Anfrage ist nicht mehr offen.")
    notification_storage.create_notification(
        db_path, uuid.uuid4().hex, result.request.sender_id, None, "friend_request_accepted",
        f"{current_user.display_name} accepted your friend request.",
    )
    return _to_friend_request_public(db_path, result.request, current_user.id)


@router.post("/friend-requests/{friend_request_id}/decline", response_model=FriendRequestPublic)
def decline_friend_request(
    friend_request_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> FriendRequestPublic:
    try:
        request = friend_requests.decline_friend_request(db_path, friend_request_id, current_user.id)
    except friend_requests.FriendRequestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden.")
    except friend_requests.InvalidFriendRequestActorError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur der Empfänger kann diese Anfrage ablehnen.")
    except friend_requests.InvalidFriendRequestTransitionError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Anfrage ist nicht mehr offen.")
    return _to_friend_request_public(db_path, request, current_user.id)


@router.post("/friend-requests/{friend_request_id}/cancel", response_model=FriendRequestPublic)
def cancel_friend_request(
    friend_request_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> FriendRequestPublic:
    try:
        request = friend_requests.cancel_friend_request(db_path, friend_request_id, current_user.id)
    except friend_requests.FriendRequestNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden.")
    except friend_requests.InvalidFriendRequestActorError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur der Sender kann diese Anfrage zurückziehen.")
    except friend_requests.InvalidFriendRequestTransitionError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Anfrage ist nicht mehr offen.")
    return _to_friend_request_public(db_path, request, current_user.id)


@router.delete("/friends/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_friend(
    user_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> None:
    """Idempotent (mirrort ``unblock_organizer``-Semantik) - kein 404 bei
    nicht-bestehender Freundschaft, da "entfernen" bereits den Zielzustand
    beschreibt."""
    friendships.remove_friendship(db_path, current_user.id, user_id)


@router.post("/users/{user_id}/block", response_model=UserBlockResponse)
def block_user(
    user_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> UserBlockResponse:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Du kannst dich nicht selbst blockieren.")
    target = user_storage.get_user_by_id(db_path, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden.")
    blocks.block_user(db_path, uuid.uuid4().hex, current_user.id, user_id)
    return UserBlockResponse(user_id=user_id, blocked=True)


@router.delete("/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(
    user_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> None:
    blocks.unblock_user(db_path, current_user.id, user_id)
