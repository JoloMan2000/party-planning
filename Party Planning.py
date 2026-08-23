"""
Party-Planungs-Fragebogen 🌿🪵✨
==================================

Linkbasierte Streamlit-App im Bauwagen-Gartenparty-Design: Gäste öffnen einen
Link und beantworten in vier Schritten (Name & Uhrzeit -> Getränke -> Essen ->
Songwünsche) einen kurzen Fragebogen. Der Admin (du) öffnet einen zweiten,
geheimen Link und bekommt eine Auswertung inkl. Einkaufsliste mit Mengen pro
Person sowie die Möglichkeit, aus den Songwünschen automatisch eine
Spotify-Playlist zu erstellen.

Lokal ausführen:
    pip install -r requirements.txt
    streamlit run "Party Planning.py"

Admin-Token:
    Der Admin-Token wird NICHT im Code gespeichert, sondern über Streamlit
    Secrets gesetzt (Datei .streamlit/secrets.toml lokal bzw. "Secrets" im
    Streamlit Community Cloud Dashboard):

        admin_token = "dein-geheimer-wert"

    Der Admin-Bereich ist dann erreichbar über:
        <deine-app-url>/?admin=<admin_token>

Spotify-Playlist (optional):
    Für die Playlist-Erstellung im Admin-Bereich zusätzlich in den Secrets:

        spotify_client_id = "..."
        spotify_client_secret = "..."
        spotify_redirect_uri = "<deine-app-url>/?admin=<admin_token>"

    Details zur Einrichtung siehe README.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import defaultdict
from datetime import date as ddate, datetime, time as dtime
from pathlib import Path

import streamlit as st

import calendar_export
import event_theme
import spotify_playlist
import music_engine.admin_settings as music_admin_settings
from music_engine.catalog import load_music_catalog
from music_engine.domain import MusicCatalog, MusicOccasionProfile, MusicPlanningResult
from music_engine.engine import plan_party_music
from music_engine.legacy_adapter import raw_song_requests_from_responses
from music_engine.occasions import get_music_occasion, load_all_music_occasions
from music_engine.spotify_adapter import songs_from_planning_result
from party_engine.catalog import load_catalog
from party_engine.domain import CatalogItem, DietaryProfile, GuestResponse, PartyCatalog, PartyConfig
from party_engine.engine import compute_party_demand
from party_engine.legacy_adapter import guest_response_from_row
from party_engine.occasions import load_all_occasions
from party_engine.recommendation import (
    format_score_explanation,
    recommend_for_admin,
    recommend_for_guest,
    resolve_occasion_for_scoring,
)
from party_engine.recommendation_domain import OccasionProfile, PartyContext
from translations import (
    ALL_LANGUAGES,
    DEFAULT_LANGUAGE,
    EXTRA_LANGUAGES,
    PRIMARY_LANGUAGES,
    catalog_item_name,
    t,
)

# --- Konfiguration ------------------------------------------------------

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "responses.db"

# Admin-Token kommt aus Streamlit Secrets (siehe Modul-Docstring oben).
ADMIN_TOKEN = st.secrets.get("admin_token", "change-me-to-a-secret-value")

# Spotify-Zugangsdaten kommen ebenfalls aus Streamlit Secrets (optional).
SPOTIFY_CLIENT_ID = st.secrets.get("spotify_client_id", "")
SPOTIFY_CLIENT_SECRET = st.secrets.get("spotify_client_secret", "")
SPOTIFY_REDIRECT_URI = st.secrets.get("spotify_redirect_uri", "")
SPOTIFY_CONFIGURED = bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REDIRECT_URI)

# Event-Typ + Party-Name (admin-konfigurierbar, siehe event_theme.py). Reine
# SQLite-Operationen (keine Streamlit-Rendering-Calls) - dürfen daher schon
# vor st.set_page_config() laufen, um den dynamischen page_title zu setzen.
event_theme.init_party_settings(DB_PATH)
_PARTY_SETTINGS = event_theme.get_party_settings(DB_PATH)
music_admin_settings.init_music_admin_settings(DB_PATH)

@st.cache_resource
def get_catalog() -> PartyCatalog:
    """Lädt den vollständigen Party-Katalog genau einmal pro Streamlit-Prozess
    (AUFGABE §44) - die eigentliche Ladelogik/das Parsing bleibt in
    party_engine.catalog (Streamlit-frei), hier kommt nur die
    Streamlit-Cache-Anbindung dazu (siehe party_engine/catalog.py Docstring)."""
    return load_catalog()


@st.cache_resource
def get_occasions() -> dict[str, OccasionProfile]:
    """Lädt alle 23 Occasion-Profile der Recommendation Engine genau einmal
    pro Streamlit-Prozess (analog zu get_catalog() - siehe
    party_engine/occasions.py Docstring)."""
    return load_all_occasions()


def get_active_occasion() -> OccasionProfile:
    """Löst den aktuell vom Admin konfigurierten Event-Typ (event_theme.py)
    auf das zugehörige OccasionProfile der Recommendation Engine auf (siehe
    EVENT_TYPES[...]['occasion_id']). Empfehlungen sind rein additiv (§78/§79
    der Recommendation-Spec) - beeinflussen niemals den Getränke-/Essenskatalog
    oder die Demand-Pipeline, nur was als "✨ empfohlen" hervorgehoben wird."""
    occasion_id = event_theme.resolve_occasion_id(_PARTY_SETTINGS["event_type"])
    return resolve_occasion_for_scoring([occasion_id], get_occasions())


@st.cache_resource
def get_music_catalog() -> MusicCatalog:
    """Lädt den Musik-Track-Katalog der Music Recommendation & Party Playlist
    Engine genau einmal pro Streamlit-Prozess (analog zu get_catalog(), siehe
    music_engine/catalog.py Docstring)."""
    return load_music_catalog()


@st.cache_resource
def get_music_occasions() -> dict[str, MusicOccasionProfile]:
    """Lädt alle musikalischen Occasion-Profile genau einmal pro
    Streamlit-Prozess (analog zu get_occasions(), siehe
    music_engine/occasions.py Docstring)."""
    return load_all_music_occasions()


def get_active_music_occasion() -> MusicOccasionProfile:
    """Löst den aktuell vom Admin konfigurierten Event-Typ auf das zugehörige
    ``MusicOccasionProfile`` der Music Engine auf (analog zu
    get_active_occasion(), aber für den separaten Musik-Occasion-Katalog unter
    music_catalog/occasions/)."""
    occasion_id = event_theme.resolve_occasion_id(_PARTY_SETTINGS["event_type"])
    return get_music_occasion(occasion_id, get_music_occasions())


# --- Katalog-getriebene Getränke-/Essens-Auswahl (AUFGABE §38-39, §45) ------
#
# Die frühere fest codierte DRINK_OPTIONS/FOOD_OPTIONS-Liste (10 Getränke, 4
# grobe Essenskategorien) ist vollständig abgelöst. Auswählbare Optionen
# kommen jetzt ausschließlich aus `PartyCatalog` (party_engine/catalog.py).
# Die folgenden Gruppierungen sind reine UI-Anzeige-Hilfen (welcher Tab zeigt
# welche Katalog-`category`n) - sie enthalten selbst KEINE Fach-/Mengenlogik
# und müssen bei neuen Katalogeinträgen i.d.R. nicht angepasst werden, solange
# neue Einträge in eine der bestehenden Katalog-`category`-Werte fallen.

_DRINK_DEMAND_GROUPS = {"alcoholic_beverage", "non_alcoholic_beverage", "energy", "beverage_general"}
_FOOD_DEMAND_GROUPS = {"main", "side", "snack", "dessert", "condiment", "salad"}

# Katalog-`category` -> UI-Gruppenschlüssel (Getränke)
_DRINK_CATEGORY_TO_GROUP = {
    "beer": "beer",
    "wine": "wine",
    "sparkling_wine": "wine",
    "fortified_wine": "wine",
    "softdrink": "softdrinks",
    "softdrink_mix": "softdrinks",
    "water": "nonalcoholic",
    "coffee": "nonalcoholic",
    "energy": "nonalcoholic",
    "juice": "juices",
    "spirit": "spirits",
    "liqueur": "spirits",
    "cocktail_vodka": "cocktails",
    "cocktail_gin": "cocktails",
    "cocktail_rum": "cocktails",
    "cocktail_tequila": "cocktails",
    "cocktail_whiskey": "cocktails",
    "cocktail_brandy": "cocktails",
    "cocktail_spritz": "cocktails",
    "cocktail_longdrink": "cocktails",
    "cocktail_complex": "cocktails",
}
_DRINK_GROUP_ORDER = ["beer", "wine", "softdrinks", "nonalcoholic", "cocktails", "spirits", "juices", "other"]
_DRINK_GROUP_LABEL_KEYS = {
    "beer": "drink_group_beer",
    "wine": "drink_group_wine",
    "softdrinks": "drink_group_softdrinks",
    "nonalcoholic": "drink_group_nonalcoholic",
    "cocktails": "drink_group_cocktails",
    "spirits": "drink_group_spirits",
    "juices": "drink_group_juices",
    "other": "drink_group_other",
}

# Katalog-`category` -> UI-Gruppenschlüssel (Essen)
_FOOD_CATEGORY_TO_GROUP = {
    "grill": "grill",
    "burger": "burger",
    "veg_grill": "veg",
    "main_dish": "warm",
    "bread": "sides",
    "side": "sides",
    "salad": "salads",
    "fingerfood": "snacks",
    "snack": "snacks",
    "cheese": "snacks",
    "fruit": "snacks",
    "vegetable": "snacks",
    "sauce": "dips",
    "dessert": "desserts",
}
_FOOD_GROUP_ORDER = ["grill", "burger", "veg", "warm", "sides", "salads", "snacks", "dips", "desserts"]
_FOOD_GROUP_LABEL_KEYS = {
    "grill": "food_group_grill",
    "burger": "food_group_burger",
    "veg": "food_group_veg",
    "warm": "food_group_warm",
    "sides": "food_group_sides",
    "salads": "food_group_salads",
    "snacks": "food_group_snacks",
    "dips": "food_group_dips",
    "desserts": "food_group_desserts",
}


def _drink_items(catalog: PartyCatalog) -> list[CatalogItem]:
    items = list(catalog.direct_consumables.values()) + list(catalog.recipes.values())
    return [i for i in items if i.demand_group in _DRINK_DEMAND_GROUPS]


def _food_items(catalog: PartyCatalog) -> list[CatalogItem]:
    items = list(catalog.direct_consumables.values()) + list(catalog.recipes.values())
    return [i for i in items if i.demand_group in _FOOD_DEMAND_GROUPS]


def _drink_group_key(item: CatalogItem) -> str:
    return _DRINK_CATEGORY_TO_GROUP.get(item.category, "other")


def _food_group_key(item: CatalogItem) -> str:
    # Designentscheidung: Hotdog-Varianten liegen katalogseitig in der
    # `grill`-Kategorie (gemeinsam mit z.B. Bratwurst/Steak), gehören UX-seitig
    # aber klar zu "Burger & Hotdogs" (AUFGABE §38) - daher hier ein gezielter
    # ID-basierter Override statt einer neuen Katalog-Kategorie.
    if "hotdog" in item.id:
        return "burger"
    return _FOOD_CATEGORY_TO_GROUP.get(item.category, "snacks")


def render_catalog_picker(
    lang: str,
    items: list[CatalogItem],
    group_key_fn,
    group_order: list[str],
    group_label_keys: dict[str, str],
    state_key_prefix: str,
    recommended_ids: list[str] = (),
    recommended_label: str = "",
) -> list[str]:
    """Rendert eine kompakte, katalog-getriebene Auswahl: optionale
    "✨ Empfohlen"-Sektion + "Beliebt"-Sektion + globale Suche +
    Kategorie-Tabs (AUFGABE §38-39, §45) - bewusst KEINE hunderte Checkboxen
    untereinander. Jedes Sub-Widget hat einen eigenen, eindeutigen
    Streamlit-Key (persistiert automatisch beim Vor-/Zurück-Navigieren im
    Wizard); die Rückgabe ist die deduplizierte Vereinigung aller
    Sub-Auswahlen als flache Liste von Katalog-IDs.

    `recommended_ids` (optional, score-sortiert von der Occasion
    Recommendation Engine - siehe party_engine/recommendation.py) rendert
    NUR eine zusätzliche Hervorhebung (eigene Sektion + "✨ "-Präfix in allen
    anderen Listen) - erzeugt selbst KEINE Auswahl und keine Demand (§77/§79
    der Recommendation-Spec: eine Empfehlung ist niemals ein Auto-Select)."""
    by_id = {i.id: i for i in items}
    recommended_set = set(recommended_ids)

    def _display_name(iid: str) -> str:
        return catalog_item_name(iid, by_id[iid].name, lang)

    def _format_name(iid: str) -> str:
        prefix = t(lang, "recommended_item_prefix") if iid in recommended_set else ""
        return f"{prefix}{_display_name(iid)}"

    popular_items = sorted((i for i in items if i.popular), key=lambda i: _display_name(i.id))
    grouped: dict[str, list[CatalogItem]] = defaultdict(list)
    for item in items:
        grouped[group_key_fn(item)].append(item)

    selected_ids: list[str] = []

    recommended_in_items = [iid for iid in recommended_ids if iid in by_id]
    if recommended_in_items:
        st.markdown(f"**{t(lang, 'recommended_for_label', occasion=recommended_label)}**")
        selected_ids += st.multiselect(
            t(lang, "recommended_for_label", occasion=recommended_label),
            options=recommended_in_items,
            format_func=_display_name,
            key=f"{state_key_prefix}_recommended",
            label_visibility="collapsed",
        )

    if popular_items:
        st.markdown(f"**{t(lang, 'popular_label')}**")
        selected_ids += st.multiselect(
            t(lang, "popular_label"),
            options=[i.id for i in popular_items],
            format_func=_format_name,
            key=f"{state_key_prefix}_popular",
            label_visibility="collapsed",
        )

    st.markdown(f"**{t(lang, 'catalog_search_label')}**")
    all_sorted = sorted(items, key=lambda i: _display_name(i.id))
    selected_ids += st.multiselect(
        t(lang, "catalog_search_label"),
        options=[i.id for i in all_sorted],
        format_func=_format_name,
        key=f"{state_key_prefix}_search",
        label_visibility="collapsed",
        placeholder=t(lang, "catalog_search_placeholder"),
    )

    available_groups = [g for g in group_order if grouped.get(g)]
    if available_groups:
        tabs = st.tabs([t(lang, group_label_keys[g]) for g in available_groups])
        for tab, group_key in zip(tabs, available_groups):
            with tab:
                group_items = sorted(grouped[group_key], key=lambda i: _display_name(i.id))
                selected_ids += st.multiselect(
                    t(lang, group_label_keys[group_key]),
                    options=[i.id for i in group_items],
                    format_func=_format_name,
                    key=f"{state_key_prefix}_cat_{group_key}",
                    label_visibility="collapsed",
                )

    return list(dict.fromkeys(selected_ids))

st.set_page_config(
    page_title=event_theme.resolve_party_title(_PARTY_SETTINGS), page_icon="🌿", layout="centered"
)

# --- Design: Bauwagen-Gartenparty-Theme ----------------------------------


def inject_theme(
    hero_gradient: tuple[str, str, str] = ("#3F2E22", "#4A342A", "#3F5B41"),
    accent_gradient: tuple[str, str] = ("#C68642", "#A8672F"),
) -> None:
    """Injiziert das App-weite CSS-Theme. `hero_gradient` (3 Farben, 135deg,
    für den `.party-hero`-Hintergrund) und `accent_gradient` (2 Farben, für
    `.stButton > button`) kommen vom aktuell aktiven Event-Typ (siehe
    event_theme.py) - Default-Werte entsprechen exakt dem bisherigen fest
    codierten Bauwagen-Sommerparty-Theme (Regressions-Vorgabe: für diesen
    Event-Typ muss die App optisch identisch zum bisherigen Stand bleiben)."""
    hero_c1, hero_c2, hero_c3 = hero_gradient
    accent_c1, accent_c2 = accent_gradient
    # Platzhalter-Token statt f-string/.format(): die CSS-Regeln unten
    # enthalten sehr viele geschweifte Klammern, ein f-string würde jede
    # davon verdoppelt erfordern (fehleranfällig) - str.replace() auf
    # eindeutigen Tokens ist robuster und diff-freundlicher.
    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        .stApp {
            background:
                radial-gradient(circle at 15% 10%, rgba(198, 134, 66, 0.10) 0, transparent 40%),
                radial-gradient(circle at 85% 0%, rgba(63, 91, 65, 0.12) 0, transparent 45%),
                linear-gradient(170deg, #F7F1E3 0%, #F1E9D4 45%, #E7EFE3 100%);
        }

        .block-container {
            padding-top: 2.5rem;
            padding-bottom: 3rem;
            max-width: 760px;
        }

        .party-hero {
            position: relative;
            background: linear-gradient(135deg, __HERO_C1__ 0%, __HERO_C2__ 45%, __HERO_C3__ 100%);
            border-radius: 22px;
            padding: 2.4rem 1.5rem 2.2rem 1.5rem;
            text-align: center;
            box-shadow: 0 16px 40px rgba(63, 46, 34, 0.35);
            margin-bottom: 2rem;
            overflow: hidden;
        }
        .party-hero::before {
            content: "";
            position: absolute;
            inset: 0;
            background-image:
                radial-gradient(circle, rgba(255, 214, 130, 0.9) 2px, transparent 2.5px),
                radial-gradient(circle, rgba(255, 214, 130, 0.55) 1.5px, transparent 2px);
            background-size: 90px 70px, 130px 100px;
            background-position: 10px 15px, 60px 55px;
            opacity: 0.5;
        }
        .party-hero > * {
            position: relative;
        }
        .party-hero h1 {
            font-family: 'Fraunces', serif;
            color: #FBF3E3;
            font-weight: 800;
            font-size: 2.3rem;
            margin: 0;
            letter-spacing: 0.01em;
            text-shadow: 0 2px 10px rgba(0,0,0,0.25);
        }
        .party-hero p {
            color: #E4DAC4;
            font-weight: 500;
            margin: 0.55rem 0 0 0;
            font-size: 1.05rem;
        }
        .party-hero p.party-hero-meta {
            margin-top: 0.85rem;
            font-size: 0.92rem;
            font-weight: 600;
            color: #FBF3E3;
        }

        h2, h3 {
            font-family: 'Fraunces', serif;
            color: #3F2E22;
        }

        .stButton > button {
            background: linear-gradient(120deg, __ACCENT_C1__, __ACCENT_C2__);
            color: #FBF3E3;
            border: none;
            border-radius: 999px;
            padding: 0.55rem 1.5rem;
            font-weight: 600;
            box-shadow: 0 6px 16px rgba(166, 103, 47, 0.35);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 22px rgba(166, 103, 47, 0.45);
            color: #FBF3E3;
        }

        [data-testid="stMetricValue"] {
            color: #A8672F;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 18px !important;
            border-color: rgba(63, 91, 65, 0.25) !important;
            background: rgba(255, 255, 255, 0.55);
            box-shadow: 0 10px 26px rgba(63, 46, 34, 0.08);
        }

        [data-testid="stExpander"] {
            border-radius: 16px !important;
            border-color: rgba(63, 91, 65, 0.25) !important;
        }

        [data-testid="stProgress"] > div > div {
            background-color: #3F5B41 !important;
        }
        </style>
        """
    css = (
        css.replace("__HERO_C1__", hero_c1)
        .replace("__HERO_C2__", hero_c2)
        .replace("__HERO_C3__", hero_c3)
        .replace("__ACCENT_C1__", accent_c1)
        .replace("__ACCENT_C2__", accent_c2)
    )
    st.markdown(css, unsafe_allow_html=True)


