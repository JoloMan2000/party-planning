from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

import accounts.discover_storage as discover_storage
import accounts.invitation_storage as invitation_storage
import accounts.notification_settings_storage as notification_settings_storage
import accounts.notification_storage as notification_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import organizers.storage as organizers_storage
import social.blocks as blocks
import social.follows as follows
import social.friendships as friendships
from accounts.domain import DiscoverAction, PartyRole, RsvpStatus, User
from backend.app.core.auth import get_current_user, require_party_role
from backend.app.core.deps import get_db_path, get_media_dir
from backend.app.schemas.accounts import (
    CoHostPromoteRequest,
    CoHostPromoteResponse,
    FriendInviteRequest,
    FriendInviteResponse,
    FriendInviteResultItem,
    GuestListEntry,
    InvitationCreate,
    InvitationPublic,
    PartyCreate,
    PartyGuestsResponse,
    PartyPublic,
    PartyUpdate,
)
from backend.app.schemas.discover import PartyPublishRequest

router = APIRouter(prefix="/api/v1/parties", tags=["parties"])

_MAX_COVER_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def _to_party_public(
    party, publication=None, host_is_verified: bool = False, my_discover_action: str | None = None
) -> PartyPublic:
    return PartyPublic(
        id=party.id, host_user_id=party.host_user_id, name=party.name, description=party.description,
        starts_at=party.starts_at, location=party.location, cover_image=party.cover_image,
        is_published=publication is not None,
        event_type=publication.event_type if publication is not None else "",
        interest_tags=publication.interest_tags if publication is not None else [],
        max_guests=publication.max_guests if publication is not None else 0,
        host_is_verified=host_is_verified,
        my_discover_action=my_discover_action,
        created_at=party.created_at, updated_at=party.updated_at,
    )


def _host_is_verified(db_path: Path, host_user_id: str) -> bool:
    """Social-Graph-Phase-4: prüft jetzt Organizer-Mitgliedschaft statt des
    LEGACY ``User.is_verified``-Flags (siehe
    ``organizers.storage.is_user_verified_organizer_member``-Docstring)."""
    return organizers_storage.is_user_verified_organizer_member(db_path, host_user_id)


def _my_discover_action(db_path: Path, user_id: str, party_id: str) -> str | None:
    record = discover_storage.get_discover_action(db_path, user_id, party_id)
    if record is not None and record.action in (DiscoverAction.GOING, DiscoverAction.MAYBE):
        return record.action.value
    return None


# --- Social-Graph-Phase-8: Followed-Entity-Notification-Fan-out ---------
# Inline im Router (gleiches Muster wie ``party_locations.py``/``invite_friends``:
# Empfänger auflisten, Akteur überspringen, nur bei echtem State-Übergang feuern).

_EVENT_UPDATE_DEDUP_MINUTES = 5


def _notify_new_publication(db_path: Path, party) -> None:
    """Ein Host hat eine Party ZUM ERSTEN MAL veröffentlicht -> alle Follower
    der verifizierten Organizer, in denen der Host Mitglied ist, bekommen
    eine Notification (Spec §64/§91).

    ACHTUNG - Attribution ist NÄHERUNGSWEISE: es gibt kein
    ``Party.organizer_id`` (seit Phase 4 deferred), daher der Umweg über
    "Follower irgendeines verifizierten Organizers des Hosts". Ein Host, der
    in mehreren Organizern Mitglied ist, pingt für eine unabhängige private
    Party alle deren Follower. Präzise Event->Organizer-Zuordnung gehört in
    eine spätere Phase mit echtem Event-Erstellungs-Flow.

    Follower, die den Host geblockt haben (oder umgekehrt), bekommen nichts
    (Spec §80/§128 - Block stoppt Organizer-Notifications). ``is_blocked``
    ist bidirektional."""
    notified: set[str] = set()
    for organizer, _membership in organizers_storage.list_organizers_for_user(db_path, party.host_user_id):
        if organizer.verification_status.value != "verified":
            continue
        for follower_id in follows.list_organizer_follower_ids(db_path, organizer.id):
            if follower_id in notified or follower_id == party.host_user_id:
                continue
            if blocks.is_blocked(db_path, follower_id, party.host_user_id):
                continue
            if not notification_settings_storage.get_notification_settings(db_path, follower_id).organizer_updates:
                continue
            notification_storage.create_notification(
                db_path, uuid.uuid4().hex, follower_id, party.id, "organizer_new_event",
                f"{organizer.display_name} just published a new event: {party.name}.",
            )
            notified.add(follower_id)


