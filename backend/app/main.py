"""FastAPI-Einstiegspunkt (Phase-1-Plan Schritt 1/2/5).

Ausführen vom Repo-Root aus (damit ``from party_engine...`` etc. genauso
auflösen wie in ``"Party Planning.py"``, keine ``sys.path``-Hacks):

    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import accounts.invitation_storage as invitation_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
import event_theme
import music_engine.admin_settings as music_admin_settings
import party_engine.response_storage as response_storage
from backend.app.core.config import settings
from backend.app.routers import (
    admin_catalog_curation,
    admin_music,
    admin_party_context,
    admin_party_settings,
    admin_recommendations,
    admin_responses,
    admin_shopping_list,
    auth,
    catalog,
    guest,
    invitations,
    me,
    parties,
    translations,
)
from party_context import learning_storage
from party_context import storage as party_context_storage
from party_engine.catalog_curation import init_catalog_curation

app = FastAPI(title="Party Planning API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    me.router,
    parties.router,
    invitations.router,
    catalog.router,
    guest.router,
    translations.router,
    admin_responses.router,
    admin_party_settings.router,
    admin_party_context.router,
    admin_catalog_curation.router,
    admin_recommendations.router,
    admin_music.router,
    admin_shopping_list.router,
):
    app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    """Idempotenter Init-Durchlauf - identisch zu den Modul-Level-Aufrufen in
    ``"Party Planning.py"``, sicher parallel zum Streamlit-Prozess gegen
    dieselbe ``responses.db`` aufrufbar."""
    db_path = settings.db_path
    user_storage.init_user_storage(db_path)
    party_storage.init_party_storage(db_path)
    invitation_storage.init_invitation_storage(db_path)
    event_theme.init_party_settings(db_path)
    music_admin_settings.init_music_admin_settings(db_path)
    party_context_storage.init_party_context_storage(db_path)
    learning_storage.init_learning_storage(db_path)
    init_catalog_curation(db_path)
    response_storage.init_db(db_path)

    # WAL-Modus reduziert "database is locked"-Risiko bei parallelem
    # Schreibzugriff von Streamlit- und FastAPI-Prozess (Plan Schritt 2) -
    # einmalig gesetzt, PRAGMA bleibt danach persistent in der DB-Datei.
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
