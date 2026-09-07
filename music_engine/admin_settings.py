"""
Admin Music Settings & Overrides Storage (Spec §60-63).
============================================================

Persistenz für die admin-konfigurierbaren Steuerparameter der Music
Recommendation & Party Playlist Engine (``AdminMusicSettings``,
Spec §60/§61) sowie für Track-/Artist-Overrides (Spec §62/§63). Mirroring
des sqlite3-Single-Row-Upsert-Musters aus ``event_theme.py`` (dieses Modul
ist bewusst ebenfalls Streamlit-frei, reines sqlite3 + Dataclasses).

Verwendung ("Party Planning.py"):
    import music_engine.admin_settings as music_admin_settings

    music_admin_settings.init_music_admin_settings(DB_PATH)   # einmal beim App-Start
    settings = music_admin_settings.get_admin_music_settings(DB_PATH, party_id)
    music_admin_settings.save_admin_music_settings(DB_PATH, party_id, settings)

    track_overrides = music_admin_settings.get_track_overrides(DB_PATH, party_id)
    music_admin_settings.set_track_override(DB_PATH, party_id, "the_killers_mr_brightside", "must_play")
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from music_engine.domain import AdminArtistOverride, AdminMusicSettings, AdminTrackOverride

# Spec §62/§63: erlaubte Status-Werte je Override-Typ.
TRACK_OVERRIDE_STATUSES = ("must_play", "preferred", "neutral", "avoid", "banned")
ARTIST_OVERRIDE_STATUSES = ("preferred", "neutral", "avoid", "banned")

_SET_FIELDS = (
    "preferred_genres",
    "discouraged_genres",
    "banned_genres",
    "preferred_eras",
    "discouraged_eras",
)


def init_music_admin_settings(db_path: str | Path) -> None:
    """Legt die (Single-Row-)Tabelle 'music_admin_settings' sowie die
    Override-Tabellen an, falls sie noch nicht existieren, und fügt die
    Default-Einstellungszeile ein, falls noch keine vorhanden ist. Sicher
    bei jedem App-Start aufrufbar (mirroring event_theme.init_party_settings())."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS music_admin_settings (
                party_id TEXT PRIMARY KEY REFERENCES parties(id),
                playlist_duration_buffer REAL NOT NULL DEFAULT 0.08,
                party_intensity REAL NOT NULL DEFAULT 0.5,
                mainstream_discovery REAL NOT NULL DEFAULT 0.7,
                guest_request_priority REAL NOT NULL DEFAULT 0.7,
                explicit_allowed INTEGER NOT NULL DEFAULT 1,
                preferred_genres TEXT NOT NULL DEFAULT '[]',
                discouraged_genres TEXT NOT NULL DEFAULT '[]',
                banned_genres TEXT NOT NULL DEFAULT '[]',
                preferred_eras TEXT NOT NULL DEFAULT '[]',
                discouraged_eras TEXT NOT NULL DEFAULT '[]',
                max_tracks_per_artist INTEGER NOT NULL DEFAULT 3,
                exploration_share REAL NOT NULL DEFAULT 0.10,
                closing_style TEXT NOT NULL DEFAULT 'singalong',
                random_seed INTEGER NOT NULL DEFAULT 42
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS music_track_overrides (
                party_id TEXT NOT NULL REFERENCES parties(id),
                track_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'neutral',
                PRIMARY KEY (party_id, track_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS music_artist_overrides (
                party_id TEXT NOT NULL REFERENCES parties(id),
                artist_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'neutral',
                PRIMARY KEY (party_id, artist_id)
            )
            """
        )


def get_admin_music_settings(db_path: str | Path, party_id: str) -> AdminMusicSettings:
    """Liest die aktuellen Admin Music Settings für ``party_id``. Gibt bei
    fehlender Zeile (z.B. noch nie gespeichert) sicherheitshalber die reinen
    Dataclass-Defaults zurück - wirft nie."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM music_admin_settings WHERE party_id = ?", (party_id,)).fetchone()
    if row is None:
        return AdminMusicSettings()

    def _load_set(column: str) -> set[str]:
        try:
            return set(json.loads(row[column]))
        except (TypeError, ValueError, KeyError):
            return set()

    return AdminMusicSettings(
        playlist_duration_buffer=row["playlist_duration_buffer"],
        party_intensity=row["party_intensity"],
        mainstream_discovery=row["mainstream_discovery"],
        guest_request_priority=row["guest_request_priority"],
        explicit_allowed=bool(row["explicit_allowed"]),
        preferred_genres=_load_set("preferred_genres"),
        discouraged_genres=_load_set("discouraged_genres"),
        banned_genres=_load_set("banned_genres"),
        preferred_eras=_load_set("preferred_eras"),
        discouraged_eras=_load_set("discouraged_eras"),
        max_tracks_per_artist=row["max_tracks_per_artist"],
        exploration_share=row["exploration_share"],
        closing_style=row["closing_style"] or "singalong",
        random_seed=row["random_seed"],
    )


def save_admin_music_settings(db_path: str | Path, party_id: str, settings: AdminMusicSettings) -> None:
    """Speichert die Admin Music Settings für ``party_id`` (Upsert)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO music_admin_settings (
                party_id, playlist_duration_buffer, party_intensity, mainstream_discovery,
                guest_request_priority, explicit_allowed, preferred_genres,
                discouraged_genres, banned_genres, preferred_eras, discouraged_eras,
                max_tracks_per_artist, exploration_share, closing_style, random_seed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(party_id) DO UPDATE SET
                playlist_duration_buffer = excluded.playlist_duration_buffer,
                party_intensity = excluded.party_intensity,
                mainstream_discovery = excluded.mainstream_discovery,
                guest_request_priority = excluded.guest_request_priority,
                explicit_allowed = excluded.explicit_allowed,
                preferred_genres = excluded.preferred_genres,
                discouraged_genres = excluded.discouraged_genres,
                banned_genres = excluded.banned_genres,
                preferred_eras = excluded.preferred_eras,
                discouraged_eras = excluded.discouraged_eras,
                max_tracks_per_artist = excluded.max_tracks_per_artist,
                exploration_share = excluded.exploration_share,
                closing_style = excluded.closing_style,
                random_seed = excluded.random_seed
            """,
            (
                party_id,
                settings.playlist_duration_buffer,
                settings.party_intensity,
                settings.mainstream_discovery,
                settings.guest_request_priority,
                int(settings.explicit_allowed),
                json.dumps(sorted(settings.preferred_genres)),
                json.dumps(sorted(settings.discouraged_genres)),
                json.dumps(sorted(settings.banned_genres)),
                json.dumps(sorted(settings.preferred_eras)),
                json.dumps(sorted(settings.discouraged_eras)),
                settings.max_tracks_per_artist,
                settings.exploration_share,
                settings.closing_style,
                settings.random_seed,
            ),
        )