def _notify_event_changed(db_path: Path, party, changes: list[str], actor_id: str) -> None:
    """Datum/Ort eines gefolgten (noch veröffentlichten) Events hat sich
    geändert (Spec §72/§90). ``_EVENT_UPDATE_DEDUP_MINUTES`` unterdrückt
    Doppel-Notifications bei schnell aufeinanderfolgenden Edits. Follower,
    die den Host geblockt haben (oder umgekehrt), bekommen nichts."""
    label = " and ".join(changes)
    for follower_id in follows.list_event_follower_ids(db_path, party.id):
        if follower_id == actor_id:
            continue
        if blocks.is_blocked(db_path, follower_id, party.host_user_id):
            continue
        if not notification_settings_storage.get_notification_settings(db_path, follower_id).followed_event_updates:
            continue
        if notification_storage.has_recent_notification(
            db_path, follower_id, "event_updated", party.id, _EVENT_UPDATE_DEDUP_MINUTES
        ):
            continue
        notification_storage.create_notification(
            db_path, uuid.uuid4().hex, follower_id, party.id, "event_updated",
            f"{party.name}: {label} changed.",
        )


def _notify_event_cancelled(db_path: Path, party, actor_id: str) -> None:
    """Ein gefolgtes, veröffentlichtes Event wurde depubliziert = abgesagt
    (Spec §106). Danach keine weiteren normalen Follow-Updates. Follower,
    die den Host geblockt haben (oder umgekehrt), bekommen nichts."""
    for follower_id in follows.list_event_follower_ids(db_path, party.id):
        if follower_id == actor_id:
            continue
        if blocks.is_blocked(db_path, follower_id, party.host_user_id):
            continue
        if not notification_settings_storage.get_notification_settings(db_path, follower_id).followed_event_updates:
            continue
        notification_storage.create_notification(
            db_path, uuid.uuid4().hex, follower_id, party.id, "event_cancelled",
            f"{party.name} has been cancelled.",
        )


@router.post("", response_model=PartyPublic, status_code=status.HTTP_201_CREATED)
def create_party(
    payload: PartyCreate, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> PartyPublic:
    party = party_storage.create_party(
        db_path, uuid.uuid4().hex, current_user.id, payload.name,
        description=payload.description, starts_at=payload.starts_at, location=payload.location,
    )
    return _to_party_public(
        party, host_is_verified=organizers_storage.is_user_verified_organizer_member(db_path, current_user.id)
    )


@router.get("/{party_id}", response_model=PartyPublic)
def get_party(
    party_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST, PartyRole.GUEST})),
) -> PartyPublic:
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")
    return _to_party_public(
        party,
        discover_storage.get_publication(db_path, party_id),
        _host_is_verified(db_path, party.host_user_id),
        _my_discover_action(db_path, current_user.id, party_id),
    )


@router.patch("/{party_id}", response_model=PartyPublic)
def update_party(
    party_id: str,
    payload: PartyUpdate,
    db_path: Path = Depends(get_db_path),
    membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> PartyPublic:
    before = party_storage.get_party(db_path, party_id)
    party = party_storage.update_party(db_path, party_id, **payload.model_dump(exclude_unset=True))
    # Social-Graph-Phase-8: Datums-/Ort-Änderung an Event-Follower melden -
    # nur wenn das Event aktuell veröffentlicht ist (Spec §106: ein
    # abgesagtes Event erzeugt keine weiteren Updates).
    if before is not None:
        changes: list[str] = []
        if before.starts_at != party.starts_at:
            changes.append("date")
        if before.location != party.location:
            changes.append("location")
        if changes and discover_storage.get_publication(db_path, party_id) is not None:
            _notify_event_changed(db_path, party, changes, membership.user_id)
    return _to_party_public(
        party, discover_storage.get_publication(db_path, party_id), _host_is_verified(db_path, party.host_user_id)
    )


@router.post("/{party_id}/publish", response_model=PartyPublic)
def publish_party(
    party_id: str,
    payload: PartyPublishRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST})),
) -> PartyPublic:
    """Macht eine bereits existierende private Party im Discover-Deck
    anderer User sichtbar (MVP-Scope-Entscheidung: kein separater Event-
    Erstellungs-Flow, siehe Plan). Nur der Host darf das, und nur wenn der
    Host Mitglied (beliebige Rolle) eines verifizierten ``Organizer`` ist
    (Social-Graph-Phase-4, siehe
    ``organizers.storage.is_user_verified_organizer_member`` - ersetzt das
    LEGACY ``User.is_verified``-Flag funktional, siehe dessen Docstring in
    ``backend/app/schemas/admin.py::UserAdminPublic``)."""
    if not organizers_storage.is_user_verified_organizer_member(db_path, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a member of a verified organizer before you can publish parties.",
        )
    # Social-Graph-Phase-8: nur ein echter None->published-Übergang löst den
    # Follower-Fan-out aus (Publish ist ein Upsert, ein Re-Publish zum Ändern
    # der Tags darf keine zweite "neues Event"-Notification erzeugen).
    newly_published = discover_storage.get_publication(db_path, party_id) is None
    discover_storage.publish_party(
        db_path, party_id, event_type=payload.event_type, interest_tags=payload.interest_tags,
        max_guests=payload.max_guests, is_major_event=payload.is_major_event,
    )
    party = party_storage.get_party(db_path, party_id)
    if newly_published and party is not None:
        _notify_new_publication(db_path, party)
    return _to_party_public(
        party, discover_storage.get_publication(db_path, party_id),
        organizers_storage.is_user_verified_organizer_member(db_path, current_user.id),
    )


