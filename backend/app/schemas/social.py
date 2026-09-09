"""Pydantic-Schemas für den Social Graph (Social-Graph-Phase-1: Friends).

Mirrort die Konvention von ``backend/app/schemas/discover.py``/``auth.py``
(reine ``BaseModel``-DTOs). Alle Response-Schemas hier lassen ``email``
bewusst WEG (anders als ``schemas/auth.py::UserPublic``) - Spec §26 verbietet
explizit, private Account-Daten (E-Mail, Telefon, Geburtsdatum, Standort,
...) über Friend Search/Social Profile preiszugeben."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

_FRIEND_LIST_VISIBILITY_VALUES = {"nobody", "friends", "everyone"}
# Bewusst nur zwei Stufen (Social-Graph-Phase-3) - die vom AUFGABE-Spec
# vorgeschlagene dritte Stufe "Friends of Friends" wurde für diese
# "Polish"-Phase explizit gestrichen (siehe accounts/domain.py::UserProfile-
# Docstring): sie bräuchte eine Zwei-Hop-Graph-Query, ein deutlich größerer
# Aufwand als der Rest dieser Phase.
_FRIEND_REQUEST_PRIVACY_VALUES = {"nobody", "everyone"}


class SocialProfilePublic(BaseModel):
    user_id: str
    username: str
    display_name: str
    profile_image: str
    relationship_status: str  # "self" | "friends" | "request_sent" | "request_received" | "blocked" | "none"
    mutual_friend_count: int = 0


class UserSearchResultPublic(BaseModel):
    user_id: str
    username: str
    display_name: str
    profile_image: str
    relationship_status: str
    mutual_friend_count: int = 0


class UserSearchResponse(BaseModel):
    results: list[UserSearchResultPublic]


class FriendPublic(BaseModel):
    user_id: str
    username: str
    display_name: str
    profile_image: str
    friends_since: datetime


class FriendRequestPublic(BaseModel):
    """Denormalisiert die Anzeige-Felder der JEWEILS ANDEREN Partei direkt
    auf die Zeile (mirrort ``DiscoverCardPublic.host_display_name`` in
    ``schemas/discover.py``) statt ein verschachteltes ``UserPublic``
    zurückzugeben - Client muss so nie zusätzlich nachladen, um Requests
    anzuzeigen."""

    id: str
    direction: str  # "incoming" | "outgoing"
    status: str
    version: int
    other_user_id: str
    other_username: str
    other_display_name: str
    other_profile_image: str
    created_at: datetime
    responded_at: datetime | None = None


class FriendRequestsInboxResponse(BaseModel):
    incoming: list[FriendRequestPublic]
    outgoing: list[FriendRequestPublic]


class FriendRequestCreateResponse(BaseModel):
    request: FriendRequestPublic
    merged: bool


class UserBlockResponse(BaseModel):
    user_id: str
    blocked: bool


class SocialPrivacyPublic(BaseModel):
    """Social-Graph-Phase-3 - Verhaltens-Policies, die steuern, was ANDERE
    User über einen sehen/tun dürfen (siehe
    ``accounts/domain.py::UserProfile``-Docstring)."""

    friend_list_visibility: str
    friend_request_privacy: str
    discoverable_by_username: bool
    discoverable_by_name: bool


class SocialPrivacyUpdateRequest(BaseModel):
    """``None`` bedeutet je Feld "unverändert lassen" (gleiche Konvention
    wie ``ProfileUpdateRequest``)."""

    friend_list_visibility: str | None = None
    friend_request_privacy: str | None = None
    discoverable_by_username: bool | None = None
    discoverable_by_name: bool | None = None

    @field_validator("friend_list_visibility")
    @classmethod
    def _gueltige_friend_list_visibility(cls, value: str | None) -> str | None:
        if value is not None and value not in _FRIEND_LIST_VISIBILITY_VALUES:
            raise ValueError("friend_list_visibility muss 'nobody', 'friends' oder 'everyone' sein.")
        return value

    @field_validator("friend_request_privacy")
    @classmethod
    def _gueltige_friend_request_privacy(cls, value: str | None) -> str | None:
        if value is not None and value not in _FRIEND_REQUEST_PRIVACY_VALUES:
            raise ValueError("friend_request_privacy muss 'nobody' oder 'everyone' sein.")
        return value
