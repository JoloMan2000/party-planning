"""
Party-Planungs-Fragebogen 🌴☀️🍹
==================================

Linkbasierte Streamlit-App im Sommerparty-Design: Gäste öffnen einen Link und
beantworten in drei Schritten (Name & Uhrzeit -> Getränke -> Essen) einen
kurzen Fragebogen. Der Admin (du) öffnet einen zweiten, geheimen Link und
bekommt eine Auswertung inkl. Einkaufsliste mit Mengen pro Person.

Lokal ausführen:
    pip install streamlit
    streamlit run "Party Planning.py"

Admin-Token:
    Der Admin-Token wird NICHT im Code gespeichert, sondern über Streamlit
    Secrets gesetzt (Datei .streamlit/secrets.toml lokal bzw. "Secrets" im
    Streamlit Community Cloud Dashboard):

        admin_token = "dein-geheimer-wert"

    Der Admin-Bereich ist dann erreichbar über:
        <deine-app-url>/?admin=<admin_token>
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, time as dtime
from pathlib import Path

import streamlit as st

# --- Konfiguration ------------------------------------------------------

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "responses.db"

# Admin-Token kommt aus Streamlit Secrets (siehe Modul-Docstring oben).
ADMIN_TOKEN = st.secrets.get("admin_token", "change-me-to-a-secret-value")

DRINK_OPTIONS = [
    "Bier",
    "Wein (Rot/Weiß)",
    "Softdrinks (Cola, Fanta, Sprite)",
    "Wasser",
]
FOOD_OPTIONS = [
    "Grillfleisch",
    "Vegetarisch/Vegan",
    "Salate",
    "Snacks/Chips",
]

# Geplante Menge pro Person, die die jeweilige Option ausgewählt hat: (Menge, Einheit)
DRINK_QUANTITY_PER_PERSON = {
    "Bier": (2, "Flasche(n) à 0,5 l"),
    "Wein (Rot/Weiß)": (0.25, "l"),
    "Softdrinks (Cola, Fanta, Sprite)": (0.5, "l"),
    "Wasser": (0.5, "l"),
}
FOOD_QUANTITY_PER_PERSON = {
    "Grillfleisch": (200, "g"),
    "Vegetarisch/Vegan": (150, "g"),
    "Salate": (150, "g"),
    "Snacks/Chips": (50, "g"),
}

st.set_page_config(page_title="Summer Party Planung", page_icon="🌴", layout="centered")

# --- Design: Sommerparty-Theme ------------------------------------------


def inject_summer_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: 'Poppins', sans-serif;
        }

        .stApp {
            background: linear-gradient(160deg, #FFF7E8 0%, #FFE8C6 35%, #CDEEE8 100%);
        }

        .summer-hero {
            background: linear-gradient(120deg, #FF6F3C 0%, #FF9A3C 45%, #00A9A5 100%);
            border-radius: 20px;
            padding: 2rem 1.5rem;
            text-align: center;
            box-shadow: 0 10px 30px rgba(255, 111, 60, 0.25);
            margin-bottom: 1.75rem;
        }
        .summer-hero h1 {
            color: white;
            font-weight: 800;
            font-size: 2.1rem;
            margin: 0;
            text-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }
        .summer-hero p {
            color: #FFF3E0;
            font-weight: 600;
            margin: 0.4rem 0 0 0;
            font-size: 1rem;
        }

        .stButton > button {
            background: linear-gradient(120deg, #FF6F3C, #FF9A3C);
            color: white;
            border: none;
            border-radius: 999px;
            padding: 0.55rem 1.4rem;
            font-weight: 600;
            box-shadow: 0 6px 16px rgba(255, 111, 60, 0.35);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(255, 111, 60, 0.45);
            color: white;
        }

        [data-testid="stMetricValue"] {
            color: #FF6F3C;
        }

        h2, h3 {
            color: #1B3B6F;
        }

        [data-testid="stExpander"], .stContainer, div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="summer-hero">
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
                submitted_at TEXT NOT NULL
            )
            """
        )