@router.delete("/{party_id}/publish", status_code=status.HTTP_204_NO_CONTENT)
def unpublish_party(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    membership=Depends(require_party_role({PartyRole.HOST})),
) -> None:
    # Social-Graph-Phase-8: Name + Veröffentlichungs-Status VOR dem
    # Hard-Delete lesen; nur wenn tatsächlich veröffentlicht war, feuert die
    # Absage-Notification (kein Spam bei doppeltem Unpublish).
    was_published = discover_storage.get_publication(db_path, party_id) is not None
    party = party_storage.get_party(db_path, party_id)
    discover_storage.unpublish_party(db_path, party_id)
    if was_published and party is not None:
        _notify_event_cancelled(db_path, party, membership.user_id)


@router.post("/{party_id}/cover-image", response_model=PartyPublic)
async def upload_party_cover_image(
    party_id: str,
    file: UploadFile,
    db_path: Path = Depends(get_db_path),
    media_dir: Path = Depends(get_media_dir),
    _membership=Depends(require_party_role({PartyRole.HOST})),
) -> PartyPublic:
    """Party-Cover-Bild ("Party-Motto"-Foto fürs Discover-Deck) - identisches
    Pillow-Verify+Re-Encode-Muster wie ``me.py::upload_profile_image`` (fester
    serverseitiger Dateiname, nie der Client-Dateiname/-Content-Type), nur
    unter einem eigenen ``party_images``-Unterordner desselben ``/media``-
    Mounts (kein neues StaticFiles-Mount/Setting nötig)."""
    raw = await file.read()
    if len(raw) > _MAX_COVER_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Cover image too large.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")

    party_images_dir = media_dir.parent / "party_images"
    party_images_dir.mkdir(parents=True, exist_ok=True)
    destination = party_images_dir / f"{party_id}.jpg"
    image.save(destination, format="JPEG")

    relative_path = f"party_images/{party_id}.jpg"
    party_storage.set_cover_image(db_path, party_id, relative_path)
    party = party_storage.get_party(db_path, party_id)
    return _to_party_public(
        party, discover_storage.get_publication(db_path, party_id), _host_is_verified(db_path, party.host_user_id)
    )