# --- Track-/Artist-Overrides (Spec §62/§63) --------------------------------


def get_track_overrides(db_path: str | Path, party_id: str) -> dict[str, AdminTrackOverride]:
    """Liefert alle gespeicherten Track-Overrides für ``party_id``, keyed by
    ``track_id``."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT track_id, status FROM music_track_overrides WHERE party_id = ?", (party_id,)
        ).fetchall()
    return {track_id: AdminTrackOverride(track_id=track_id, status=status) for track_id, status in rows}


def set_track_override(db_path: str | Path, party_id: str, track_id: str, status: str) -> None:
    """Setzt/aktualisiert den Override-Status eines Tracks für ``party_id``.
    ``status="neutral"`` löscht den Override wieder (spart Zeilen, "neutral"
    ist ohnehin der Default bei Abwesenheit einer Zeile)."""
    if status not in TRACK_OVERRIDE_STATUSES:
        status = "neutral"
    with sqlite3.connect(db_path) as conn:
        if status == "neutral":
            conn.execute(
                "DELETE FROM music_track_overrides WHERE party_id = ? AND track_id = ?", (party_id, track_id)
            )
        else:
            conn.execute(
                """
                INSERT INTO music_track_overrides (party_id, track_id, status) VALUES (?, ?, ?)
                ON CONFLICT(party_id, track_id) DO UPDATE SET status = excluded.status
                """,
                (party_id, track_id, status),
            )


def get_artist_overrides(db_path: str | Path, party_id: str) -> dict[str, AdminArtistOverride]:
    """Liefert alle gespeicherten Artist-Overrides für ``party_id``, keyed by
    ``artist_id`` (in dieser App: der Artist-Name, da kein separates
    Artist-ID-System existiert - analog zu ``guest_id`` in RawSongRequest)."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT artist_id, status FROM music_artist_overrides WHERE party_id = ?", (party_id,)
        ).fetchall()
    return {artist_id: AdminArtistOverride(artist_id=artist_id, status=status) for artist_id, status in rows}


