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
#   occasion_id      - Fremdschlüssel in die Occasion Recommendation Engine
#                       (party_engine/occasions.py, catalog/occasions/*.json)
#                       - steuert NICHT die Optik, sondern welches
#                       Anlass-Profil beim Empfehlungs-Scoring
#                       (party_engine/recommendation.py) verwendet wird.
#
# Die Keys entsprechen absichtlich 1:1 den 23 Occasion-IDs der Recommendation
# Engine (Ausnahme: "bauwagen_sommerparty" ist ein zusätzlicher, rein
# optischer Sonder-Eintrag für den bisherigen Default-Look und mappt für die
# Empfehlungslogik auf die Occasion "summer_party").
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
        "occasion_id": "summer_party",
    },
    "birthday": {
        "emoji": "🎂🎈🎉",
        "label_de": "Geburtstag",
        "label_en": "Birthday",
        "default_title": "Geburtstagsfeier",
        "intro_subtitle": "Schön, dass du mitfeierst! · So glad you're celebrating with us!",
        "hero_gradient": ("#4A1F33", "#7A2E4A", "#C9873A"),
        "accent_gradient": ("#E8A24A", "#C9873A"),
        "occasion_id": "birthday",
    },
    "grill_party": {
        "emoji": "🔥🍖🌭",
        "label_de": "Grillparty",
        "label_en": "Grill party",
        "default_title": "Grillparty",
        "intro_subtitle": "Lust auf Gegrilltes? · Ready to fire up the grill?",
        "hero_gradient": ("#2B1A0F", "#4A2A12", "#7A3B12"),
        "accent_gradient": ("#E8722A", "#C25A1A"),
        "occasion_id": "grill_party",
    },
    "garden_party": {
        "emoji": "🌸🌿✨",
        "label_de": "Gartenparty",
        "label_en": "Garden party",
        "default_title": "Gartenparty",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining!",
        "hero_gradient": ("#1E2B1A", "#2E4023", "#4A6B2F"),
        "accent_gradient": ("#8FBF5A", "#6B9E3E"),
        "occasion_id": "garden_party",
    },
    "daydrinking": {
        "emoji": "🍹☀️✨",
        "label_de": "Daydrinking",
        "label_en": "Daydrinking",
        "default_title": "Daydrinking-Session",
        "intro_subtitle": "Bereit für ein paar Drinks bei Sonne? · Ready for some sunny sipping?",
        "hero_gradient": ("#2B2410", "#4A3D14", "#C9873A"),
        "accent_gradient": ("#F2C14E", "#D9A62D"),
        "occasion_id": "daydrinking",
    },
    "house_party": {
        "emoji": "🏠🎶✨",
        "label_de": "Hausparty",
        "label_en": "House party",
        "default_title": "Hausparty",
        "intro_subtitle": "Bereit für eine Wohnzimmer-Party? · Ready for a house party?",
        "hero_gradient": ("#1C1730", "#2E2350", "#5C2E6B"),
        "accent_gradient": ("#B14FD1", "#8E2FA8"),
        "occasion_id": "house_party",
    },
    "cocktail_party": {
        "emoji": "🍸🌃✨",
        "label_de": "Cocktailabend",
        "label_en": "Cocktail party",
        "default_title": "Cocktailabend",
        "intro_subtitle": "Zeit für gute Drinks! · Time for great drinks!",
        "hero_gradient": ("#150F1F", "#2A1A3A", "#4A2050"),
        "accent_gradient": ("#D4AF37", "#B8952E"),
        "occasion_id": "cocktail_party",
    },
    "game_night": {
        "emoji": "🎲🕹️✨",
        "label_de": "Spieleabend",
        "label_en": "Game night",
        "default_title": "Spieleabend",
        "intro_subtitle": "Bereit zum Zocken? · Ready to play?",
        "hero_gradient": ("#241B3F", "#382A5C", "#1F4E5F"),
        "accent_gradient": ("#8E6FE0", "#5C3FB8"),
        "occasion_id": "game_night",
    },
    "sports_night": {
        "emoji": "⚽📺✨",
        "label_de": "Sportabend",
        "label_en": "Sports night",
        "default_title": "Sportabend",
        "intro_subtitle": "Anpfiff! · Kick-off!",
        "hero_gradient": ("#0F1F14", "#1B3322", "#245C2E"),
        "accent_gradient": ("#4CC26B", "#2E9E4A"),
        "occasion_id": "sports_night",
    },
    "movie_night": {
        "emoji": "🎬🍿✨",
        "label_de": "Filmabend",
        "label_en": "Movie night",
        "default_title": "Filmabend",
        "intro_subtitle": "Film ab! · Lights, camera, action!",
        "hero_gradient": ("#160F14", "#2A1620", "#4A1F30"),
        "accent_gradient": ("#E0475C", "#B8324A"),
        "occasion_id": "movie_night",
    },
    "dinner_party": {
        "emoji": "🍽️🕯️✨",
        "label_de": "Dinner-Abend",
        "label_en": "Dinner party",
        "default_title": "Dinner-Abend",
        "intro_subtitle": "Guten Appetit! · Bon appétit!",
        "hero_gradient": ("#241A16", "#3A2620", "#5C3428"),
        "accent_gradient": ("#D9A25E", "#B8813E"),
        "occasion_id": "dinner_party",
    },
    "brunch": {
        "emoji": "🥐☕✨",
        "label_de": "Brunch",
        "label_en": "Brunch",
        "default_title": "Brunch",
        "intro_subtitle": "Guten Morgen! · Good morning!",
        "hero_gradient": ("#2E2418", "#4A3826", "#C9A24A"),
        "accent_gradient": ("#F2C879", "#D9A24E"),
        "occasion_id": "brunch",
    },
    "summer_party": {
        "emoji": "☀️🍉✨",
        "label_de": "Sommerparty",
        "label_en": "Summer party",
        "default_title": "Sommerparty",
        "intro_subtitle": "Sommer, Sonne, gute Laune! · Summer, sun, good vibes!",
        "hero_gradient": ("#102030", "#1B3A4A", "#2C8FA8"),
        "accent_gradient": ("#4FC7D9", "#2E9EAF"),
        "occasion_id": "summer_party",
    },
    "pool_party": {
        "emoji": "🏊🌊✨",
        "label_de": "Poolparty",
        "label_en": "Pool party",
        "default_title": "Poolparty",
        "intro_subtitle": "Ab ins kühle Nass! · Dive in!",
        "hero_gradient": ("#0C1F2A", "#153A4A", "#1E6E8A"),
        "accent_gradient": ("#4FD9E8", "#2EA8B8"),
        "occasion_id": "pool_party",
    },
    "picnic": {
        "emoji": "🧺🌼✨",
        "label_de": "Picknick",
        "label_en": "Picnic",
        "default_title": "Picknick",
        "intro_subtitle": "Decke ausbreiten und genießen! · Spread the blanket and enjoy!",
        "hero_gradient": ("#242E14", "#3A4A20", "#6B8F3E"),
        "accent_gradient": ("#C9DB7A", "#A8C24E"),
        "occasion_id": "picnic",
    },
    "festival_outdoor": {
        "emoji": "🎪🎶✨",
        "label_de": "Festival / Open-Air-Party",
        "label_en": "Festival / outdoor party",
        "default_title": "Open-Air-Party",
        "intro_subtitle": "Bühne frei! · Let the show begin!",
        "hero_gradient": ("#1F1030", "#3A1850", "#6B1F70"),
        "accent_gradient": ("#E85FD1", "#B82FA8"),
        "occasion_id": "festival_outdoor",
    },
    "winter_party": {
        "emoji": "❄️🎄✨",
        "label_de": "Winterparty",
        "label_en": "Winter party",
        "default_title": "Winterparty",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining!",
        "hero_gradient": ("#0F2027", "#203A43", "#2C5364"),
        "accent_gradient": ("#7FC7D9", "#3E8FA8"),
        "occasion_id": "winter_party",
    },
    "christmas_party": {
        "emoji": "🎄🎅✨",
        "label_de": "Weihnachtsfeier",
        "label_en": "Christmas party",
        "default_title": "Weihnachtsfeier",
        "intro_subtitle": "Frohe Weihnachten! · Merry Christmas!",
        "hero_gradient": ("#0F2418", "#1B3D26", "#7A1F24"),
        "accent_gradient": ("#D4AF37", "#B8952E"),
        "occasion_id": "christmas_party",
    },
    "new_years_eve": {
        "emoji": "🎆🥂✨",
        "label_de": "Silvesterparty",
        "label_en": "New Year's Eve",
        "default_title": "Silvesterparty",
        "intro_subtitle": "Auf ein neues Jahr! · To a new year!",
        "hero_gradient": ("#0A0A14", "#1A1A2E", "#2E2A50"),
        "accent_gradient": ("#D4AF37", "#F2C14E"),
        "occasion_id": "new_years_eve",
    },
    "wedding": {
        "emoji": "💍👰✨",
        "label_de": "Hochzeit",
        "label_en": "Wedding",
        "default_title": "Hochzeitsfeier",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're celebrating with us!",
        "hero_gradient": ("#241E1A", "#3A2E24", "#C9A24A"),
        "accent_gradient": ("#E8C97A", "#C9A24A"),
        "occasion_id": "wedding",
    },
    "engagement_party": {
        "emoji": "💍💕✨",
        "label_de": "Verlobungsfeier",
        "label_en": "Engagement party",
        "default_title": "Verlobungsfeier",
        "intro_subtitle": "Herzlichen Glückwunsch! · Congratulations!",
        "hero_gradient": ("#2A1A20", "#4A2830", "#7A3A4A"),
        "accent_gradient": ("#E88FA8", "#C9607F"),
        "occasion_id": "engagement_party",
    },
    "bachelor_party": {
        "emoji": "🥳🍾✨",
        "label_de": "Junggesell(inn)enabschied",
        "label_en": "Bachelor / bachelorette party",
        "default_title": "JGA",
        "intro_subtitle": "Let's party! · Let's celebrate!",
        "hero_gradient": ("#160F1C", "#2E1030", "#5C1750"),
        "accent_gradient": ("#E845B8", "#B82F8E"),
        "occasion_id": "bachelor_party",
    },
    "family_party": {
        "emoji": "👨‍👩‍👧‍👦🎉✨",
        "label_de": "Familienfeier",
        "label_en": "Family party",
        "default_title": "Familienfeier",
        "intro_subtitle": "Schön, dass die Familie zusammenkommt! · So glad the family is together!",
        "hero_gradient": ("#2A1F14", "#4A3620", "#7A5A2E"),
        "accent_gradient": ("#E8A24A", "#C9873A"),
        "occasion_id": "family_party",
    },
    "casual_get_together": {
        "emoji": "🍻😊✨",
        "label_de": "Lockeres Beisammensein",
        "label_en": "Casual get-together",
        "default_title": "Gemütliches Beisammensein",
        "intro_subtitle": "Schön, dass du dabei bist! · So glad you're joining!",
        "hero_gradient": ("#1F2420", "#333D34", "#4A5C4A"),
        "accent_gradient": ("#8FBF7A", "#6B9E5E"),
        "occasion_id": "casual_get_together",
    },
}

DEFAULT_EVENT_TYPE = "bauwagen_sommerparty"


def resolve_occasion_id(event_type: str) -> str:
    """Löst den admin-konfigurierten Event-Typ auf die zugehörige Occasion-ID
    der Recommendation Engine auf (siehe ``occasion_id``-Feld oben). Fällt bei
    unbekanntem ``event_type`` auf den Default-Event-Typ zurück; wirft nie."""
    theme = EVENT_TYPES.get(event_type, EVENT_TYPES[DEFAULT_EVENT_TYPE])
    return theme["occasion_id"]


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
