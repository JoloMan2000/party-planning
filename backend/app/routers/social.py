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
import social.friend_requests as friend_requests
import social.friendships as friendships
import social.search as search
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.social import (
    FriendPublic,
    FriendRequestCreateResponse,
    FriendRequestPublic,
    FriendRequestsInboxResponse,
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
    result = []
    for friendship in friendships.list_friends_for_user(db_path, current_user.id):
        other_id = friendship.user_b_id if friendship.user_a_id == current_user.id else friendship.user_a_id
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


@router.get("/users/search", response_model=UserSearchResponse)
def search_users(
    q: str = Query(min_length=2),
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> UserSearchResponse:
    results = search.search_users(db_path, q, exclude_user_id=current_user.id, limit=limit)
    return UserSearchResponse(
        results=[
            UserSearchResultPublic(
                user_id=r.user_id,
                username=r.username,
                display_name=r.display_name,
                profile_image=r.profile_image,
                relationship_status=_relationship_status(db_path, current_user.id, r.user_id),
            )
            for r in results
            if not blocks.is_blocked(db_path, current_user.id, r.user_id)
        ]
    )


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
