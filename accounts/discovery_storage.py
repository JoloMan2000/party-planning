"""SQLite-Persistenz für den Explicit-Discovery-Preferences-Layer
(Onboarding-Spec, Phase 6 des Account-basierten Pivots).

Mirrort exakt das etablierte Muster aus ``accounts/user_storage.py``/
``accounts/profile_storage.py``: kurzlebige
``with sqlite3.connect(db_path) as conn:``-Blöcke, ``CREATE TABLE IF NOT
EXISTS``, ein ``init_*(db_path)`` pro Modul, ausführbarer
``__main__``-Selbsttest.

Musik-Genres/Artists/Event-Interessen sind Listen (nicht Skalarwerte wie
Radius/Stadt) - jede Liste wird per "delete-then-insert" in derselben
Transaktion ersetzt (``replace_*``), damit ein PUT immer den vollständigen
gewünschten Endzustand herstellt (kein Client-seitiges Diffing nötig)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from accounts.domain import ExplicitDiscoveryPreference, UserArtistPreference, UserDiscoveryPreferences, UserMusicPreference


def init_discovery_storage(db_path: str | Path) -> None:
    """Legt alle Discovery-Preferences-Tabellen an, falls nicht vorhanden.
    Idempotent, sicher bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_discovery_preferences (
                user_id TEXT PRIMARY KEY,
                discovery_radius_km REAL NOT NULL DEFAULT 25.0,
                allow_major_events_outside_radius INTEGER NOT NULL DEFAULT 0,
                discovery_city TEXT NOT NULL DEFAULT '',
                discovery_lat REAL,
                discovery_lon REAL,
                preferred_days TEXT NOT NULL DEFAULT '',
                preferred_dayparts TEXT NOT NULL DEFAULT '',
                price_preference TEXT NOT NULL DEFAULT '',
                mainstream_discovery REAL NOT NULL DEFAULT 0.5,
                personalized_recommendations_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_music_preferences (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                genre_id TEXT NOT NULL,
                preference_level TEXT NOT NULL DEFAULT 'like',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_music_preferences_user ON user_music_preferences(user_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_artist_preferences (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                artist_reference TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                preference_level TEXT NOT NULL DEFAULT 'like',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_artist_preferences_user ON user_artist_preferences(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS explicit_discovery_preferences (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                item_id TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_explicit_discovery_preferences_user "
            "ON explicit_discovery_preferences(user_id)"
        )


def _encode_list(values: list[str]) -> str:
    return ",".join(values)


def _decode_list(raw: str) -> list[str]:
    return [v for v in raw.split(",") if v]


def _row_to_discovery_preferences(row: sqlite3.Row) -> UserDiscoveryPreferences:
    return UserDiscoveryPreferences(
        user_id=row["user_id"],
        discovery_radius_km=row["discovery_radius_km"],
        allow_major_events_outside_radius=bool(row["allow_major_events_outside_radius"]),
        discovery_city=row["discovery_city"] or "",
        discovery_lat=row["discovery_lat"],
        discovery_lon=row["discovery_lon"],
        preferred_days=_decode_list(row["preferred_days"] or ""),
        preferred_dayparts=_decode_list(row["preferred_dayparts"] or ""),
        price_preference=row["price_preference"] or "",
        mainstream_discovery=row["mainstream_discovery"],
        personalized_recommendations_enabled=bool(row["personalized_recommendations_enabled"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def get_discovery_preferences(db_path: str | Path, user_id: str) -> UserDiscoveryPreferences | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM user_discovery_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
    return _row_to_discovery_preferences(row) if row is not None else None


def upsert_discovery_preferences(
    db_path: str | Path, user_id: str, preferences: UserDiscoveryPreferences
) -> UserDiscoveryPreferences:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_discovery_preferences
                (user_id, discovery_radius_km, allow_major_events_outside_radius, discovery_city,
                 discovery_lat, discovery_lon, preferred_days, preferred_dayparts, price_preference,
                 mainstream_discovery, personalized_recommendations_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                discovery_radius_km = excluded.discovery_radius_km,
                allow_major_events_outside_radius = excluded.allow_major_events_outside_radius,
                discovery_city = excluded.discovery_city,
                discovery_lat = excluded.discovery_lat,
                discovery_lon = excluded.discovery_lon,
                preferred_days = excluded.preferred_days,
                preferred_dayparts = excluded.preferred_dayparts,
                price_preference = excluded.price_preference,
                mainstream_discovery = excluded.mainstream_discovery,
                personalized_recommendations_enabled = excluded.personalized_recommendations_enabled,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                preferences.discovery_radius_km,
                int(preferences.allow_major_events_outside_radius),
                preferences.discovery_city,
                preferences.discovery_lat,
                preferences.discovery_lon,
                _encode_list(preferences.preferred_days),
                _encode_list(preferences.preferred_dayparts),
                preferences.price_preference,
                preferences.mainstream_discovery,
                int(preferences.personalized_recommendations_enabled),
                now,
            ),
        )
    result = get_discovery_preferences(db_path, user_id)
    assert result is not None
    return result


def _row_to_music_preference(row: sqlite3.Row) -> UserMusicPreference:
    return UserMusicPreference(
        user_id=row["user_id"],
        genre_id=row["genre_id"],
        preference_level=row["preference_level"],
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_music_preferences(db_path: str | Path, user_id: str) -> list[UserMusicPreference]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM user_music_preferences WHERE user_id = ? ORDER BY created_at", (user_id,)
        ).fetchall()
    return [_row_to_music_preference(row) for row in rows]


def replace_music_preferences(
    db_path: str | Path, user_id: str, preferences: list[UserMusicPreference]
) -> list[UserMusicPreference]:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM user_music_preferences WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO user_music_preferences (id, user_id, genre_id, preference_level, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (uuid.uuid4().hex, user_id, p.genre_id, p.preference_level, p.source, now)
                for p in preferences
            ],
        )
    return get_music_preferences(db_path, user_id)


def _row_to_artist_preference(row: sqlite3.Row) -> UserArtistPreference:
    return UserArtistPreference(
        user_id=row["user_id"],
        artist_reference=row["artist_reference"],
        display_name=row["display_name"],
        preference_level=row["preference_level"],
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_artist_preferences(db_path: str | Path, user_id: str) -> list[UserArtistPreference]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM user_artist_preferences WHERE user_id = ? ORDER BY created_at", (user_id,)
        ).fetchall()
    return [_row_to_artist_preference(row) for row in rows]


def replace_artist_preferences(
    db_path: str | Path, user_id: str, preferences: list[UserArtistPreference]
) -> list[UserArtistPreference]:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM user_artist_preferences WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO user_artist_preferences "
            "(id, user_id, artist_reference, display_name, preference_level, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (uuid.uuid4().hex, user_id, p.artist_reference, p.display_name, p.preference_level, p.source, now)
                for p in preferences
            ],
        )
    return get_artist_preferences(db_path, user_id)


def _row_to_explicit_preference(row: sqlite3.Row) -> ExplicitDiscoveryPreference:
    return ExplicitDiscoveryPreference(
        id=row["id"],
        user_id=row["user_id"],
        category=row["category"],
        item_id=row["item_id"],
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_event_interests(db_path: str | Path, user_id: str, category: str | None = None) -> list[ExplicitDiscoveryPreference]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if category is not None:
            rows = conn.execute(
                "SELECT * FROM explicit_discovery_preferences WHERE user_id = ? AND category = ? ORDER BY created_at",
                (user_id, category),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM explicit_discovery_preferences WHERE user_id = ? ORDER BY created_at", (user_id,)
            ).fetchall()
    return [_row_to_explicit_preference(row) for row in rows]


def replace_event_interests(
    db_path: str | Path, user_id: str, category: str, item_ids: list[str]
) -> list[ExplicitDiscoveryPreference]:
    """Ersetzt alle Einträge einer ``category`` (z.B. ``"event_type"``) für
    diesen User - andere Kategorien bleiben unangetastet."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM explicit_discovery_preferences WHERE user_id = ? AND category = ?", (user_id, category)
        )
        conn.executemany(
            "INSERT INTO explicit_discovery_preferences (id, user_id, category, item_id, source, created_at) "
            "VALUES (?, ?, ?, ?, 'manual', ?)",
            [(uuid.uuid4().hex, user_id, category, item_id, now) for item_id in item_ids],
        )
    return get_event_interests(db_path, user_id, category=category)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_discovery_storage.db"
        user_id = "user-1"
        init_discovery_storage(db_path)
        init_discovery_storage(db_path)  # idempotent, darf nicht crashen

        assert get_discovery_preferences(db_path, user_id) is None

        prefs = UserDiscoveryPreferences(
            user_id=user_id,
            discovery_radius_km=15.0,
            discovery_city="Berlin",
            preferred_days=["friday", "saturday"],
            mainstream_discovery=0.3,
        )
        saved = upsert_discovery_preferences(db_path, user_id, prefs)
        assert saved.discovery_radius_km == 15.0
        assert saved.discovery_city == "Berlin"
        assert saved.preferred_days == ["friday", "saturday"]

        # Upsert erneut - muss updaten statt einen zweiten Datensatz anzulegen.
        prefs.discovery_radius_km = 30.0
        updated = upsert_discovery_preferences(db_path, user_id, prefs)
        assert updated.discovery_radius_km == 30.0

        assert get_music_preferences(db_path, user_id) == []
        music = replace_music_preferences(
            db_path,
            user_id,
            [
                UserMusicPreference(user_id=user_id, genre_id="tech_house", preference_level="love"),
                UserMusicPreference(user_id=user_id, genre_id="pop", preference_level="like"),
            ],
        )
        assert {m.genre_id for m in music} == {"tech_house", "pop"}

        # Replace muss den alten Zustand komplett ersetzen, nicht anhängen.
        music2 = replace_music_preferences(
            db_path, user_id, [UserMusicPreference(user_id=user_id, genre_id="jazz", preference_level="neutral")]
        )
        assert len(music2) == 1
        assert music2[0].genre_id == "jazz"

        artists = replace_artist_preferences(
            db_path,
            user_id,
            [UserArtistPreference(user_id=user_id, artist_reference="manual:daft-punk", display_name="Daft Punk", preference_level="love")],
        )
        assert len(artists) == 1
        assert artists[0].display_name == "Daft Punk"

        interests = replace_event_interests(db_path, user_id, "event_type", ["concert", "festival"])
        assert {i.item_id for i in interests} == {"concert", "festival"}
        tags = replace_event_interests(db_path, user_id, "interest_tag", ["late_night"])
        assert len(tags) == 1
        # Andere Kategorie darf unangetastet bleiben.
        assert len(get_event_interests(db_path, user_id, category="event_type")) == 2

        print("accounts/discovery_storage.py sanity check OK.")
