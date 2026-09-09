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
Routers (via ``social.blocks.is_blocked``), damit dieses Modul eine reine
Text-Such-Zuständigkeit behält."""

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
    pattern = f"%{_escape_like(query)}%"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT u.id AS user_id, COALESCE(up.username, '') AS username,
                   u.display_name AS display_name, u.profile_image AS profile_image
            FROM users u
            LEFT JOIN user_profiles up ON up.user_id = u.id
            WHERE u.id != ?
              AND (up.username LIKE ? ESCAPE '\\' OR u.display_name LIKE ? ESCAPE '\\')
            ORDER BY u.display_name
            LIMIT ?
            """,
            (exclude_user_id, pattern, pattern, limit),
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

        print("social/search.py sanity check OK.")
