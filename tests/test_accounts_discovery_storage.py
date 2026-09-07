"""Pytest-Unit-Tests für ``accounts/discovery_storage.py`` (Onboarding-Spec,
Phase 6). Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst
um eine pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import pytest

import accounts.discovery_storage as discovery_storage
from accounts.domain import UserArtistPreference, UserDiscoveryPreferences, UserMusicPreference


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "discovery_test.db"
    discovery_storage.init_discovery_storage(path)
    return path


def test_get_discovery_preferences_none_wenn_nicht_angelegt(db_path):
    assert discovery_storage.get_discovery_preferences(db_path, "user-1") is None


def test_upsert_discovery_preferences_erstellt_und_aktualisiert(db_path):
    prefs = UserDiscoveryPreferences(
        user_id="user-1",
        discovery_radius_km=15.0,
        discovery_city="Berlin",
        preferred_days=["friday", "saturday"],
        mainstream_discovery=0.3,
    )
    saved = discovery_storage.upsert_discovery_preferences(db_path, "user-1", prefs)
    assert saved.discovery_radius_km == 15.0
    assert saved.discovery_city == "Berlin"
    assert saved.preferred_days == ["friday", "saturday"]

    prefs.discovery_radius_km = 30.0
    updated = discovery_storage.upsert_discovery_preferences(db_path, "user-1", prefs)
    assert updated.discovery_radius_km == 30.0
    # Upsert darf keinen zweiten Datensatz anlegen.
    assert discovery_storage.get_discovery_preferences(db_path, "user-1").discovery_radius_km == 30.0


def test_replace_music_preferences_ersetzt_vollstaendig(db_path):
    assert discovery_storage.get_music_preferences(db_path, "user-1") == []

    music = discovery_storage.replace_music_preferences(
        db_path,
        "user-1",
        [
            UserMusicPreference(user_id="user-1", genre_id="tech_house", preference_level="love"),
            UserMusicPreference(user_id="user-1", genre_id="pop", preference_level="like"),
        ],
    )
    assert {m.genre_id for m in music} == {"tech_house", "pop"}

    music2 = discovery_storage.replace_music_preferences(
        db_path, "user-1", [UserMusicPreference(user_id="user-1", genre_id="jazz", preference_level="neutral")]
    )
    assert len(music2) == 1
    assert music2[0].genre_id == "jazz"


def test_replace_artist_preferences_ersetzt_vollstaendig(db_path):
    artists = discovery_storage.replace_artist_preferences(
        db_path,
        "user-1",
        [
            UserArtistPreference(
                user_id="user-1", artist_reference="manual:daft-punk", display_name="Daft Punk", preference_level="love"
            )
        ],
    )
    assert len(artists) == 1
    assert artists[0].display_name == "Daft Punk"


def test_replace_event_interests_andere_kategorie_bleibt_unangetastet(db_path):
    interests = discovery_storage.replace_event_interests(db_path, "user-1", "event_type", ["concert", "festival"])
    assert {i.item_id for i in interests} == {"concert", "festival"}

    tags = discovery_storage.replace_event_interests(db_path, "user-1", "interest_tag", ["late_night"])
    assert len(tags) == 1

    assert len(discovery_storage.get_event_interests(db_path, "user-1", category="event_type")) == 2
    assert len(discovery_storage.get_event_interests(db_path, "user-1")) == 3
