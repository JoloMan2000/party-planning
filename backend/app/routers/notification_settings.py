"""Pro-User-Notification-Kategorie-Schalter (Social-Graph-Phase-8, Spec
§109/§156).

Eigener Router (eine Verantwortlichkeit pro Datei), exaktes Pendant zu
``backend/app/routers/discovery_preferences.py``: gleiches
``/api/v1/me``-Präfix, ``_to_public``-Mapper, GET liefert bei fehlender
Zeile die Dataclass-Defaults, PUT ist Full-Replace (der Client hält immer
alle fünf Werte)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

import accounts.notification_settings_storage as notification_settings_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.notifications import NotificationSettingsPublic, NotificationSettingsUpdateRequest

router = APIRouter(prefix="/api/v1/me", tags=["notification-settings"])


def _to_public(settings) -> NotificationSettingsPublic:
    return NotificationSettingsPublic(
        friend_requests=settings.friend_requests,
        party_invitations=settings.party_invitations,
        organizer_updates=settings.organizer_updates,
        followed_event_updates=settings.followed_event_updates,
        nearby_discover=settings.nearby_discover,
    )


@router.get("/notification-settings", response_model=NotificationSettingsPublic)
def get_notification_settings(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> NotificationSettingsPublic:
    return _to_public(notification_settings_storage.get_notification_settings(db_path, current_user.id))


@router.put("/notification-settings", response_model=NotificationSettingsPublic)
def put_notification_settings(
    payload: NotificationSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> NotificationSettingsPublic:
    saved = notification_settings_storage.upsert_notification_settings(
        db_path,
        current_user.id,
        friend_requests=payload.friend_requests,
        party_invitations=payload.party_invitations,
        organizer_updates=payload.organizer_updates,
        followed_event_updates=payload.followed_event_updates,
        nearby_discover=payload.nearby_discover,
    )
    return _to_public(saved)
