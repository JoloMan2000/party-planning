"""Gäste-Antworten-Storage (``responses``-Tabelle).

Extrahiert aus ``"Party Planning.py"`` (Backend-Migration Phase 1, Schritt 0a):
diese vier Funktionen (``init_db``/``save_response``/``load_responses``/
``_classify_item_type``) enthielten von Anfang an keine Streamlit-Aufrufe,
lebten aber als private Helfer direkt im Streamlit-Skript. Da
``"Party Planning.py"`` selbst nicht importierbar ist (führt beim Import
``st.secrets``/``st.set_page_config`` aus und crasht außerhalb einer
Streamlit-Runtime), müssen sie hierher verschoben werden, damit sowohl die
Streamlit-App als auch das neue FastAPI-Backend dieselbe Logik nutzen können
- ein reiner Move, keine Verhaltensänderung (mirroring des sqlite3-Musters aus
``event_theme.py``/``party_engine/catalog_curation.py``).

Verwendung ("Party Planning.py" UND backend/):
    import party_engine.response_storage as response_storage

    response_storage.init_db(DB_PATH)
    response_storage.save_response(DB_PATH, name=..., start_time=..., ...)
    rows = response_storage.load_responses(DB_PATH)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from party_engine.domain import PartyCatalog


def init_db(db_path: str | Path) -> None:
    """Legt die ``responses``-Tabelle an, falls sie noch nicht existiert.
    Sicher bei jedem App-Start aufrufbar (idempotent)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                party_id TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                drinks TEXT NOT NULL,
                drinks_freetext TEXT,
                food TEXT NOT NULL,
                food_freetext TEXT,
                songs TEXT NOT NULL DEFAULT '[]',
                submitted_at TEXT NOT NULL
            )
            """
        )
        # Migration für Datenbanken, die vor der Songwunsch-Funktion angelegt wurden.
        try:
            conn.execute("ALTER TABLE responses ADD COLUMN songs TEXT NOT NULL DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits
        # Migration für Datenbanken von vor dem Multi-Tenant-Pivot (Phase 4).
        try:
            conn.execute("ALTER TABLE responses ADD COLUMN party_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responses_party_id ON responses(party_id)")


def save_response(
    db_path: str | Path,
    party_id: str,
    name: str,
    start_time: str,
    drinks: list[str],
    drinks_freetext: str,
    food: list[str],
    food_freetext: str,
    songs: list[dict],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO responses
                (party_id, name, start_time, drinks, drinks_freetext, food, food_freetext, songs, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                party_id,
                name,
                start_time,
                json.dumps(drinks),
                drinks_freetext,
                json.dumps(food),
                food_freetext,
                json.dumps(songs),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def load_responses(db_path: str | Path, party_id: str) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM responses WHERE party_id = ? ORDER BY id", (party_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def _classify_item_type(item_id: str, catalog: PartyCatalog) -> str:
    """Ordnet eine gespeicherte Auswahl-ID ihrem Katalog-Item-Typ zu
    (Geo-Kultur-Spec §7). Leerer String für unbekannte/Freitext-IDs -
    diese werden beim Einfrieren nicht als ``SelectionEvent`` geloggt."""
    if item_id in catalog.recipes:
        return "recipe"
    if item_id in catalog.direct_consumables:
        return "direct_consumable"
    return ""


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_response_storage.db"
        party_id = "test-party"
        init_db(db_path)
        init_db(db_path)  # idempotent, darf nicht crashen

        assert load_responses(db_path, party_id) == []

        save_response(
            db_path,
            party_id,
            name="Max",
            start_time="19:00",
            drinks=["beer_pils"],
            drinks_freetext="",
            food=["pizza_margherita"],
            food_freetext="",
            songs=[{"artist": "Queen", "title": "Bohemian Rhapsody"}],
        )
        rows = load_responses(db_path, party_id)
        assert len(rows) == 1
        assert rows[0]["name"] == "Max"
        assert json.loads(rows[0]["drinks"]) == ["beer_pils"]
        assert json.loads(rows[0]["songs"])[0]["artist"] == "Queen"

        print("party_engine/response_storage.py sanity check OK.")
