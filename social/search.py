"""Storage-freie, cross-entity LIKE-Suche für den Social Graph.

Ursprünglich nur User-Suche (Social-Graph-Phase-1, AUFGABE-Spec §9-10);
seit Social-Graph-Phase-6 (Spec §82-83, §122-125) zusätzlich Organizer- und
Event-Suche in EINEM Modul - es ist die einzige LIKE-Such-Stelle der
Codebase, und ``_escape_like`` (``%``/``_``/``\\``-Escaping, damit ein User
keine SQL-Wildcards in seine Suchanfrage schmuggeln kann) soll genau einmal
existieren.

Framework-frei und OHNE eigene Tabelle/``init_*`` - mirrort damit den
"bleibt storage-frei"-Vertrag von ``accounts/discover_ranking.py``. Liest
per Roh-SQL Tabellen anderer Domänen (``users``/``user_profiles`` von
``accounts``, ``organizers`` von ``organizers``, ``parties``/
``public_events`` von ``accounts``), importiert diese Pakete auf
Modulebene aber NICHT (nur der ``__main__``-Selbsttest tut das).

Privacy-Aufteilung je Entität:
- **User**: die zwei ``discoverable_by_*``-Toggles (Social-Graph-Phase-3,
  Eigenschaft des GESUCHTEN Users) werden HIER in der WHERE-Klausel
  durchgesetzt. Nur über ``username``/``display_name`` (Spec §10: NICHT
  über E-Mail/Telefon/Geburtsdatum/Standort).
- **Organizer**: nur ``verification_status = 'verified'`` ist öffentlich
  auffindbar (Spec §84: nur das Backend setzt ``verified``; unverifizierte
  Organizer sollen nicht leaken). Match nur über ``display_name`` (kein
  ``description``).
- **Event**: nur veröffentlichte Partys (Zeile in ``public_events``
  vorhanden). Match nur über ``parties.name`` (kein ``location``/
  ``description``).
- **Blocking** bleibt in JEDEM Fall Aufgabe des Routers - es ist eine
  Beziehung zwischen ZWEI Usern (Daten des Suchenden), siehe
  ``backend/app/routers/social.py``."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class UserSearchResult:
    user_id: str
    username: str
    display_name: str
    profile_image: str


@dataclass
class OrganizerSearchResult:
    organizer_id: str
    owner_user_id: str  # echter User - der Router filtert damit geblockte Owner raus
    display_name: str
    verification_status: str  # per WHERE immer "verified", für den DTO-``verified``-Bool durchgereicht


@dataclass
class EventSearchResult:
    party_id: str
    host_user_id: str  # echter User - Router-seitiger Block-Filter + Auflösung von ``organizer_name``
    name: str
    starts_at: datetime | None
    location: str
    cover_image: str
    event_type: str


def _escape_like(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_users(db_path: str | Path, query: str, exclude_user_id: str, limit: int = 20) -> list[UserSearchResult]:
    """UNION zweier unabhängig gegateter Zweige (Social-Graph-Phase-3) -
    ein einzelnes ``WHERE (username LIKE ? OR display_name LIKE ?)`` könnte
    nicht ausdrücken, WELCHES Feld getroffen hat, und damit die beiden
    ``discoverable_by_*``-Toggles nicht unabhängig durchsetzen (ein User,
    der nur per @handle, nicht aber per echtem Namen auffindbar sein will,
    bräuchte sonst eine Alles-oder-nichts-Regel). ``UNION`` (nicht
    ``UNION ALL``) dedupliziert automatisch, wenn ein User über BEIDE Zweige
    matcht. ``ORDER BY``/``LIMIT`` wirken bewusst auf die äußere,
    zusammengeführte Query - nicht auf einen der beiden inneren Zweige,
    sonst würde ``LIMIT`` jeden Zweig unabhängig kappen statt das
    kombinierte Ergebnis."""
    pattern = f"%{_escape_like(query)}%"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT u.id AS user_id, COALESCE(up.username, '') AS username,
                       u.display_name AS display_name, u.profile_image AS profile_image
                FROM users u
                LEFT JOIN user_profiles up ON up.user_id = u.id
                WHERE u.id != ?
                  AND COALESCE(up.discoverable_by_username, 1) = 1
                  AND up.username LIKE ? ESCAPE '\\'

                UNION

                SELECT u.id AS user_id, COALESCE(up.username, '') AS username,
                       u.display_name AS display_name, u.profile_image AS profile_image
                FROM users u
                LEFT JOIN user_profiles up ON up.user_id = u.id
                WHERE u.id != ?
                  AND COALESCE(up.discoverable_by_name, 1) = 1
                  AND u.display_name LIKE ? ESCAPE '\\'
            )
            ORDER BY display_name
            LIMIT ?
            """,
            (exclude_user_id, pattern, exclude_user_id, pattern, limit),
        ).fetchall()
    return [
        UserSearchResult(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            profile_image=row["profile_image"] or "",
        )
        for row in rows
    ]


def search_organizers(db_path: str | Path, query: str, limit: int = 20) -> list[OrganizerSearchResult]:
    """Social-Graph-Phase-6: nur ``verified`` Organizer sind öffentlich
    auffindbar (Spec §84), Match nur über ``display_name`` (kein
    ``description`` - free-text-Substrings sollen nicht leaken)."""
    pattern = f"%{_escape_like(query)}%"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id AS organizer_id, owner_user_id, display_name, verification_status
            FROM organizers
            WHERE verification_status = 'verified'
              AND display_name LIKE ? ESCAPE '\\'
            ORDER BY display_name
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()
    return [
        OrganizerSearchResult(
            organizer_id=row["organizer_id"],
            owner_user_id=row["owner_user_id"],
            display_name=row["display_name"],
            verification_status=row["verification_status"],
        )
        for row in rows
    ]


