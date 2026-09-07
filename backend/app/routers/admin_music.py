from __future__ import annotations

from fastapi import APIRouter, Depends

import event_theme
import music_engine.admin_settings as music_admin_settings
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from accounts.domain import PartyMembership, PartyRole
from backend.app.core.auth import require_party_role
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_db_path, get_music_catalog, get_music_occasions
from backend.app.schemas.admin import ArtistOverrideCreate, MusicSettingsUpdate, TrackOverrideCreate
from music_engine.domain import MusicCatalog, MusicOccasionProfile
from music_engine.engine import plan_party_music
from music_engine.legacy_adapter import raw_song_requests_from_responses
from music_engine.occasions import get_music_occasion

router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/music", tags=["admin"])

_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})


@router.get("/settings")
def get_music_settings(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    return to_jsonable(music_admin_settings.get_admin_music_settings(db_path, party_id))


@router.post("/settings")
def save_music_settings(
    party_id: str,
    payload: MusicSettingsUpdate,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    settings = music_admin_settings.get_admin_music_settings(db_path, party_id)
    settings.party_intensity = payload.party_intensity
    settings.mainstream_discovery = payload.mainstream_discovery
    settings.guest_request_priority = payload.guest_request_priority
    settings.explicit_allowed = payload.explicit_allowed
    settings.max_tracks_per_artist = payload.max_tracks_per_artist
    music_admin_settings.save_admin_music_settings(db_path, party_id, settings)
    return {"status": "ok"}


@router.get("/track-overrides")
def list_track_overrides(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    return to_jsonable(music_admin_settings.get_track_overrides(db_path, party_id))


@router.post("/track-overrides")
def set_track_override(
    party_id: str,
    payload: TrackOverrideCreate,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    music_admin_settings.set_track_override(db_path, party_id, payload.track_id, payload.status)
    return {"status": "ok"}


@router.get("/artist-overrides")
def list_artist_overrides(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    return to_jsonable(music_admin_settings.get_artist_overrides(db_path, party_id))


@router.post("/artist-overrides")
def set_artist_override(
    party_id: str,
    payload: ArtistOverrideCreate,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    music_admin_settings.set_artist_override(db_path, party_id, payload.artist_id, payload.status)
    return {"status": "ok"}


@router.post("/generate-playlist")
def generate_playlist(
    party_id: str,
    db_path=Depends(get_db_path),
    catalog: MusicCatalog = Depends(get_music_catalog),
    occasions: dict[str, MusicOccasionProfile] = Depends(get_music_occasions),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    settings = event_theme.get_party_settings(db_path, party_id)
    responses = response_storage.load_responses(db_path, party_id)
    music_settings = music_admin_settings.get_admin_music_settings(db_path, party_id)
    occasion_id = event_theme.resolve_occasion_id(settings["event_type"])
    occasion_profile = get_music_occasion(occasion_id, occasions)
    raw_requests = raw_song_requests_from_responses(responses)
    track_overrides = music_admin_settings.get_track_overrides(db_path, party_id)
    artist_overrides = music_admin_settings.get_artist_overrides(db_path, party_id)
    derived_context = context_orchestration.get_derived_party_context(db_path, party_id, settings, len(responses))

    result = plan_party_music(
        raw_song_requests=raw_requests,
        party_duration_minutes=settings["party_duration_hours"] * 60.0,
        occasion_profile=occasion_profile,
        admin_settings=music_settings,
        catalog=catalog,
        admin_track_overrides=track_overrides,
        admin_artist_overrides=artist_overrides,
        derived_context=derived_context,
    )
    body = to_jsonable(result)
    # Zusatzinfo pro Slot (Spec-Ergebnis kennt nur track_id) - mirroring
    # `catalog.get_track(slot.track_id)` in `render_music_playlist_section`,
    # spart der Flutter-Seite einen eigenen Katalog-Lookup.
    for slot_json, slot in zip(body["playlist"], result.playlist):
        track = catalog.get_track(slot.track_id)
        slot_json["track_title"] = track.title if track else slot.track_id
        slot_json["track_artist"] = track.artist if track else ""
    return body
