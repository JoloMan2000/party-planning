"""SQLite-Persistenz der Geo Platform (Spec §18, §102). Mirrort das Muster
aus ``accounts/party_storage.py``: idempotente ``CREATE TABLE IF NOT EXISTS``
+ ``PRAGMA table_info``-Migration, ``UNIQUE(party_id)``-Constraint für echte
Upsert-Idempotenz statt Anwendungs-seitiger Lese-vor-Schreib-Prüfung."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from geo.domain import GeoAddress, GeoPoint, LocationPrecision, LocationSource, PartyLocation, VisibilityPolicy


def init_geo_storage(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_locations (
                id TEXT PRIMARY KEY,
                party_id TEXT NOT NULL UNIQUE,
                place_name TEXT,
                street TEXT,
                house_number TEXT,
                postal_code TEXT,
                city TEXT,
                district TEXT,
                region TEXT,
                country_code TEXT,
                country_name TEXT,
                formatted_address TEXT,
                latitude REAL,
                longitude REAL,
                precision TEXT NOT NULL DEFAULT 'approximate',
                provider TEXT,
                provider_place_id TEXT,
                public_location_label TEXT,
                visibility_policy TEXT NOT NULL DEFAULT 'exact_after_accept',
                arrival_instructions TEXT,
                source TEXT NOT NULL DEFAULT 'organizer_entry',
                manually_adjusted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (party_id) REFERENCES parties(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_party_locations_point ON party_locations(latitude, longitude)")


def _row_to_party_location(row: sqlite3.Row) -> PartyLocation:
    has_address = any(
        row[key] is not None
        for key in ("street", "house_number", "postal_code", "city", "district", "region", "country_code", "country_name")
    ) or bool(row["formatted_address"])
    address = (
        GeoAddress(
            street=row["street"],
            house_number=row["house_number"],
            postal_code=row["postal_code"],
            city=row["city"],
            district=row["district"],
            region=row["region"],
            country_code=row["country_code"],
            country_name=row["country_name"],
            formatted_address=row["formatted_address"] or "",
        )
        if has_address
        else None
    )
    point = (
        GeoPoint(latitude=row["latitude"], longitude=row["longitude"])
        if row["latitude"] is not None and row["longitude"] is not None
        else None
    )
    return PartyLocation(
        id=row["id"],
        party_id=row["party_id"],
        place_name=row["place_name"],
        address=address,
        point=point,
        precision=LocationPrecision(row["precision"]),
        provider=row["provider"],
        provider_place_id=row["provider_place_id"],
        public_location_label=row["public_location_label"] or "",
        visibility_policy=VisibilityPolicy(row["visibility_policy"]),
        arrival_instructions=row["arrival_instructions"],
        source=LocationSource(row["source"]),
        manually_adjusted=bool(row["manually_adjusted"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def upsert_party_location(
    db_path: str | Path,
    party_id: str,
    *,
    place_name: str | None = None,
    address: GeoAddress | None = None,
    point: GeoPoint | None = None,
    precision: LocationPrecision = LocationPrecision.APPROXIMATE,
    provider: str | None = None,
    provider_place_id: str | None = None,
    public_location_label: str = "",
    visibility_policy: VisibilityPolicy = VisibilityPolicy.EXACT_AFTER_ACCEPT,
    arrival_instructions: str | None = None,
    source: LocationSource = LocationSource.ORGANIZER_ENTRY,
    manually_adjusted: bool = False,
) -> PartyLocation:
    """Echte Idempotenz via ``UNIQUE(party_id)`` + ``ON CONFLICT DO UPDATE``
    (Spec §102) - dieselbe Location zweimal gespeichert ergibt EINE Zeile."""
    now = datetime.now(timezone.utc).isoformat()
    location_id = f"loc:{party_id}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO party_locations (
                id, party_id, place_name, street, house_number, postal_code, city, district, region,
                country_code, country_name, formatted_address, latitude, longitude, precision, provider,
                provider_place_id, public_location_label, visibility_policy, arrival_instructions, source,
                manually_adjusted, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(party_id) DO UPDATE SET
                place_name = excluded.place_name, street = excluded.street, house_number = excluded.house_number,
                postal_code = excluded.postal_code, city = excluded.city, district = excluded.district,
                region = excluded.region, country_code = excluded.country_code, country_name = excluded.country_name,
                formatted_address = excluded.formatted_address, latitude = excluded.latitude,
                longitude = excluded.longitude, precision = excluded.precision, provider = excluded.provider,
                provider_place_id = excluded.provider_place_id, public_location_label = excluded.public_location_label,
                visibility_policy = excluded.visibility_policy, arrival_instructions = excluded.arrival_instructions,
                source = excluded.source, manually_adjusted = excluded.manually_adjusted, updated_at = excluded.updated_at
            """,
            (
                location_id,
                party_id,
                place_name,
                address.street if address else None,
                address.house_number if address else None,
                address.postal_code if address else None,
                address.city if address else None,
                address.district if address else None,
                address.region if address else None,
                address.country_code if address else None,
                address.country_name if address else None,
                address.formatted_address if address else None,
                point.latitude if point else None,
                point.longitude if point else None,
                precision.value,
                provider,
                provider_place_id,
                public_location_label,
                visibility_policy.value,
                arrival_instructions,
                source.value,
                1 if manually_adjusted else 0,
                now,
                now,
            ),
        )
    return get_party_location(db_path, party_id)


def get_party_location(db_path: str | Path, party_id: str) -> PartyLocation | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM party_locations WHERE party_id = ?", (party_id,)).fetchone()
    return _row_to_party_location(row) if row is not None else None
