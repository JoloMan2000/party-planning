from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationPublic(BaseModel):
    id: str
    party_id: str | None
    kind: str
    message: str
    created_at: datetime
    read: bool


class NotificationSettingsPublic(BaseModel):
    """Social-Graph-Phase-8 (Spec §109/§156) - die fünf
    Notification-Kategorie-Schalter eines Users."""

    friend_requests: bool
    party_invitations: bool
    organizer_updates: bool
    followed_event_updates: bool
    nearby_discover: bool


class NotificationSettingsUpdateRequest(BaseModel):
    """Full-Replace (mirrort ``DiscoveryPreferencesUpdateRequest``): der
    Client sendet stets alle fünf Werte; ein weggelassenes Feld fällt auf
    den Default ``True`` zurück."""

    friend_requests: bool = True
    party_invitations: bool = True
    organizer_updates: bool = True
    followed_event_updates: bool = True
    nearby_discover: bool = True
