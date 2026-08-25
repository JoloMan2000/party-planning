"""Äquivalenz-Test: die Generate-Playlist-API muss exakt dasselbe Ergebnis
liefern wie ein direkter Aufruf von ``plan_party_music`` mit denselben
Eingaben (Phase-1-Plan Schritt 7)."""

from __future__ import annotations

import event_theme
import music_engine.admin_settings as music_admin_settings
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_music_catalog, get_music_occasions
from music_engine.engine import plan_party_music
from music_engine.legacy_adapter import raw_song_requests_from_responses
from music_engine.occasions import get_music_occasion


def test_generate_playlist_api_entspricht_direktem_plan_party_music(api_client, admin_headers):
    response_storage.save_response(
        api_client.db_path,
        name="Anna",
        start_time="18:30",
        drinks=[],
        drinks_freetext="",
        food=[],
        food_freetext="",
        songs=[{"artist": "Queen", "title": "Bohemian Rhapsody"}],
    )

    resp = api_client.post("/api/v1/admin/music/generate-playlist", headers=admin_headers)
    assert resp.status_code == 200
    api_result = resp.json()

    settings = event_theme.get_party_settings(api_client.db_path)
    responses = response_storage.load_responses(api_client.db_path)
    music_settings = music_admin_settings.get_admin_music_settings(api_client.db_path)
    occasion_id = event_theme.resolve_occasion_id(settings["event_type"])
    occasion_profile = get_music_occasion(occasion_id, get_music_occasions())
    raw_requests = raw_song_requests_from_responses(responses)
    track_overrides = music_admin_settings.get_track_overrides(api_client.db_path)
    artist_overrides = music_admin_settings.get_artist_overrides(api_client.db_path)
    derived_context = context_orchestration.get_derived_party_context(api_client.db_path, settings, len(responses))

    expected = to_jsonable(
        plan_party_music(
            raw_song_requests=raw_requests,
            party_duration_minutes=settings["party_duration_hours"] * 60.0,
            occasion_profile=occasion_profile,
            admin_settings=music_settings,
            catalog=get_music_catalog(),
            admin_track_overrides=track_overrides,
            admin_artist_overrides=artist_overrides,
            derived_context=derived_context,
        )
    )

    assert api_result == expected
