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
from datetime import datetime, time as dtime
from pathlib import Path

import streamlit as st

import spotify_playlist
from drink_model import compute_drink_shopping_list
from translations import (
    ALL_LANGUAGES,
    DEFAULT_LANGUAGE,
    EXTRA_LANGUAGES,
    PRIMARY_LANGUAGES,
    t,
    translate_option,
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

DRINK_OPTIONS = [
    "Bier",
    "Rotwein",
    "Weißwein",
    "Cola",
    "Cola Zero",
    "Fanta",
    "Sprite",
    "Red Bull",
    "Alkoholfreies Bier",
    "Wasser",
]
FOOD_OPTIONS = [
    "Grillfleisch",
    "Vegetarisch/Vegan",
    "Salate",
    "Snacks/Chips",
]

# Geplante Menge pro Person, die die jeweilige Option ausgewählt hat: (Menge, Einheit)
# Hinweis: Die Getränke-Mengen werden NICHT mehr hier berechnet, sondern über
# das Demand-Allocation-Modell in drink_model.py (siehe compute_drink_shopping_list).
FOOD_QUANTITY_PER_PERSON = {
    "Grillfleisch": (200, "g"),
    "Vegetarisch/Vegan": (150, "g"),
    "Salate": (150, "g"),
    "Snacks/Chips": (50, "g"),
}

st.set_page_config(page_title="Bauwagen Gartenparty", page_icon="🌿", layout="centered")

# --- Design: Bauwagen-Gartenparty-Theme ----------------------------------


def inject_theme() -> None:
    st.markdown(
        """
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
            background: linear-gradient(135deg, #3F2E22 0%, #4A342A 45%, #3F5B41 100%);
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

        h2, h3 {
            font-family: 'Fraunces', serif;
            color: #3F2E22;
        }

        .stButton > button {
            background: linear-gradient(120deg, #C68642, #A8672F);
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
        """,
        unsafe_allow_html=True,
    )


def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="party-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
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


def parse_freetext_items(text: str | None) -> list[str]:
    """Zerlegt ein Freitextfeld (kommagetrennt) in einzelne Einträge."""
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def format_total(count: int, amount: float, unit: str) -> str:
    total = count * amount
    if unit == "g" and total >= 1000:
        return f"{total / 1000:.2f} kg"
    if isinstance(total, float) and total.is_integer():
        total = int(total)
    return f"{total} {unit}"


def build_food_list(responses: list[dict]) -> dict:
    food_counts = {opt: 0 for opt in FOOD_OPTIONS}
    food_freetext_counts: dict[str, int] = {}
    times = []

    for r in responses:
        times.append(r["start_time"])
        for item in json.loads(r["food"]):
            if item in food_counts:
                food_counts[item] += 1
        for item in parse_freetext_items(r["food_freetext"]):
            food_freetext_counts[item] = food_freetext_counts.get(item, 0) + 1

    return {
        "guest_count": len(responses),
        "times": times,
        "food_counts": food_counts,
        "food_freetext_counts": food_freetext_counts,
    }


def responses_to_guests(responses: list[dict]) -> list[dict]:
    """Wandelt SQLite-Antworten in das von drink_model.compute_drink_shopping_list
    erwartete Gast-Dict-Format um."""
    return [
        {
            "name": r["name"],
            "drinks": json.loads(r["drinks"]),
            "drinks_freetext": r["drinks_freetext"] or "",
        }
        for r in responses
    ]


def format_songs(songs_json: str | None) -> str:
    songs = json.loads(songs_json) if songs_json else []
    return "; ".join(f"{s['artist']} – {s['title']}" for s in songs)


def responses_to_csv(responses: list[dict]) -> str:
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
        writer.writerow(
            [
                r["name"],
                r["start_time"],
                ", ".join(json.loads(r["drinks"])),
                r["drinks_freetext"] or "",
                ", ".join(json.loads(r["food"])),
                r["food_freetext"] or "",
                format_songs(r["songs"]),
                r["submitted_at"],
            ]
        )
    return buffer.getvalue()


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


def render_guest_form() -> None:
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

    render_hero(t(lang, "landing_title"), t(lang, "hero_subtitle"))

    if st.session_state.submitted:
        st.success(t(lang, "submitted_msg"))
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
            st.session_state.drinks = st.multiselect(
                t(lang, "drinks_label"),
                DRINK_OPTIONS,
                default=st.session_state.drinks,
                format_func=lambda opt: translate_option(lang, "drinks", opt),
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
            st.session_state.food = st.multiselect(
                t(lang, "food_label"),
                FOOD_OPTIONS,
                default=st.session_state.food,
                format_func=lambda opt: translate_option(lang, "food", opt),
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
    responses = load_responses()

    if not responses:
        st.info(t(lang, "no_responses_yet"))
        render_spotify_section(responses, lang)
        return

    st.metric(t(lang, "metric_responses"), len(responses))

    st.download_button(
        t(lang, "btn_csv"),
        data=responses_to_csv(responses),
        file_name="party_antworten.csv",
        mime="text/csv",
        help=t(lang, "csv_help"),
    )

    with st.expander(t(lang, "raw_responses_expander")):
        for r in responses:
            drinks = ", ".join(json.loads(r["drinks"])) or "–"
            food = ", ".join(json.loads(r["food"])) or "–"
            extra_drinks = f" + {r['drinks_freetext']}" if r["drinks_freetext"] else ""
            extra_food = f" + {r['food_freetext']}" if r["food_freetext"] else ""
            songs = format_songs(r["songs"]) or "–"
            st.write(
                f"**{r['name']}** – {r['start_time']} | "
                f"{drinks}{extra_drinks} | {food}{extra_food} | {songs}"
            )

    if st.button(t(lang, "btn_create_shopping_list")):
        food_data = build_food_list(responses)

        st.subheader(t(lang, "times_header", n=food_data["guest_count"]))
        st.write(", ".join(sorted(food_data["times"])))

        st.subheader(t(lang, "drinks_shopping_header"))
        shopping = compute_drink_shopping_list(responses_to_guests(responses))

        def render_drink_row(result) -> None:
            review_flag = " ⚠️" if result.needs_review else ""
            st.markdown(f"**{result.canonical_name}**{review_flag}")
            st.write(
                f"→ {result.purchase_count} × {result.purchase_unit} "
                f"({result.actual_purchase_quantity_l:.2f} l gesamt)"
            )
            st.caption(result.explanation)
            with st.expander(t(lang, "details_expander")):
                st.write(f"{t(lang, 'family_label')}: {result.family}")
                st.write(f"{t(lang, 'supporting_guests_label')}: {result.number_of_supporting_guests}")
                st.write(f"{t(lang, 'weighted_score_label')}: {result.weighted_preference_score}")
                st.write(f"{t(lang, 'calc_qty_label')}: {result.calculated_quantity_l} l")
                st.write(f"{t(lang, 'reserve_label')}: {result.reserve_percentage * 100:.0f}%")
                st.write(f"{t(lang, 'qty_after_reserve_label')}: {result.quantity_after_reserve_l} l")
                st.write(f"{t(lang, 'source_label')}: {result.source}")
                st.write(f"{t(lang, 'confidence_label')}: {result.confidence}")

        render_drink_row(shopping.water)
        if not shopping.drinks:
            st.caption(t(lang, "no_more_drinks"))
        for result in shopping.drinks:
            render_drink_row(result)

        if shopping.admin_hints:
            with st.expander(t(lang, "review_hints_expander", n=len(shopping.admin_hints))):
                for hint in shopping.admin_hints:
                    st.write(f"- {hint}")

        if shopping.unresolved_freetext:
            with st.expander(t(lang, "unresolved_expander", n=len(shopping.unresolved_freetext))):
                for item in shopping.unresolved_freetext:
                    st.write(f"- „{item.raw_text}“ ({t(lang, 'from_guest', name=item.guest_name)})")

        st.subheader(t(lang, "food_shopping_header"))
        any_food = False
        for item, count in food_data["food_counts"].items():
            if count > 0:
                any_food = True
                amount, unit = FOOD_QUANTITY_PER_PERSON.get(item, (1, "Portion(en)"))
                label = translate_option(lang, "food", item)
                st.write(f"- **{label}**: {count}x → {format_total(count, amount, unit)}")
        for item, count in food_data["food_freetext_counts"].items():
            any_food = True
            st.write(f"- **{item}**: {count}x")
        if not any_food:
            st.caption(t(lang, "no_food"))

    render_spotify_section(responses, lang)


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
                        playlist_name="Bauwagen Gartenparty",
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

inject_theme()

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