@router.get("/{party_id}/guests", response_model=PartyGuestsResponse)
def get_party_guests(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> PartyGuestsResponse:
    memberships = party_storage.list_memberships_for_party(db_path, party_id)
    guests = []
    for membership in memberships:
        user = user_storage.get_user_by_id(db_path, membership.user_id)
        if user is None:
            continue
        guests.append(
            GuestListEntry(
                user_id=user.id, display_name=user.display_name, email=user.email,
                role=membership.role.value, rsvp_status=membership.rsvp_status.value,
                joined_at=membership.joined_at,
            )
        )
    counts = party_storage.count_rsvp_statuses(db_path, party_id)
    return PartyGuestsResponse(guests=guests, counts=counts)


@router.post("/{party_id}/invitations", response_model=InvitationPublic, status_code=status.HTTP_201_CREATED)
def invite_guest(
    party_id: str,
    payload: InvitationCreate,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> InvitationPublic:
    invited_user = user_storage.get_user_by_email(db_path, payload.invited_user_email)
    if invited_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein User mit dieser E-Mail gefunden.")
    try:
        invitation = invitation_storage.create_invitation(
            db_path, uuid.uuid4().hex, party_id, current_user.id, invited_user.id,
            invitation_message=payload.invitation_message,
        )
    except invitation_storage.InvitationAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Einladung existiert bereits.")
    party = party_storage.get_party(db_path, party_id)
    party_name = party.name if party is not None else party_id
    notification_storage.create_notification(
        db_path, uuid.uuid4().hex, invited_user.id, party_id, "invitation",
        f"You've been invited to {party_name}.",
    )
    return InvitationPublic(
        id=invitation.id, party_id=invitation.party_id, host_user_id=invitation.host_user_id,
        invited_user_id=invitation.invited_user_id, status=invitation.status.value,
        invitation_message=invitation.invitation_message, version=invitation.version,
        created_at=invitation.created_at, viewed_at=invitation.viewed_at, responded_at=invitation.responded_at,
    )


@router.post("/{party_id}/invitations/friends", response_model=FriendInviteResponse)
def invite_friends(
    party_id: str,
    payload: FriendInviteRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST, PartyRole.CO_HOST})),
) -> FriendInviteResponse:
    """Social-Graph-Phase-2: Batch-Einladung aus dem Freundeskreis - EIN
    schlechter Eintrag (kein Freund, bereits Mitglied) bricht den Batch
    NICHT ab, jede ID bekommt ihr eigenes Ergebnis (siehe
    ``FriendInviteResponse``-Docstring). ``are_friends`` wird IMMER geprüft,
    die vom Client behauptete Freundes-Auswahl wird nie vertraut."""
    party = party_storage.get_party(db_path, party_id)
    party_name = party.name if party is not None else party_id
    results: list[FriendInviteResultItem] = []
    for friend_id in payload.friend_user_ids:
        if not friendships.are_friends(db_path, current_user.id, friend_id):
            results.append(FriendInviteResultItem(user_id=friend_id, status="not_a_friend"))
            continue
        if party_storage.get_membership(db_path, party_id, friend_id) is not None:
            results.append(FriendInviteResultItem(user_id=friend_id, status="already_member"))
            continue
        try:
            invitation = invitation_storage.create_invitation(
                db_path, uuid.uuid4().hex, party_id, current_user.id, friend_id,
            )
        except invitation_storage.InvitationAlreadyExistsError:
            results.append(FriendInviteResultItem(user_id=friend_id, status="already_invited"))
            continue
        notification_storage.create_notification(
            db_path, uuid.uuid4().hex, friend_id, party_id, "invitation",
            f"You've been invited to {party_name}.",
        )
        results.append(FriendInviteResultItem(user_id=friend_id, status="invited", invitation_id=invitation.id))
    return FriendInviteResponse(results=results)


@router.post("/{party_id}/co-hosts", response_model=CoHostPromoteResponse)
def promote_co_host(
    party_id: str,
    payload: CoHostPromoteRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    _membership=Depends(require_party_role({PartyRole.HOST})),
) -> CoHostPromoteResponse:
    """Social-Graph-Phase-2: Co-Host-Beförderung ist bewusst NUR dem Host
    vorbehalten (nicht auch Co-Hosts, wie beim generischen Invite) - ein
    Co-Host, der selbst weitere Co-Hosts ernennen kann, ist eine
    Privilegien-Eskalation, die dieses kleine App-Modell nicht braucht.
    Freundschafts-unabhängig: das Ziel muss KEIN Freund des Hosts sein,
    nur bereits akzeptiertes Party-Mitglied (Mobile-UI schlägt Freunde nur
    als bequeme Vorauswahl vor, siehe Plan)."""
    if payload.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Du kannst dich nicht selbst befördern.")
    target = party_storage.get_membership(db_path, party_id, payload.user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dieser User ist kein Mitglied dieser Party.")
    if target.role == PartyRole.HOST:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der Host kann nicht befördert werden.")
    if target.role == PartyRole.CO_HOST:
        return CoHostPromoteResponse(user_id=payload.user_id, party_id=party_id, role="co_host", already_co_host=True)
    if target.rsvp_status != RsvpStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieser Gast muss die Einladung zuerst annehmen, bevor er Co-Host werden kann.",
        )
    party_storage.upsert_membership(db_path, party_id, payload.user_id, PartyRole.CO_HOST, target.rsvp_status)
    party = party_storage.get_party(db_path, party_id)
    party_name = party.name if party is not None else party_id
    notification_storage.create_notification(
        db_path, uuid.uuid4().hex, payload.user_id, party_id, "co_host_promoted",
        f"You're now a co-host of {party_name}.",
    )
    return CoHostPromoteResponse(user_id=payload.user_id, party_id=party_id, role="co_host")