def search_public_events(db_path: str | Path, query: str, limit: int = 20) -> list[EventSearchResult]:
    """Social-Graph-Phase-6: nur veröffentlichte Partys (Zeile in
    ``public_events`` - Unpublish löscht sie). Match nur über
    ``parties.name`` (kein ``location``/``description``). Reihenfolge:
    zuletzt veröffentlicht zuerst, mirrort
    ``discover_storage.list_candidate_publications``."""
    pattern = f"%{_escape_like(query)}%"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT p.id AS party_id, p.host_user_id AS host_user_id, p.name AS name,
                   p.starts_at AS starts_at, p.location AS location, p.cover_image AS cover_image,
                   pe.event_type AS event_type
            FROM parties p
            JOIN public_events pe ON pe.party_id = p.id
            WHERE p.name LIKE ? ESCAPE '\\'
            ORDER BY pe.published_at DESC
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()
    return [
        EventSearchResult(
            party_id=row["party_id"],
            host_user_id=row["host_user_id"],
            name=row["name"],
            starts_at=datetime.fromisoformat(row["starts_at"]) if row["starts_at"] else None,
            location=row["location"],
            cover_image=row["cover_image"] or "",
            event_type=row["event_type"],
        )
        for row in rows
    ]


if __name__ == "__main__":
    import tempfile
    import uuid
    from datetime import date

    import accounts.discover_storage as discover_storage
    import accounts.party_storage as party_storage
    import accounts.profile_storage as profile_storage
    import accounts.user_storage as user_storage
    import organizers.storage as organizers_storage
    from organizers.domain import OrganizerVerificationStatus

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_search.db"
        user_storage.init_user_storage(db_path)
        profile_storage.init_profile_storage(db_path)
        party_storage.init_party_storage(db_path)
        organizers_storage.init_organizer_storage(db_path)
        discover_storage.init_discover_storage(db_path)

        me = user_storage.create_user(db_path, uuid.uuid4().hex, "me@example.com", "hash", "Me")
        max_ = user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max Mustermann")
        profile_storage.upsert_user_profile(db_path, max_.id, birth_date=date(1990, 1, 1), username="MaxM")
        anna = user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")

        by_username = search_users(db_path, "maxm", exclude_user_id=me.id)
        assert len(by_username) == 1 and by_username[0].user_id == max_.id
        by_display_name = search_users(db_path, "Anna", exclude_user_id=me.id)
        assert len(by_display_name) == 1 and by_display_name[0].user_id == anna.id
        assert all(r.user_id != me.id for r in search_users(db_path, "Me", exclude_user_id=me.id))
        assert search_users(db_path, "nonexistent", exclude_user_id=me.id) == []
        assert search_users(db_path, "%", exclude_user_id=me.id) == []

        # Social-Graph-Phase-3: die zwei Discoverability-Toggles wirken unabhängig.
        username_only = user_storage.create_user(
            db_path, uuid.uuid4().hex, "usernameonly@example.com", "hash", "Findable By Name"
        )
        profile_storage.upsert_user_profile(
            db_path, username_only.id, birth_date=date(1990, 1, 1), username="handleonly", discoverable_by_name=False
        )
        assert any(r.user_id == username_only.id for r in search_users(db_path, "handleonly", exclude_user_id=me.id))
        assert not any(
            r.user_id == username_only.id for r in search_users(db_path, "Findable By Name", exclude_user_id=me.id)
        )

        # --- Social-Graph-Phase-6: Organizer-Suche ---
        verified_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, max_.id, "Boiler Room")
        organizers_storage.set_verification_status(db_path, verified_org.id, OrganizerVerificationStatus.VERIFIED)
        unverified_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, max_.id, "Boiler Basement")

        org_hits = search_organizers(db_path, "boiler")
        assert [o.organizer_id for o in org_hits] == [verified_org.id]  # nur der verifizierte, case-insensitiv
        assert org_hits[0].owner_user_id == max_.id
        assert search_organizers(db_path, "%") == []
        assert search_organizers(db_path, "nonexistent") == []

        organizers_storage.set_verification_status(db_path, unverified_org.id, OrganizerVerificationStatus.SUSPENDED)
        assert search_organizers(db_path, "basement") == []  # suspended zählt nicht als verified

        # --- Social-Graph-Phase-6: Event-Suche ---
        published = party_storage.create_party(db_path, uuid.uuid4().hex, max_.id, "Summer Sound Festival")
        discover_storage.publish_party(db_path, published.id, event_type="festival")
        unpublished = party_storage.create_party(db_path, uuid.uuid4().hex, max_.id, "Summer Secret Party")

        ev_hits = search_public_events(db_path, "summer")
        assert [e.party_id for e in ev_hits] == [published.id]
        assert ev_hits[0].host_user_id == max_.id
        assert ev_hits[0].event_type == "festival"

        discover_storage.unpublish_party(db_path, published.id)
        assert search_public_events(db_path, "summer") == []  # nach Unpublish weg
        assert search_public_events(db_path, "%") == []

        print("social/search.py sanity check OK.")
