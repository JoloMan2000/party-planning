"""Pydantic-Schemas für den Social Graph (Social-Graph-Phase-1: Friends).

Mirrort die Konvention von ``backend/app/schemas/discover.py``/``auth.py``
(reine ``BaseModel``-DTOs). Alle Response-Schemas hier lassen ``email``
bewusst WEG (anders als ``schemas/auth.py::UserPublic``) - Spec §26 verbietet
explizit, private Account-Daten (E-Mail, Telefon, Geburtsdatum, Standort,
...) über Friend Search/Social Profile preiszugeben."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SocialProfilePublic(BaseModel):
    user_id: str
    username: str
    display_name: str
    profile_image: str
    relationship_status: str  # "self" | "friends" | "request_sent" | "request_received" | "blocked" | "none"


class UserSearchResultPublic(BaseModel):
    user_id: str
    username: str
    display_name: str
    profile_image: str
    relationship_status: str


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
