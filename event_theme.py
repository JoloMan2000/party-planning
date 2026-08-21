"""
Event-Typ & Party-Name (admin-konfigurierbar)
==============================================

Der Admin kann für die gesamte Party EINMAL einen Event-Typ (z.B. Geburtstag,
Jubiläum, Spieleabend, Winterparty, Sonstiges) sowie einen individuellen
Party-Namen festlegen. Das beeinflusst NUR Optik/Text (Titel, Icon,
Hero-Farbverlauf, Untertitel auf dem Intro-Screen) - NICHT den Getränke-/
Essenskatalog oder die Wizard-Fragen (die kommen weiterhin ausschließlich aus
party_engine/catalog.py).

Dieses Modul ist bewusst Streamlit-frei (reines sqlite3 + Dict-Daten), damit
es leicht testbar/wiederverwendbar bleibt - siehe Docstring-Konvention der
übrigen Module in diesem Repo (z.B. party_engine/catalog.py).

Verwendung ("Party Planning.py"):
    import event_theme

    event_theme.init_party_settings(DB_PATH)   # einmal beim App-Start
    settings = event_theme.get_party_settings(DB_PATH)
    title = event_theme.resolve_party_title(settings)
    theme = event_theme.EVENT_TYPES[settings["event_type"]]
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# --- Event-Typ-Presets ----------------------------------------------------
#
# Jeder Eintrag steuert AUSSCHLIESSLICH Optik/Text:
#   emoji           - Icon-String für den Hero-Bereich
#   label_de/en      - kurzes Label für die Admin-Auswahl (Selectbox)
#   default_title    - Fallback-Partyname, falls der Admin keinen eigenen
#                       Namen einträgt
#   intro_subtitle   - kurzer, zweisprachiger (DE/EN) Text für den neuen
#                       Intro-Screen VOR der Sprachauswahl (dort steht noch
#                       keine gewählte Sprache zur Verfügung, daher bewusst
#                       kombiniert statt über t())
#   hero_gradient    - 3 CSS-Farben für den 135deg-Hero-Verlauf
#                       (".party-hero" background in inject_theme())
#   accent_gradient  - 2 CSS-Farben für Buttons/Akzente
#                       (".stButton > button" background in inject_theme())
#
# WICHTIG: "bauwagen_sommerparty" ist der Default und muss exakt die heute
# fest codierten Farben aus inject_theme()/render_hero() abbilden (siehe
# Regressions-Vorgabe in der Aufgabenstellung) - NICHT verändern.

EVENT_TYPES: dict[str, dict] = {
    "bauwagen_sommerparty": {
        "emoji": "🌿🪵✨",
        "label_de": "Bauwagen-Sommerparty",
        "label_en": "Bauwagen summer party",
        "default_title": "Bauwagen Gartenparty",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining!",
        "hero_gradient": ("#3F2E22", "#4A342A", "#3F5B41"),
        "accent_gradient": ("#C68642", "#A8672F"),
    },
    "birthday": {
        "emoji": "🎂🎈🎉",
        "label_de": "Geburtstag",
        "label_en": "Birthday",
        "default_title": "Geburtstagsfeier",
        "intro_subtitle": "Schön, dass du mitfeierst! · So glad you're celebrating with us!",
        "hero_gradient": ("#4A1F33", "#7A2E4A", "#C9873A"),
        "accent_gradient": ("#E8A24A", "#C9873A"),
    },
    "anniversary": {
        "emoji": "💍✨🥂",
        "label_de": "Jubiläum",
        "label_en": "Anniversary",
        "default_title": "Jubiläumsfeier",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining us!",
        "hero_gradient": ("#1A1A1A", "#2B2418", "#3D3320"),
        "accent_gradient": ("#D4AF37", "#B8952E"),
    },
    "game_night": {
        "emoji": "🎲🕹️✨",
        "label_de": "Spieleabend",
        "label_en": "Game night",
        "default_title": "Spieleabend",
        "intro_subtitle": "Bereit zum Zocken? · Ready to play?",
        "hero_gradient": ("#241B3F", "#382A5C", "#1F4E5F"),
        "accent_gradient": ("#8E6FE0", "#5C3FB8"),
    },
    "winter_party": {
        "emoji": "❄️🎄✨",
        "label_de": "Winterparty",
        "label_en": "Winter party",
        "default_title": "Winterparty",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining!",
        "hero_gradient": ("#0F2027", "#203A43", "#2C5364"),
        "accent_gradient": ("#7FC7D9", "#3E8FA8"),
    },
    "custom": {
        "emoji": "🎊🎈✨",
        "label_de": "Sonstiges",
        "label_en": "Other",
        "default_title": "Meine Party",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining!",
        "hero_gradient": ("#2C2A26", "#3A3733", "#4A4842"),
        "accent_gradient": ("#C68642", "#A8672F"),
    },
}

DEFAULT_EVENT_TYPE = "bauwagen_sommerparty"


# --- Storage (SQLite) ------------------------------------------------------


def init_party_settings(db_path: str | Path) -> None:
    """Legt die (Single-Row-)Tabelle 'party_settings' an, falls sie noch nicht
    existiert, und fügt die Default-Zeile ein, falls noch keine vorhanden ist.
    Sicher bei jedem App-Start aufrufbar (mirroring init_db()-Muster in
    "Party Planning.py")."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                event_type TEXT NOT NULL DEFAULT 'bauwagen_sommerparty',
                party_name TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO party_settings (id, event_type, party_name)
            VALUES (1, ?, '')
            """,
            (DEFAULT_EVENT_TYPE,),
        )


def get_party_settings(db_path: str | Path) -> dict:
    """Liest die aktuellen Party-Einstellungen. Gibt bei fehlender/unbekannter
    event_type sicherheitshalber den Default-Event-Typ zurück (z.B. falls die
    DB manuell verändert wurde)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT event_type, party_name FROM party_settings WHERE id = 1"
        ).fetchone()
    if row is None:
        return {"event_type": DEFAULT_EVENT_TYPE, "party_name": ""}
    event_type = row["event_type"] if row["event_type"] in EVENT_TYPES else DEFAULT_EVENT_TYPE
    return {"event_type": event_type, "party_name": row["party_name"] or ""}


def save_party_settings(db_path: str | Path, event_type: str, party_name: str) -> None:
    """Speichert Event-Typ + Party-Name (Single-Row-Upsert)."""
    if event_type not in EVENT_TYPES:
        event_type = DEFAULT_EVENT_TYPE
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO party_settings (id, event_type, party_name)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET event_type = excluded.event_type,
                                           party_name = excluded.party_name
            """,
            (event_type, party_name.strip()),
        )


def resolve_party_title(settings: dict) -> str:
    """Liefert den anzuzeigenden Partynamen: den vom Admin eingetragenen
    Namen, falls vorhanden, sonst den default_title des gewählten Event-Typs."""
    party_name = (settings.get("party_name") or "").strip()
    if party_name:
        return party_name
    event_type = settings.get("event_type", DEFAULT_EVENT_TYPE)
    theme = EVENT_TYPES.get(event_type, EVENT_TYPES[DEFAULT_EVENT_TYPE])
    return theme["default_title"]
