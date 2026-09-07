from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SpotifyConnectResponse(BaseModel):
    authorize_url: str


class SpotifyStatusResponse(BaseModel):
    connected: bool
    spotify_user_id: str | None = None
    connected_at: datetime | None = None