def render_hero(title: str, subtitle: str, meta: str | None = None) -> None:
    """``meta`` ist eine optionale, sprachneutrale Zusatzzeile (aktuell:
    Datum/Uhrzeit/Ort der Party, siehe calendar_export.format_party_datetime())
    - wird nur gerendert, falls der Admin bereits ein Datum konfiguriert hat."""
    meta_html = f'<p class="party-hero-meta">{meta}</p>' if meta else ""
    st.markdown(
        f"""
        <div class="party-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Datenbank ------------------------------------------------------------


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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


def save_response(
    name: str,
    start_time: str,
    drinks: list[str],
    drinks_freetext: str,
    food: list[str],
    food_freetext: str,
    songs: list[dict],
) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO responses
                (name, start_time, drinks, drinks_freetext, food, food_freetext, songs, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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


def load_responses() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM responses ORDER BY id").fetchall()
    return [dict(row) for row in rows]


init_db()

# --- Hilfsfunktionen --------------------------------------------------------


def display_name_for_selection(value: str, catalog: PartyCatalog, lang: str = DEFAULT_LANGUAGE) -> str:
    """Zeigt für eine gespeicherte Auswahl den Katalog-Anzeigenamen an, falls
    ``value`` eine bekannte Katalog-ID ist (neues Format). Für Legacy-Zeilen
    (alte, bereits menschenlesbare Options-Strings wie "Bier") oder unbekannte
    IDs wird der Rohwert unverändert zurückgegeben - nice-to-have Anzeige,
    keine Fach-/Mengenlogik (siehe AUFGABE-Task Punkt 3). ``lang`` (Default:
    Deutsch) übersetzt den Katalog-Anzeigenamen optional via
    catalog_item_name() - z.B. für die admin-seitige Rohantworten-Ansicht,
    die eine eigene Sprachauswahl hat (siehe render_admin_view())."""
    item = catalog.get_item(value)
    if item is None:
        return value
    return catalog_item_name(item.id, item.name, lang)


def format_songs(songs_json: str | None) -> str:
    songs = json.loads(songs_json) if songs_json else []
    return "; ".join(f"{s['artist']} – {s['title']}" for s in songs)


def responses_to_csv(responses: list[dict], catalog: PartyCatalog) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Name",
            "Startzeit",
            "Getränke",
            "Getränke (Freitext)",
            "Essen",
            "Essen (Freitext)",
            "Songwünsche",
            "Eingereicht am",
        ]
    )
    for r in responses:
        drinks = [display_name_for_selection(v, catalog) for v in json.loads(r["drinks"])]
        food = [display_name_for_selection(v, catalog) for v in json.loads(r["food"])]
        writer.writerow(
            [
                r["name"],
                r["start_time"],
                ", ".join(drinks),
                r["drinks_freetext"] or "",
                ", ".join(food),
                r["food_freetext"] or "",
                format_songs(r["songs"]),
                r["submitted_at"],
            ]
        )
    return buffer.getvalue()


# --- Event-Intro (Landing Page vor der Sprachauswahl) -----------------------


def render_event_intro(settings: dict) -> None:
    """Themen-Intro-Screen (Party-Name + Event-Branding), der VOR der
    Sprachauswahl angezeigt wird - die Sprache ist an dieser Stelle noch
    nicht bekannt, daher bewusst nur ein pragmatischer zweisprachiger
    Continue-Button statt des vollen t()-i18n-Systems (siehe event_theme.py:
    EVENT_TYPES[...]['intro_subtitle'] folgt demselben Muster)."""
    theme = event_theme.EVENT_TYPES.get(
        settings["event_type"], event_theme.EVENT_TYPES[event_theme.DEFAULT_EVENT_TYPE]
    )
    render_hero(
        f"{theme['emoji']} {event_theme.resolve_party_title(settings)}",
        theme["intro_subtitle"],
        meta=calendar_export.format_party_datetime(settings),
    )

    if st.button("Weiter / Continue ➡️", key="btn_enter_intro", use_container_width=True):
        st.session_state.entered_intro = True
        st.rerun()


# --- Sprachauswahl (Landing Page) --------------------------------------------


def render_language_landing() -> None:
    """Icon-basierte Landing Page zur Sprachauswahl (8 Sprachen + 'weitere')."""
    render_hero("🌿🪵✨", "Choose your language / Wähle deine Sprache")

    cols = st.columns(3)
    for i, (code, name, flag) in enumerate(PRIMARY_LANGUAGES):
        with cols[i % 3]:
            if st.button(f"{flag}\n{name}", key=f"lang_btn_{code}", use_container_width=True):
                st.session_state.language = code
                st.rerun()

    with cols[len(PRIMARY_LANGUAGES) % 3]:
        with st.popover("🌐\nMore", use_container_width=True):
            options = ["–"] + [f"{flag} {name}" for _, name, flag in EXTRA_LANGUAGES]
            choice = st.selectbox("Select language", options, key="extra_lang_select")
            if choice != "–":
                idx = options.index(choice) - 1
                st.session_state.language = EXTRA_LANGUAGES[idx][0]
                st.rerun()


# --- Gäste-Fragebogen --------------------------------------------------------


TOTAL_STEPS = 4


def _guest_recommended_ids(catalog: PartyCatalog, top_n: int = 16) -> list[str]:
    """Liefert score-sortierte Item-IDs für den aktuell im Wizard befindlichen
    Gast (§60/§61/§77 der Recommendation-Spec) - rein additive Hervorhebung,
    erzeugt selbst NIE eine Preference/DemandAllocation (§78). Da der Wizard
    noch keine Diät-Abfrage kennt, wird ein Gast ohne Constraints angenommen
    (DietaryProfile() == keine Einschränkungen == nichts wird ausgeschlossen)."""
    stub_guest = GuestResponse(
        guest_name=st.session_state.get("name", ""),
        start_time="",
        drink_selections=list(st.session_state.get("drinks", [])),
        food_selections=list(st.session_state.get("food", [])),
        dietary=DietaryProfile(),
    )
    already_selected = set(st.session_state.get("drinks", [])) | set(st.session_state.get("food", []))
    occasion_profile = get_active_occasion()
    party_context = PartyContext(occasion_ids=[occasion_profile.id])
    recommended = recommend_for_guest(
        catalog, occasion_profile, party_context, stub_guest,
        already_selected_ids=already_selected, top_n=top_n,
    )
    return [item.id for item, _score in recommended]


def render_calendar_export_section(lang: str, theme: dict) -> None:
    """Zeigt Gästen nach dem Absenden des Fragebogens eine 'Zum Kalender
    hinzufügen'-Sektion (Google Calendar + .ics-Download für Apple
    Calendar/Outlook/Android) an - siehe calendar_export.py. Blendet sich
    komplett aus, solange der Admin noch kein Party-Datum in den
    Party-Einstellungen (render_party_settings_section) konfiguriert hat."""
    if not calendar_export.has_scheduled_date(_PARTY_SETTINGS):
        return
    title = f"{theme['emoji']} {event_theme.resolve_party_title(_PARTY_SETTINGS)}"
    st.divider()
    st.subheader(t(lang, "calendar_section_header"))
    google_url = calendar_export.google_calendar_url(_PARTY_SETTINGS, title)
    if google_url:
        st.link_button(t(lang, "calendar_google_button"), google_url)
    ics = calendar_export.ics_content(_PARTY_SETTINGS, title)
    if ics:
        st.download_button(
            t(lang, "calendar_ics_button"),
            data=ics,
            file_name="party.ics",
            mime="text/calendar",
        )


def render_guest_form() -> None:
    if "entered_intro" not in st.session_state:
        st.session_state.entered_intro = False

    if not st.session_state.entered_intro:
        render_event_intro(_PARTY_SETTINGS)
        return

    if "language" not in st.session_state:
        st.session_state.language = None

    if st.session_state.language is None:
        render_language_landing()
        return

    lang = st.session_state.language

    if "step" not in st.session_state:
        st.session_state.step = 1
        st.session_state.name = ""
        st.session_state.start_time = dtime(19, 0)
        st.session_state.drinks = []
        st.session_state.drinks_freetext = ""
        st.session_state.food = []
        st.session_state.food_freetext = ""
        st.session_state.songs = []
        st.session_state.song_input_generation = 0
        st.session_state.submitted = False

    theme = event_theme.EVENT_TYPES.get(
        _PARTY_SETTINGS["event_type"], event_theme.EVENT_TYPES[event_theme.DEFAULT_EVENT_TYPE]
    )
    render_hero(
        f"{theme['emoji']} {event_theme.resolve_party_title(_PARTY_SETTINGS)}",
        t(lang, "hero_subtitle"),
        meta=calendar_export.format_party_datetime(_PARTY_SETTINGS),
    )

    if st.session_state.submitted:
        st.success(t(lang, "submitted_msg"))
        render_calendar_export_section(lang, theme)
        return

    st.progress(st.session_state.step / TOTAL_STEPS)

    with st.container(border=True):
        if st.session_state.step == 1:
            st.subheader(t(lang, "step1_header", n=TOTAL_STEPS))
            st.session_state.name = st.text_input(t(lang, "name_label"), value=st.session_state.name)
            st.session_state.start_time = st.time_input(
                t(lang, "time_label"), value=st.session_state.start_time
            )
            if st.button(t(lang, "btn_next"), disabled=not st.session_state.name.strip()):
                st.session_state.step = 2
                st.rerun()

        elif st.session_state.step == 2:
            st.subheader(t(lang, "step2_header", n=TOTAL_STEPS))
            st.caption(t(lang, "drinks_label"))
            catalog = get_catalog()
            occasion_profile = get_active_occasion()
            occasion_label = occasion_profile.label_de if lang == "de" else occasion_profile.label_en
            st.session_state.drinks = render_catalog_picker(
                lang,
                _drink_items(catalog),
                _drink_group_key,
                _DRINK_GROUP_ORDER,
                _DRINK_GROUP_LABEL_KEYS,
                state_key_prefix="drinks",
                recommended_ids=_guest_recommended_ids(catalog),
                recommended_label=occasion_label,
            )
            st.session_state.drinks_freetext = st.text_input(
                t(lang, "drinks_freetext_label"), value=st.session_state.drinks_freetext
            )
            col1, col2 = st.columns(2)
            if col1.button(t(lang, "btn_back")):
                st.session_state.step = 1
                st.rerun()
            if col2.button(t(lang, "btn_next")):
                st.session_state.step = 3
                st.rerun()

        elif st.session_state.step == 3:
            st.subheader(t(lang, "step3_header", n=TOTAL_STEPS))
            st.caption(t(lang, "food_label"))
            catalog = get_catalog()
            occasion_profile = get_active_occasion()
            occasion_label = occasion_profile.label_de if lang == "de" else occasion_profile.label_en
            st.session_state.food = render_catalog_picker(
                lang,
                _food_items(catalog),
                _food_group_key,
                _FOOD_GROUP_ORDER,
                _FOOD_GROUP_LABEL_KEYS,
                state_key_prefix="food",
                recommended_ids=_guest_recommended_ids(catalog),
                recommended_label=occasion_label,
            )
            st.session_state.food_freetext = st.text_input(
                t(lang, "food_freetext_label"), value=st.session_state.food_freetext
            )
            col1, col2 = st.columns(2)
            if col1.button(t(lang, "btn_back"), key="btn_back_step3"):
                st.session_state.step = 2
                st.rerun()
            if col2.button(t(lang, "btn_next"), key="btn_next_step3"):
                st.session_state.step = 4
                st.rerun()

        elif st.session_state.step == 4:
            st.subheader(t(lang, "step4_header", n=TOTAL_STEPS))
            st.caption(t(lang, "step4_caption"))

            gen = st.session_state.song_input_generation
            col1, col2 = st.columns(2)
            artist = col1.text_input(t(lang, "artist_label"), key=f"song_artist_input_{gen}")
            title = col2.text_input(t(lang, "title_label"), key=f"song_title_input_{gen}")
            if st.button(t(lang, "btn_add_song"), disabled=not (artist.strip() and title.strip())):
                st.session_state.songs.append({"artist": artist.strip(), "title": title.strip()})
                st.session_state.song_input_generation += 1
                st.rerun()

            if st.session_state.songs:
                st.write(t(lang, "your_songs_label"))
                for i, song in enumerate(st.session_state.songs):
                    row1, row2 = st.columns([5, 1])
                    row1.write(f"🎶 {song['artist']} – {song['title']}")
                    if row2.button("❌", key=f"remove_song_{i}"):
                        st.session_state.songs.pop(i)
                        st.rerun()

            col1, col2 = st.columns(2)
            if col1.button(t(lang, "btn_back"), key="btn_back_step4"):
                st.session_state.step = 3
                st.rerun()
            if col2.button(t(lang, "btn_submit")):
                save_response(
                    name=st.session_state.name.strip(),
                    start_time=st.session_state.start_time.strftime("%H:%M"),
                    drinks=st.session_state.drinks,
                    drinks_freetext=st.session_state.drinks_freetext,
                    food=st.session_state.food,
                    food_freetext=st.session_state.food_freetext,
                    songs=st.session_state.songs,
                )
                st.session_state.submitted = True
                st.rerun()

    if st.button(t(lang, "change_language")):
        st.session_state.language = None
        st.rerun()


# --- Admin-Ansicht -----------------------------------------------------------


def render_party_settings_section(lang: str) -> None:
    """Admin-Sektion zum EINMALIGEN Festlegen von Event-Typ + Party-Name für
    die gesamte Party (siehe event_theme.py) - beeinflusst nur Optik/Text
    (Titel, Icon, Hero-/Button-Farbverlauf, Intro-Untertitel), NICHT den
    Getränke-/Essenskatalog oder die Wizard-Fragen."""
    settings = event_theme.get_party_settings(DB_PATH)
    event_type_keys = list(event_theme.EVENT_TYPES.keys())

    def _format_event_type(key: str) -> str:
        theme = event_theme.EVENT_TYPES[key]
        label = theme["label_de"] if lang == "de" else theme["label_en"]
        return f"{theme['emoji']} {label}"

    with st.expander(t(lang, "party_settings_header"), expanded=not settings["party_name"]):
        chosen_type = st.selectbox(
            t(lang, "event_type_label"),
            event_type_keys,
            index=event_type_keys.index(settings["event_type"]),
            format_func=_format_event_type,
            key="party_settings_event_type",
        )
        default_title = event_theme.EVENT_TYPES[chosen_type]["default_title"]
        party_name = st.text_input(
            t(lang, "party_name_label"),
            value=settings["party_name"],
            placeholder=t(lang, "party_name_placeholder", default_title=default_title),
            key="party_settings_party_name",
        )

        existing_date = ddate.fromisoformat(settings["party_date"]) if settings["party_date"] else None
        party_date = st.date_input(
            t(lang, "party_date_label"),
            value=existing_date,
            key="party_settings_date",
        )
        existing_start_time = (
            dtime.fromisoformat(settings["party_start_time"]) if settings["party_start_time"] else dtime(19, 0)
        )
        party_start_time = st.time_input(
            t(lang, "party_start_time_label"),
            value=existing_start_time,
            key="party_settings_start_time",
        )
        party_duration_hours = st.number_input(
            t(lang, "party_duration_label"),
            min_value=0.5,
            max_value=48.0,
            step=0.5,
            value=float(settings["party_duration_hours"]),
            key="party_settings_duration",
        )
        party_location = st.text_input(
            t(lang, "party_location_label"),
            value=settings["party_location"],
            placeholder=t(lang, "party_location_placeholder"),
            key="party_settings_location",
        )

        if st.button(t(lang, "btn_save_party_settings"), key="party_settings_save_btn"):
            event_theme.save_party_settings(
                DB_PATH,
                chosen_type,
                party_name,
                party_date=party_date.isoformat() if party_date else "",
                party_start_time=party_start_time.strftime("%H:%M"),
                party_duration_hours=party_duration_hours,
                party_location=party_location,
            )
            st.success(t(lang, "party_settings_saved"))
            st.rerun()


def render_recommendations_section(lang: str, responses: list[dict], catalog: PartyCatalog) -> None:
    """Admin-Sortiment-Empfehlungen (§58/§59/§83 der Recommendation-Spec):
    rein informativer Vorschlag für den Sortiment-Aufbau basierend auf dem
    aktuell konfigurierten Event-Typ (event_theme.py -> Occasion Recommendation
    Engine). Erzeugt garantiert KEINE Preference/DemandAllocation/
    IngredientDemand (§78) und kauft/wählt nichts automatisch (§79) - die
    Einkaufsliste basiert weiterhin ausschließlich auf tatsächlichen
    Gäste-Antworten (siehe render_shopping_list/compute_party_demand)."""
    already_selected_ids: set[str] = set()
    for r in responses:
        already_selected_ids.update(json.loads(r["drinks"]))
        already_selected_ids.update(json.loads(r["food"]))

    occasion_profile = get_active_occasion()
    occasion_label = occasion_profile.label_de if lang == "de" else occasion_profile.label_en
    party_context = PartyContext(occasion_ids=[occasion_profile.id], guest_count=len(responses) or None)

    recommended = recommend_for_admin(
        catalog, occasion_profile, party_context,
        already_selected_ids=already_selected_ids, top_n=20,
    )

    with st.expander(t(lang, "admin_recommendations_header", occasion=occasion_label), expanded=False):
        st.caption(t(lang, "admin_recommendations_caption"))
        for item, score in recommended:
            st.markdown(f"- **{catalog_item_name(item.id, item.name, lang)}** — {score.total_score:.2f}")
            with st.expander(t(lang, "admin_recommendations_score_expander"), expanded=False):
                st.text(format_score_explanation(score, lang=lang if lang in ("de", "en") else "en"))


def render_music_playlist_section(lang: str, responses: list[dict]) -> None:
    """Admin-Sektion für die Music Recommendation & Party Playlist Engine
    (music_engine/, AUFGABE-Musik-Spec §60-92): Admin-Steuerparameter
    (Sliders/Checkbox), Playlist-Generierung via
    ``music_engine.engine.plan_party_music()`` und Anzeige der generierten,
    nach Party-Phase gruppierten Playlist inkl. Erklärbarkeit, Review-Hinweisen
    und Gäste-Abdeckung. Rein additiv - beeinflusst weder den bestehenden
    Spotify-Export (render_spotify_section) noch die Getränke-/Essens-Pipeline;
    kein Songwunsch wird dabei aus der Datenbank gelöscht (Spec §8)."""
    settings = music_admin_settings.get_admin_music_settings(DB_PATH)

    with st.expander(t(lang, "music_settings_header"), expanded=False):
        party_intensity = st.slider(
            t(lang, "music_party_intensity_label"), 0.0, 1.0, settings.party_intensity, 0.05,
            key="music_settings_intensity",
        )
        mainstream_discovery = st.slider(
            t(lang, "music_mainstream_discovery_label"), 0.0, 1.0, settings.mainstream_discovery, 0.05,
            key="music_settings_mainstream",
        )
        guest_request_priority = st.slider(
            t(lang, "music_guest_request_priority_label"), 0.0, 1.0, settings.guest_request_priority, 0.05,
            key="music_settings_guest_priority",
        )
        explicit_allowed = st.checkbox(
            t(lang, "music_explicit_allowed_label"), value=settings.explicit_allowed, key="music_settings_explicit",
        )
        max_tracks_per_artist = st.number_input(
            t(lang, "music_max_tracks_per_artist_label"), min_value=1, max_value=10,
            value=settings.max_tracks_per_artist, key="music_settings_max_artist",
        )

        if st.button(t(lang, "btn_save_music_settings"), key="music_settings_save_btn"):
            settings.party_intensity = party_intensity
            settings.mainstream_discovery = mainstream_discovery
            settings.guest_request_priority = guest_request_priority
            settings.explicit_allowed = explicit_allowed
            settings.max_tracks_per_artist = int(max_tracks_per_artist)
            music_admin_settings.save_admin_music_settings(DB_PATH, settings)
            st.success(t(lang, "music_settings_saved"))
            st.rerun()

    st.subheader(t(lang, "music_playlist_header"))

    if st.button(t(lang, "btn_generate_playlist"), key="music_generate_btn"):
        catalog = get_music_catalog()
        occasion_profile = get_active_music_occasion()
        raw_requests = raw_song_requests_from_responses(responses)
        track_overrides = music_admin_settings.get_track_overrides(DB_PATH)
        artist_overrides = music_admin_settings.get_artist_overrides(DB_PATH)
        result = plan_party_music(
            raw_song_requests=raw_requests,
            party_duration_minutes=_PARTY_SETTINGS["party_duration_hours"] * 60.0,
            occasion_profile=occasion_profile,
            admin_settings=settings,
            catalog=catalog,
            admin_track_overrides=track_overrides,
            admin_artist_overrides=artist_overrides,
        )
        st.session_state["music_planning_result"] = result

    result: MusicPlanningResult | None = st.session_state.get("music_planning_result")
    if result is None:
        st.caption(t(lang, "music_no_playlist_yet"))
        return

    catalog = get_music_catalog()

    col1, col2, col3 = st.columns(3)
    col1.metric(t(lang, "music_metric_tracks"), result.total_tracks)
    col2.metric(t(lang, "music_metric_duration"), f"{result.actual_duration_ms / 60_000:.0f} min")
    col3.metric(
        t(lang, "music_metric_guest_coverage"),
        f"{result.guest_coverage * 100:.0f}%",
    )
    st.caption(
        t(
            lang, "music_requested_coverage_caption",
            selected=result.requested_tracks_selected, total=result.requested_tracks_total,
        )
    )

    if result.review_issues:
        with st.expander(t(lang, "music_review_issues_header"), expanded=True):
            for issue in result.review_issues:
                st.warning(issue)

    with st.expander(t(lang, "music_explanations_header"), expanded=False):
        for explanation in result.explanations:
            st.write(f"- {explanation}")

    phase_labels = {phase.id: (phase.label_de if lang == "de" else phase.label_en) or phase.id for phase in result.phases}
    phase_groups: dict[str, list] = defaultdict(list)
    for slot in result.playlist:
        phase_groups[slot.phase_id].append(slot)

    for phase in result.phases:
        slots = phase_groups.get(phase.id, [])
        if not slots:
            continue
        with st.expander(f"{phase_labels.get(phase.id, phase.id)} ({len(slots)})", expanded=False):
            for slot in slots:
                track = catalog.get_track(slot.track_id)
                title = f"{track.artist} – {track.title}" if track else slot.track_id
                guests = f" ({', '.join(slot.supporting_guests)})" if slot.supporting_guests else ""
                st.write(f"{slot.position + 1}. **{title}**{guests}")
                if slot.reasons:
                    st.caption(" · ".join(slot.reasons))

    if not SPOTIFY_CONFIGURED:
        return
    if not spotify_playlist.is_connected():
        st.caption(t(lang, "spotify_connect_caption"))
        return

    if st.button(t(lang, "btn_export_music_playlist_spotify"), key="music_spotify_export_btn"):
        songs = songs_from_planning_result(result, catalog)
        if not songs:
            st.caption(t(lang, "no_songs"))
        else:
            with st.spinner(t(lang, "playlist_creating")):
                try:
                    export_result = spotify_playlist.build_playlist_from_songs(
                        SPOTIFY_CLIENT_ID,
                        SPOTIFY_CLIENT_SECRET,
                        songs,
                        playlist_name=event_theme.resolve_party_title(_PARTY_SETTINGS),
                        playlist_description="Automatisch erstellt aus der Music Recommendation Engine.",
                    )
                except Exception as e:
                    st.error(t(lang, "playlist_error", e=e))
                else:
                    st.success(t(lang, "playlist_success", n=export_result["track_count"]))
                    st.markdown(f"[{t(lang, 'playlist_open_link')}]({export_result['playlist_url']})")
                    if export_result["not_found"]:
                        with st.expander(t(lang, "not_found_expander", n=len(export_result["not_found"]))):
                            for s in export_result["not_found"]:
                                guest_part = f" ({t(lang, 'from_guest', name=s['guest_name'])})" if s["guest_name"] else ""
                                st.write(f"- {s['artist']} – {s['title']}{guest_part}")


def render_admin_view() -> None:
    if "admin_language" not in st.session_state:
        st.session_state.admin_language = DEFAULT_LANGUAGE

    lang_labels = [f"{flag} {name}" for _, name, flag in ALL_LANGUAGES]
    lang_codes = [code for code, _, _ in ALL_LANGUAGES]
    current_idx = lang_codes.index(st.session_state.admin_language)
    chosen = st.selectbox(
        t(st.session_state.admin_language, "admin_language_label"),
        lang_labels,
        index=current_idx,
        key="admin_language_select",
    )
    st.session_state.admin_language = lang_codes[lang_labels.index(chosen)]
    lang = st.session_state.admin_language

    render_hero(t(lang, "admin_title"), t(lang, "admin_subtitle"))

    render_party_settings_section(lang)

    responses = load_responses()
    catalog = get_catalog()

    render_recommendations_section(lang, responses, catalog)

    render_music_playlist_section(lang, responses)

    if not responses:
        st.info(t(lang, "no_responses_yet"))
        render_spotify_section(responses, lang)
        return

    st.metric(t(lang, "metric_responses"), len(responses))

    st.download_button(
        t(lang, "btn_csv"),
        data=responses_to_csv(responses, catalog),
        file_name="party_antworten.csv",
        mime="text/csv",
        help=t(lang, "csv_help"),
    )

    with st.expander(t(lang, "raw_responses_expander")):
        for r in responses:
            drinks = ", ".join(display_name_for_selection(v, catalog, lang) for v in json.loads(r["drinks"])) or "–"
            food = ", ".join(display_name_for_selection(v, catalog, lang) for v in json.loads(r["food"])) or "–"
            extra_drinks = f" + {r['drinks_freetext']}" if r["drinks_freetext"] else ""
            extra_food = f" + {r['food_freetext']}" if r["food_freetext"] else ""
            songs = format_songs(r["songs"]) or "–"
            st.write(
                f"**{r['name']}** – {r['start_time']} | "
                f"{drinks}{extra_drinks} | {food}{extra_food} | {songs}"
            )

    if st.button(t(lang, "btn_create_shopping_list")):
        render_shopping_list(responses, catalog, lang)

    render_spotify_section(responses, lang)


def render_shopping_list(responses: list[dict], catalog: PartyCatalog, lang: str) -> None:
    """Unified Shopping-List-Ansicht (AUFGABE §40-41): ersetzt die früheren
    getrennten Getränke-/Essen-Sektionen durch EINE Ansicht, die auf der
    vollständigen Demand-Pipeline (``compute_party_demand``) basiert - egal
    ob ein Getränk oder ein Gericht die Zutat letztlich benötigt."""
    guest_responses = [guest_response_from_row(r, catalog) for r in responses]
    result = compute_party_demand(catalog, guest_responses, PartyConfig())

    st.subheader(t(lang, "times_header", n=len(responses)))
    st.write(", ".join(sorted(r["start_time"] for r in responses)))

    # --- Präferenzübersicht (§40: "Espresso Martini - 14 Unterstützer, 8,3 erwartete Portionen") ---
    st.subheader(t(lang, "item_overview_header"))
    if not result.item_demand:
        st.caption(t(lang, "no_item_demand"))
    for summary in result.item_demand:
        st.write(
            f"- **{summary.item_name}** — {summary.supporters} {t(lang, 'supporting_guests_label')}, "
            f"{summary.expected_servings:.1f} {t(lang, 'expected_servings_label')}"
        )

    # --- Ingredient Demand mit Erklärbarkeit (§41) ---
    st.subheader(t(lang, "ingredient_demand_header"))
    if not result.ingredient_demand:
        st.caption(t(lang, "no_ingredient_demand"))
    for ingredient_id, demand in sorted(result.ingredient_demand.items(), key=lambda kv: kv[1].name):
        st.markdown(f"**{demand.name}** — {demand.quantity_after_reserve:.2f} {demand.unit}")
        with st.expander(t(lang, "details_expander")):
            ingredient = catalog.ingredients.get(ingredient_id)
            if ingredient is not None:
                st.write(f"{t(lang, 'family_label')}: {ingredient.family}")
            st.write(f"{t(lang, 'contributions_label')}:")
            for contribution in demand.contributions:
                st.write(f"　　{contribution.source_item_name}: {contribution.amount:.3f} {contribution.unit}")
            st.write(f"{t(lang, 'raw_quantity_label')}: {demand.raw_quantity:.3f} {demand.unit}")
            st.write(f"{t(lang, 'reserve_label')}: {demand.reserve_pct * 100:.0f}%")
            st.write(f"{t(lang, 'qty_after_reserve_label')}: {demand.quantity_after_reserve:.3f} {demand.unit}")

    # --- Purchase Plan (§35, §40-41) ---
    st.subheader(t(lang, "purchase_plan_header"))
    if not result.purchase_plan:
        st.caption(t(lang, "no_purchase_plan"))
    for plan_item in result.purchase_plan:
        breakdown_text = ", ".join(
            f"{b.count} × {b.size:g} {b.unit}" + (f" ({b.pack_label})" if b.pack_label else "")
            for b in plan_item.sku_breakdown
        ) or "–"
        st.write(
            f"- **{plan_item.name}**: {breakdown_text} "
            f"({t(lang, 'total_purchased_label')}: {plan_item.total_purchased_quantity:.2f} {plan_item.unit})"
        )

    # --- Eisbedarf ---
    st.subheader(t(lang, "ice_demand_label"))
    st.write(f"{result.ice_demand_kg:.2f} kg")

    # --- Review Issues (unbekannte Freitexte, niedrige Confidence, Allergien, ...) ---
    if result.review_issues:
        with st.expander(t(lang, "review_issues_header", n=len(result.review_issues))):
            for issue in result.review_issues:
                guest_part = f" ({t(lang, 'from_guest', name=issue.guest_name)})" if issue.guest_name else ""
                st.write(f"- [{issue.issue_type}] {issue.message}{guest_part}")
    else:
        st.caption(t(lang, "no_review_issues"))


def render_spotify_section(responses: list[dict], lang: str = DEFAULT_LANGUAGE) -> None:
    st.subheader(t(lang, "spotify_header"))

    if not SPOTIFY_CONFIGURED:
        st.info(t(lang, "spotify_not_configured"))
        return

    status_msg = st.session_state.pop("spotify_status_msg", None)
    if status_msg:
        is_success, msg_key, msg_kwargs = status_msg
        text = t(lang, msg_key, **msg_kwargs)
        (st.success if is_success else st.error)(text)

    if not spotify_playlist.is_connected():
        authorize_url = spotify_playlist.build_authorize_url(
            SPOTIFY_CLIENT_ID, SPOTIFY_REDIRECT_URI, state="admin"
        )
        st.markdown(f"[{t(lang, 'spotify_connect_link')}]({authorize_url})")
        st.caption(t(lang, "spotify_connect_caption"))
        return

    col1, col2 = st.columns([3, 1])
    col1.success(t(lang, "spotify_connected"))
    if col2.button(t(lang, "btn_disconnect")):
        spotify_playlist.disconnect()
        st.rerun()

    if st.button(t(lang, "btn_create_playlist")):
        songs = [
            {"artist": song["artist"], "title": song["title"], "guest_name": r["name"]}
            for r in responses
            for song in json.loads(r["songs"] or "[]")
        ]
        if not songs:
            st.caption(t(lang, "no_songs"))
        else:
            with st.spinner(t(lang, "playlist_creating")):
                try:
                    result = spotify_playlist.build_playlist_from_songs(
                        SPOTIFY_CLIENT_ID,
                        SPOTIFY_CLIENT_SECRET,
                        songs,
                        playlist_name=event_theme.resolve_party_title(event_theme.get_party_settings(DB_PATH)),
                        playlist_description="Automatisch erstellt aus den Songwünschen der Gäste.",
                    )
                except Exception as e:
                    st.error(t(lang, "playlist_error", e=e))
                else:
                    st.success(t(lang, "playlist_success", n=result["track_count"]))
                    st.markdown(f"[{t(lang, 'playlist_open_link')}]({result['playlist_url']})")
                    if result["not_found"]:
                        with st.expander(t(lang, "not_found_expander", n=len(result["not_found"]))):
                            for s in result["not_found"]:
                                st.write(
                                    f"- {s['artist']} – {s['title']} "
                                    f"({t(lang, 'from_guest', name=s['guest_name'])})"
                                )


def handle_spotify_callback(code: str) -> None:
    try:
        spotify_playlist.exchange_code_for_token(
            SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, code
        )
        st.session_state["spotify_status_msg"] = (True, "spotify_connect_success", {})
    except Exception as e:
        st.session_state["spotify_status_msg"] = (False, "spotify_connect_error", {"e": e})


# --- Einstiegspunkt -----------------------------------------------------------

_ACTIVE_EVENT_THEME = event_theme.EVENT_TYPES.get(
    _PARTY_SETTINGS["event_type"], event_theme.EVENT_TYPES[event_theme.DEFAULT_EVENT_TYPE]
)
inject_theme(_ACTIVE_EVENT_THEME["hero_gradient"], _ACTIVE_EVENT_THEME["accent_gradient"])

query_params = st.query_params
is_admin_token_set = ADMIN_TOKEN != "change-me-to-a-secret-value"
is_admin = query_params.get("admin") == ADMIN_TOKEN and is_admin_token_set

if is_admin:
    if "code" in query_params and SPOTIFY_CONFIGURED:
        handle_spotify_callback(query_params.get("code"))
        st.query_params.clear()
        st.query_params["admin"] = ADMIN_TOKEN
        st.rerun()
    render_admin_view()
else:
    render_guest_form()
    st.divider()
    footer_lang = st.session_state.get("language") or DEFAULT_LANGUAGE
    st.caption(t(footer_lang, "admin_hint"))
