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
