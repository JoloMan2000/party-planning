"""User-Suche für Friend Search (Social-Graph-Phase-1, AUFGABE-Spec §9-10).

Framework-frei und OHNE eigene Tabelle/``init_*`` - mirrort damit den
"bleibt storage-frei"-Vertrag von ``accounts/discover_ranking.py`` (siehe
dortiger Docstring). Sucht ausschließlich über ``username``/``display_name``
(Spec §10: explizit NICHT über E-Mail/Telefon/Geburtsdatum/Standort).

Neues LIKE-Such-Terrain in dieser Codebase - kein bestehendes Muster zum
Kopieren, daher hier explizit dokumentiert: ``%``/``_``/``\\`` werden im
rohen Query-String escaped, bevor er ins ``LIKE``-Pattern eingebettet wird,
damit ein User keine SQL-Wildcards in seine Suchanfrage schmuggeln kann.
Blockierte User werden HIER NICHT ausgefiltert - das bleibt Aufgabe des
Routers (via ``social.blocks.is_blocked``), da Blocking eine Beziehung
zwischen ZWEI Usern ist (Daten des Suchenden). Discoverability
(Social-Graph-Phase-3, ``discoverable_by_username``/``discoverable_by_name``
auf ``UserProfile``) ist dagegen eine Eigenschaft des GESUCHTEN Users
allein und wird deshalb HIER in der WHERE-Klausel durchgesetzt, nicht
nachgelagert im Router - siehe ``search_users`` unten."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UserSearchResult:
    user_id: str
    username: str
    display_name: str
    profile_image: str


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


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.profile_storage as profile_storage
    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_search.db"
        user_storage.init_user_storage(db_path)
        profile_storage.init_profile_storage(db_path)

        me = user_storage.create_user(db_path, uuid.uuid4().hex, "me@example.com", "hash", "Me")
        max_ = user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max Mustermann")
        from datetime import date

        profile_storage.upsert_user_profile(db_path, max_.id, birth_date=date(1990, 1, 1), username="MaxM")
        anna = user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")

        by_username = search_users(db_path, "maxm", exclude_user_id=me.id)
        assert len(by_username) == 1
        assert by_username[0].user_id == max_.id
        assert by_username[0].username == "MaxM"

        by_display_name = search_users(db_path, "Anna", exclude_user_id=me.id)
        assert len(by_display_name) == 1
        assert by_display_name[0].user_id == anna.id

        # Sich selbst nie im Ergebnis.
        assert all(r.user_id != me.id for r in search_users(db_path, "Me", exclude_user_id=me.id))

        # Kein Treffer -> leere Liste, kein Crash.
        assert search_users(db_path, "nonexistent", exclude_user_id=me.id) == []

        # SQL-Wildcards im Query werden escaped, nicht als Wildcard interpretiert.
        assert search_users(db_path, "%", exclude_user_id=me.id) == []

        # Social-Graph-Phase-3: die zwei Discoverability-Toggles wirken unabhängig.
        username_only = user_storage.create_user(
            db_path, uuid.uuid4().hex, "usernameonly@example.com", "hash", "Findable By Name"
        )
        profile_storage.upsert_user_profile(
            db_path, username_only.id, birth_date=date(1990, 1, 1), username="handleonly",
            discoverable_by_name=False,
        )
        # Per Username findbar (Toggle an)...
        assert any(r.user_id == username_only.id for r in search_users(db_path, "handleonly", exclude_user_id=me.id))
        # ...aber NICHT per echtem Namen (Toggle aus).
        assert not any(
            r.user_id == username_only.id for r in search_users(db_path, "Findable By Name", exclude_user_id=me.id)
        )

        name_only = user_storage.create_user(db_path, uuid.uuid4().hex, "nameonly@example.com", "hash", "Only By Name")
        profile_storage.upsert_user_profile(
            db_path, name_only.id, birth_date=date(1990, 1, 1), username="hiddenhandle",
            discoverable_by_username=False,
        )
        # Per echtem Namen findbar (Toggle an)...
        assert any(r.user_id == name_only.id for r in search_users(db_path, "Only By Name", exclude_user_id=me.id))
        # ...aber NICHT per Username (Toggle aus).
        assert not any(
            r.user_id == name_only.id for r in search_users(db_path, "hiddenhandle", exclude_user_id=me.id)
        )

        print("social/search.py sanity check OK.")