def save_response(
    name: str,
    start_time: str,
    drinks: list[str],
    drinks_freetext: str,
    food: list[str],
    food_freetext: str,
) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO responses
                (name, start_time, drinks, drinks_freetext, food, food_freetext, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                start_time,
                json.dumps(drinks),
                drinks_freetext,
                json.dumps(food),
                food_freetext,
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


def build_shopping_list(responses: list[dict]) -> dict:
    drink_counts = {opt: 0 for opt in DRINK_OPTIONS}
    food_counts = {opt: 0 for opt in FOOD_OPTIONS}
    drink_freetext_counts: dict[str, int] = {}
    food_freetext_counts: dict[str, int] = {}
    times = []

    for r in responses:
        times.append(r["start_time"])
        for item in json.loads(r["drinks"]):
            if item in drink_counts:
                drink_counts[item] += 1
        for item in parse_freetext_items(r["drinks_freetext"]):
            drink_freetext_counts[item] = drink_freetext_counts.get(item, 0) + 1
        for item in json.loads(r["food"]):
            if item in food_counts:
                food_counts[item] += 1
        for item in parse_freetext_items(r["food_freetext"]):
            food_freetext_counts[item] = food_freetext_counts.get(item, 0) + 1

    return {
        "guest_count": len(responses),
        "times": times,
        "drink_counts": drink_counts,
        "food_counts": food_counts,
        "drink_freetext_counts": drink_freetext_counts,
        "food_freetext_counts": food_freetext_counts,
    }


def responses_to_csv(responses: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Name", "Startzeit", "Getränke", "Getränke (Freitext)", "Essen", "Essen (Freitext)", "Eingereicht am"])
    for r in responses:
        writer.writerow(
            [
                r["name"],
                r["start_time"],
                ", ".join(json.loads(r["drinks"])),
                r["drinks_freetext"] or "",
                ", ".join(json.loads(r["food"])),
                r["food_freetext"] or "",
                r["submitted_at"],
            ]
        )
    return buffer.getvalue()


# --- Gäste-Fragebogen --------------------------------------------------------


def render_guest_form() -> None:
    if "step" not in st.session_state:
        st.session_state.step = 1
        st.session_state.name = ""
        st.session_state.start_time = dtime(19, 0)
        st.session_state.drinks = []
        st.session_state.drinks_freetext = ""
        st.session_state.food = []
        st.session_state.food_freetext = ""
        st.session_state.submitted = False

    render_hero("🌴 Summer Party 🍹", "Sag uns, was du dir für die Party wünschst!")

    if st.session_state.submitted:
        st.success("Danke für deine Antworten! Wir sehen uns auf der Party! 🎉☀️")
        return

    st.progress(st.session_state.step / 3)

    with st.container(border=True):
        if st.session_state.step == 1:
            st.subheader("☀️ Schritt 1 von 3: Wer bist du & wann soll's losgehen?")
            st.session_state.name = st.text_input("Dein Name", value=st.session_state.name)
            st.session_state.start_time = st.time_input(
                "Um wie viel Uhr soll die Party starten?", value=st.session_state.start_time
            )
            if st.button("Weiter ➡️", disabled=not st.session_state.name.strip()):
                st.session_state.step = 2
                st.rerun()

        elif st.session_state.step == 2:
            st.subheader("🍹 Schritt 2 von 3: Getränke")
            st.session_state.drinks = st.multiselect(
                "Was soll's zu trinken geben?", DRINK_OPTIONS, default=st.session_state.drinks
            )
            st.session_state.drinks_freetext = st.text_input(
                "Sonstige Getränkewünsche (mit Komma trennen)", value=st.session_state.drinks_freetext
            )
            col1, col2 = st.columns(2)
            if col1.button("⬅️ Zurück"):
                st.session_state.step = 1
                st.rerun()
            if col2.button("Weiter ➡️"):
                st.session_state.step = 3
                st.rerun()

        elif st.session_state.step == 3:
            st.subheader("🍔 Schritt 3 von 3: Essen")
            st.session_state.food = st.multiselect(
                "Was soll's zu essen geben?", FOOD_OPTIONS, default=st.session_state.food
            )
            st.session_state.food_freetext = st.text_input(
                "Sonstige Essenswünsche (mit Komma trennen)", value=st.session_state.food_freetext
            )
            col1, col2 = st.columns(2)
            if col1.button("⬅️ Zurück "):
                st.session_state.step = 2
                st.rerun()
            if col2.button("✅ Absenden"):
                save_response(
                    name=st.session_state.name.strip(),
                    start_time=st.session_state.start_time.strftime("%H:%M"),
                    drinks=st.session_state.drinks,
                    drinks_freetext=st.session_state.drinks_freetext,
                    food=st.session_state.food,
                    food_freetext=st.session_state.food_freetext,
                )
                st.session_state.submitted = True
                st.rerun()


# --- Admin-Ansicht -----------------------------------------------------------


def render_admin_view() -> None:
    render_hero("🔑 Admin-Dashboard", "Auswertung & Einkaufsliste für deine Summer Party")
    responses = load_responses()

    if not responses:
        st.info("Noch keine Antworten vorhanden.")
        return

    st.metric("Anzahl Antworten", len(responses))

    st.download_button(
        "⬇️ Antworten als CSV sichern",
        data=responses_to_csv(responses),
        file_name="party_antworten.csv",
        mime="text/csv",
        help="Backup empfohlen, da Hosting-Speicher nicht dauerhaft garantiert ist.",
    )

    with st.expander("Alle Antworten (Rohdaten)"):
        for r in responses:
            drinks = ", ".join(json.loads(r["drinks"])) or "–"
            food = ", ".join(json.loads(r["food"])) or "–"
            extra_drinks = f" + {r['drinks_freetext']}" if r["drinks_freetext"] else ""
            extra_food = f" + {r['food_freetext']}" if r["food_freetext"] else ""
            st.write(
                f"**{r['name']}** – Startzeit: {r['start_time']} | "
                f"Getränke: {drinks}{extra_drinks} | Essen: {food}{extra_food}"
            )

    if st.button("🛒 Einkaufsliste erstellen"):
        data = build_shopping_list(responses)

        st.subheader(f"Gewünschte Startzeiten ({data['guest_count']} Antworten)")
        st.write(", ".join(sorted(data["times"])))

        st.subheader("🍹 Getränke-Einkaufsliste")
        any_drinks = False
        for item, count in data["drink_counts"].items():
            if count > 0:
                any_drinks = True
                amount, unit = DRINK_QUANTITY_PER_PERSON[item]
                st.write(f"- **{item}**: {count}x gewählt → {format_total(count, amount, unit)}")
        for item, count in data["drink_freetext_counts"].items():
            any_drinks = True
            st.write(f"- **{item}** (Freitext): {count}x gewünscht")
        if not any_drinks:
            st.caption("Keine Getränke ausgewählt.")

        st.subheader("🍔 Essen-Einkaufsliste")
        any_food = False
        for item, count in data["food_counts"].items():
            if count > 0:
                any_food = True
                amount, unit = FOOD_QUANTITY_PER_PERSON[item]
                st.write(f"- **{item}**: {count}x gewählt → {format_total(count, amount, unit)}")
        for item, count in data["food_freetext_counts"].items():
            any_food = True
            st.write(f"- **{item}** (Freitext): {count}x gewünscht")
        if not any_food:
            st.caption("Keine Essenswünsche ausgewählt.")


# --- Einstiegspunkt -----------------------------------------------------------

inject_summer_theme()

query_params = st.query_params
is_admin_token_set = ADMIN_TOKEN != "change-me-to-a-secret-value"
is_admin = query_params.get("admin") == ADMIN_TOKEN and is_admin_token_set

if is_admin:
    render_admin_view()
else:
    render_guest_form()
    st.divider()
    st.caption("Bist du der Admin? Nutze deinen geheimen Admin-Link.")