def set_artist_override(db_path: str | Path, party_id: str, artist_id: str, status: str) -> None:
    """Setzt/aktualisiert den Override-Status eines Artists für ``party_id``
    (siehe ``set_track_override`` für die "neutral löscht Zeile"-Konvention)."""
    if status not in ARTIST_OVERRIDE_STATUSES:
        status = "neutral"
    with sqlite3.connect(db_path) as conn:
        if status == "neutral":
            conn.execute(
                "DELETE FROM music_artist_overrides WHERE party_id = ? AND artist_id = ?", (party_id, artist_id)
            )
        else:
            conn.execute(
                """
                INSERT INTO music_artist_overrides (party_id, artist_id, status) VALUES (?, ?, ?)
                ON CONFLICT(party_id, artist_id) DO UPDATE SET status = excluded.status
                """,
                (party_id, artist_id, status),
            )


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        _db_path = Path(tmp_dir) / "music_admin_settings_test.db"
        _party_id = "test-party"

        init_music_admin_settings(_db_path)
        _settings = get_admin_music_settings(_db_path, _party_id)
        assert _settings.max_tracks_per_artist == 3
        assert _settings.closing_style == "singalong"
        print(f"Defaults after init: {_settings}")

        _settings.party_intensity = 0.9
        _settings.mainstream_discovery = 0.2
        _settings.preferred_genres = {"house", "edm"}
        _settings.banned_genres = {"schlager"}
        _settings.closing_style = "big_finish"
        save_admin_music_settings(_db_path, _party_id, _settings)

        _reloaded = get_admin_music_settings(_db_path, _party_id)
        assert _reloaded.party_intensity == 0.9
        assert _reloaded.preferred_genres == {"house", "edm"}
        assert _reloaded.banned_genres == {"schlager"}
        assert _reloaded.closing_style == "big_finish"
        print(f"Reloaded after save: {_reloaded}")

        set_track_override(_db_path, _party_id, "the_killers_mr_brightside", "must_play")
        set_track_override(_db_path, _party_id, "some_avoid_track", "avoid")
        _track_overrides = get_track_overrides(_db_path, _party_id)
        assert _track_overrides["the_killers_mr_brightside"].status == "must_play"
        assert _track_overrides["some_avoid_track"].status == "avoid"
        set_track_override(_db_path, _party_id, "the_killers_mr_brightside", "neutral")
        _track_overrides = get_track_overrides(_db_path, _party_id)
        assert "the_killers_mr_brightside" not in _track_overrides
        print(f"Track overrides after neutral-delete: {_track_overrides}")

        set_artist_override(_db_path, _party_id, "Metallica", "banned")
        _artist_overrides = get_artist_overrides(_db_path, _party_id)
        assert _artist_overrides["Metallica"].status == "banned"
        print(f"Artist overrides: {_artist_overrides}")

        print("music_engine/admin_settings.py sanity check OK.")
