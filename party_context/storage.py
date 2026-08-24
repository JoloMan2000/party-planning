"""
SQLite-Persistenz für die Party Context Intelligence Layer (Spec §89-§91).
=============================================================================

Bewusst als separate Tabellen ``party_context`` / ``party_context_override`` /
``weather_snapshot`` umgesetzt (§90, bevorzugte langfristige Struktur), nicht
destruktiv gegenüber der bestehenden ``party_settings``-Tabelle
(``event_theme.py``). Mirrort exakt das dort etablierte Migrations-Muster
(``CREATE TABLE IF NOT EXISTS`` -> ``PRAGMA table_info`` -> fehlende Spalten
per ``ALTER TABLE`` nachziehen -> ``INSERT OR IGNORE`` für die Default-Zeile).

Die App verwaltet aktuell genau EINE laufende Party (siehe
``event_theme.party_settings``), daher sind ``party_context`` und
``weather_snapshot`` bewusst Single-Row-Tabellen (``id = 1``).
``party_context_override`` ist dagegen Multi-Row (ein Override pro Key,
§72)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from party_context.config import PARTY_CONTEXT_MODEL_VERSION
from party_context.domain import PartyContext, PartyContextOverride, WeatherContext

_BOOL_FIELDS = [
    "has_grill", "has_kitchen", "has_fridge", "has_freezer", "has_ice_machine",
    "has_bar", "has_coffee_machine", "has_power", "has_running_water",
    "dancing_possible", "neighbors_sensitive", "self_service",
]
_TEXT_FIELDS = [
    "occasion_id", "season", "location_type", "indoor_outdoor", "music_volume_limit", "weather_condition",
    "party_address", "country_code",
]
_REAL_FIELDS = ["duration_hours", "expected_temperature_c", "rain_probability", "seating_ratio"]
_INT_FIELDS = ["guest_count", "month"]


def init_party_context_storage(db_path: str | Path) -> None:
    """Legt ``party_context``/``party_context_override``/``weather_snapshot``
    an, falls nicht vorhanden, und migriert bestehende Datenbanken idempotent
    (sicher bei jedem App-Start aufrufbar, siehe ``event_theme.init_party_settings``)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_context (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                occasion_id TEXT NOT NULL DEFAULT '',
                start_datetime TEXT NOT NULL DEFAULT '',
                duration_hours REAL NOT NULL DEFAULT 4.0,
                guest_count INTEGER NOT NULL DEFAULT 1,
                season TEXT NOT NULL DEFAULT '',
                month INTEGER,
                location_type TEXT NOT NULL DEFAULT 'other',
                indoor_outdoor TEXT NOT NULL DEFAULT 'outdoor',
                has_grill INTEGER NOT NULL DEFAULT 0,
                has_kitchen INTEGER NOT NULL DEFAULT 0,
                has_fridge INTEGER NOT NULL DEFAULT 0,
                has_freezer INTEGER NOT NULL DEFAULT 0,
                has_ice_machine INTEGER NOT NULL DEFAULT 0,
                has_bar INTEGER NOT NULL DEFAULT 0,
                has_coffee_machine INTEGER NOT NULL DEFAULT 0,
                has_power INTEGER NOT NULL DEFAULT 0,
                has_running_water INTEGER NOT NULL DEFAULT 0,
                music_volume_limit TEXT NOT NULL DEFAULT '',
                dancing_possible INTEGER NOT NULL DEFAULT 0,
                neighbors_sensitive INTEGER NOT NULL DEFAULT 0,
                expected_temperature_c REAL,
                weather_condition TEXT NOT NULL DEFAULT '',
                rain_probability REAL,
                seating_ratio REAL,
                self_service INTEGER NOT NULL DEFAULT 1,
                context_tags TEXT NOT NULL DEFAULT '[]',
                context_model_version TEXT NOT NULL DEFAULT '1.0',
                party_address TEXT NOT NULL DEFAULT '',
                country_code TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_context_override (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_snapshot (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                temperature_c REAL,
                apparent_temperature_c REAL,
                condition TEXT,
                precipitation_probability REAL,
                wind_speed REAL,
                fetched_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geocode_cache (
                address_key TEXT PRIMARY KEY,
                country_code TEXT NOT NULL DEFAULT '',
                cached_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(party_context)")}
        migrations = {
            "context_model_version": "ALTER TABLE party_context ADD COLUMN context_model_version TEXT NOT NULL DEFAULT '1.0'",
            "party_address": "ALTER TABLE party_context ADD COLUMN party_address TEXT NOT NULL DEFAULT ''",
            "country_code": "ALTER TABLE party_context ADD COLUMN country_code TEXT NOT NULL DEFAULT ''",
        }
        for column, ddl in migrations.items():
            if column not in existing_cols:
                conn.execute(ddl)
        conn.execute(
            "INSERT OR IGNORE INTO party_context (id, context_model_version) VALUES (1, ?)",
            (PARTY_CONTEXT_MODEL_VERSION,),
        )


def get_party_context(db_path: str | Path) -> PartyContext:
    """Liest den aktuellen ``PartyContext``. Liefert einen leeren/neutralen
    Default, falls noch nichts gespeichert wurde - niemals None (mirrors
    ``event_theme.get_party_settings``)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM party_context WHERE id = 1").fetchone()
    if row is None:
        return PartyContext()

    start_datetime = None
    if row["start_datetime"]:
        try:
            start_datetime = datetime.fromisoformat(row["start_datetime"])
        except ValueError:
            start_datetime = None

    kwargs: dict = {
        "occasion_id": row["occasion_id"] or "",
        "start_datetime": start_datetime,
        "duration_hours": row["duration_hours"] if row["duration_hours"] is not None else 4.0,
        "guest_count": row["guest_count"] if row["guest_count"] is not None else 1,
        "season": row["season"] or None,
        "month": row["month"],
        "location_type": row["location_type"] or "other",
        "indoor_outdoor": row["indoor_outdoor"] or "outdoor",
        "music_volume_limit": row["music_volume_limit"] or None,
        "expected_temperature_c": row["expected_temperature_c"],
        "weather_condition": row["weather_condition"] or None,
        "rain_probability": row["rain_probability"],
        "seating_ratio": row["seating_ratio"],
        "context_tags": set(json.loads(row["context_tags"] or "[]")),
        "party_address": row["party_address"] or "",
        "country_code": row["country_code"] or "",
    }
    for field_name in _BOOL_FIELDS:
        kwargs[field_name] = bool(row[field_name])
    return PartyContext(**kwargs)


def save_party_context(db_path: str | Path, party_context: PartyContext) -> None:
    """Speichert den ``PartyContext`` (Single-Row-Upsert)."""
    columns = (
        ["id", "context_model_version", "context_tags", "start_datetime"]
        + _TEXT_FIELDS + _REAL_FIELDS + _INT_FIELDS + _BOOL_FIELDS
    )
    values: dict = {
        "id": 1,
        "context_model_version": PARTY_CONTEXT_MODEL_VERSION,
        "context_tags": json.dumps(sorted(party_context.context_tags)),
        "start_datetime": party_context.start_datetime.isoformat() if party_context.start_datetime else "",
    }
    for field_name in _TEXT_FIELDS:
        values[field_name] = getattr(party_context, field_name) or ""
    for field_name in _REAL_FIELDS + _INT_FIELDS:
        values[field_name] = getattr(party_context, field_name)
    for field_name in _BOOL_FIELDS:
        values[field_name] = int(bool(getattr(party_context, field_name)))

    placeholders = ", ".join(f":{c}" for c in columns)
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO party_context ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_clause}",
            values,
        )


def get_party_context_overrides(db_path: str | Path) -> list[PartyContextOverride]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT key, value, reason FROM party_context_override").fetchall()
    return [PartyContextOverride(key=r["key"], value=json.loads(r["value"]), reason=r["reason"]) for r in rows]


def save_party_context_override(db_path: str | Path, override: PartyContextOverride) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO party_context_override (key, value, reason) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, reason = excluded.reason
            """,
            (override.key, json.dumps(override.value), override.reason),
        )


def delete_party_context_override(db_path: str | Path, key: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM party_context_override WHERE key = ?", (key,))


def get_weather_snapshot(db_path: str | Path) -> WeatherContext | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM weather_snapshot WHERE id = 1").fetchone()
    if row is None or row["temperature_c"] is None:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"]) if row["fetched_at"] else None
    return WeatherContext(
        temperature_c=row["temperature_c"],
        apparent_temperature_c=row["apparent_temperature_c"],
        condition=row["condition"],
        precipitation_probability=row["precipitation_probability"],
        wind_speed=row["wind_speed"],
        fetched_at=fetched_at,
    )


def save_weather_snapshot(db_path: str | Path, weather: WeatherContext) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO weather_snapshot (id, temperature_c, apparent_temperature_c, condition, precipitation_probability, wind_speed, fetched_at)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET temperature_c = excluded.temperature_c,
                                           apparent_temperature_c = excluded.apparent_temperature_c,
                                           condition = excluded.condition,
                                           precipitation_probability = excluded.precipitation_probability,
                                           wind_speed = excluded.wind_speed,
                                           fetched_at = excluded.fetched_at
            """,
            (
                weather.temperature_c,
                weather.apparent_temperature_c,
                weather.condition,
                weather.precipitation_probability,
                weather.wind_speed,
                weather.fetched_at.isoformat() if weather.fetched_at else None,
            ),
        )


def get_cached_country_code(db_path: str | Path, address: str) -> str | None:
    """Liefert einen gecachten Ländercode für ``address`` (normalisiert per
    ``.strip().lower()``), oder ``None`` falls noch nicht gecacht. Pflicht-
    Cache (Geo-Kultur-Spec §2), um Nominatims Rate-Limit (max. 1 req/s) zu
    respektieren und redundante Netzwerk-Calls zu vermeiden."""
    key = address.strip().lower()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT country_code FROM geocode_cache WHERE address_key = ?", (key,)).fetchone()
    if row is None:
        return None
    return row["country_code"]


def save_geocode_cache(db_path: str | Path, address: str, country_code: str) -> None:
    key = address.strip().lower()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO geocode_cache (address_key, country_code, cached_at) VALUES (?, ?, ?)
            ON CONFLICT(address_key) DO UPDATE SET country_code = excluded.country_code, cached_at = excluded.cached_at
            """,
            (key, country_code, datetime.now().isoformat()),
        )


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_party_context.db"
        init_party_context_storage(db_path)
        init_party_context_storage(db_path)  # idempotent, darf nicht crashen

        default_ctx = get_party_context(db_path)
        assert default_ctx.location_type == "other"
        assert default_ctx.guest_count == 1

        ctx = PartyContext(
            occasion_id="birthday",
            start_datetime=datetime(2026, 7, 18, 15, 0),
            duration_hours=8.0,
            guest_count=35,
            location_type="garden",
            indoor_outdoor="outdoor",
            has_grill=True,
            has_bar=False,
            expected_temperature_c=29.0,
            weather_condition="sunny",
            context_tags={"birthday", "outdoor"},
        )
        save_party_context(db_path, ctx)
        loaded = get_party_context(db_path)
        assert loaded.occasion_id == "birthday"
        assert loaded.start_datetime == datetime(2026, 7, 18, 15, 0)
        assert loaded.duration_hours == 8.0
        assert loaded.guest_count == 35
        assert loaded.location_type == "garden"
        assert loaded.has_grill is True
        assert loaded.has_bar is False
        assert loaded.expected_temperature_c == 29.0
        assert loaded.context_tags == {"birthday", "outdoor"}

        assert get_party_context_overrides(db_path) == []
        override = PartyContextOverride(key="temperature_class", value="warm", reason="Zelt mit Heizung")
        save_party_context_override(db_path, override)
        loaded_overrides = get_party_context_overrides(db_path)
        assert len(loaded_overrides) == 1
        assert loaded_overrides[0].key == "temperature_class"
        assert loaded_overrides[0].value == "warm"
        assert loaded_overrides[0].reason == "Zelt mit Heizung"

        delete_party_context_override(db_path, "temperature_class")
        assert get_party_context_overrides(db_path) == []

        assert get_weather_snapshot(db_path) is None
        weather = WeatherContext(temperature_c=29.0, apparent_temperature_c=31.0, condition="sunny", precipitation_probability=0.05, wind_speed=3.0, fetched_at=datetime(2026, 7, 18, 8, 0))
        save_weather_snapshot(db_path, weather)
        loaded_weather = get_weather_snapshot(db_path)
        assert loaded_weather is not None
        assert loaded_weather.temperature_c == 29.0
        assert loaded_weather.fetched_at == datetime(2026, 7, 18, 8, 0)

        print("party_context/storage.py sanity check OK.")
