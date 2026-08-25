from __future__ import annotations

from pydantic import BaseModel, Field


class PartySettingsUpdate(BaseModel):
    event_type: str
    party_name: str = ""
    party_date: str = ""  # ISO "YYYY-MM-DD", darf leer bleiben
    party_start_time: str = ""  # "HH:MM", darf leer bleiben
    party_duration_hours: float = 7.0
    party_location: str = ""


class PartyContextUpdate(BaseModel):
    """Mirroring der in ``render_party_context_section`` admin-erfassten
    Felder (Anlass/Datum/Startzeit/Dauer/Gästezahl kommen NICHT hierüber,
    siehe ``get_party_context``, EINE Quelle der Wahrheit)."""

    location_type: str = "other"
    indoor_outdoor: str = "outdoor"
    country_code: str = ""
    has_grill: bool = False
    has_kitchen: bool = False
    has_fridge: bool = False
    has_freezer: bool = False
    has_ice_machine: bool = False
    has_bar: bool = False
    has_coffee_machine: bool = False
    has_power: bool = False
    has_running_water: bool = False
    dancing_possible: bool = False
    neighbors_sensitive: bool = False
    music_volume_limit: str | None = None
    self_service: bool = True
    seating_ratio: float | None = None  # 0.0 - 1.0
    weather_condition: str | None = None
    expected_temperature_c: float | None = None


class PartyContextOverrideCreate(BaseModel):
    key: str
    value: str
    reason: str | None = None


class CatalogCurationUpdate(BaseModel):
    enabled: bool = False
    curated_item_ids: list[str] = Field(default_factory=list)


class MusicSettingsUpdate(BaseModel):
    """Nur die im Admin-UI editierbare Teilmenge von ``AdminMusicSettings``
    (Read-Modify-Write auf die restlichen Felder, mirroring
    ``render_music_playlist_section``)."""

    party_intensity: float = 0.5
    mainstream_discovery: float = 0.7
    guest_request_priority: float = 0.7
    explicit_allowed: bool = True
    max_tracks_per_artist: int = 3


class TrackOverrideCreate(BaseModel):
    track_id: str
    status: str


class ArtistOverrideCreate(BaseModel):
    artist_id: str
    status: str
