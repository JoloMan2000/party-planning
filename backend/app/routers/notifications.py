"""In-App-Notification-Inbox (Phase 5) - Poll-basiert, kein echtes Push.

TODO: Auf echtes Push (FCM/APNs) umstellen, sobald ein Backend-Push-Provider
gewählt wurde. Bis dahin pollt der Flutter-Client `GET /me/notifications`
periodisch (siehe `mobile/lib/state/auth_providers.dart`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

import accounts.notification_storage as notification_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path
from backend.app.schemas.notifications import NotificationPublic

router = APIRouter(prefix="/api/v1/me/notifications", tags=["notifications"])


def _to_public(notification) -> NotificationPublic:
    return NotificationPublic(
        id=notification.id, party_id=notification.party_id, kind=notification.kind,
        message=notification.message, created_at=notification.created_at, read=notification.read,
    )


@router.get("", response_model=list[NotificationPublic])
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> list[NotificationPublic]:
    notifications = notification_storage.list_notifications(db_path, current_user.id, limit=limit)
    return [_to_public(n) for n in notifications]


@router.post("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> NotificationPublic:
    notification = notification_storage.mark_read(db_path, notification_id, current_user.id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification nicht gefunden.")
    return _to_public(notification)
