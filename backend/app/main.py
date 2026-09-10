"""FastAPI-Einstiegspunkt (Phase-1-Plan Schritt 1/2/5).

Ausführen vom Repo-Root aus (damit ``from party_engine...`` etc. genauso
auflösen wie in ``"Party Planning.py"``, keine ``sys.path``-Hacks):

    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import accounts.discover_learning as discover_learning
import accounts.discover_storage as discover_storage
import accounts.discovery_storage as discovery_storage
import accounts.invitation_storage as invitation_storage
import accounts.notification_storage as notification_storage
import accounts.party_storage as party_storage
import accounts.profile_storage as profile_storage
import accounts.spotify_storage as spotify_storage
import accounts.user_storage as user_storage
import event_theme
import geo.storage as geo_storage
import music_engine.admin_settings as music_admin_settings
import organizers.storage as organizers_storage
import party_engine.response_storage as response_storage
import social.blocks as social_blocks
import social.follows as social_follows
import social.friend_requests as social_friend_requests
import social.friendships as social_friendships
from backend.app.core.config import settings, warn_if_insecure_defaults
from backend.app.routers import (
    admin_catalog_curation,
    admin_music,
    admin_organizers,
    admin_party_context,
    admin_party_settings,
    admin_recommendations,
    admin_responses,
    admin_shopping_list,
    admin_users,
    auth,
    catalog,
    discover,
    discovery_catalogs,
    discovery_preferences,
    follows,
    geo as geo_router,
    guest,
    invitations,
    me,
    notifications,
    organizers,
    parties,
    party_locations,
    profile,
    social,
    spotify_connect,
    translations,
)
from party_context import learning_storage
from party_context import storage as party_context_storage
from party_engine.catalog_curation import init_catalog_curation

app = FastAPI(title="Party Planning API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Auth läuft ausschließlich über einen `Authorization: Bearer`-Header
    # (kein Cookie-Auth irgendwo in dieser Codebase), daher wird
    # `allow_credentials` nicht gebraucht. Zusammen mit dem Default
    # `cors_origins=["*"]` wäre `allow_credentials=True` ohnehin
    # spezifikationswidrig (Browser lehnen den Wildcard-Origin bei
    # credentialed Requests ab) - Security-Hardening-Pass.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    me.router,
    notifications.router,
    parties.router,
    organizers.router,
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
    admin_users.router,
    admin_organizers.router,
    profile.router,
    discovery_preferences.router,
    discovery_catalogs.router,
    spotify_connect.router,
    discover.router,
    geo_router.router,
    party_locations.router,
    social.router,
    follows.router,
):
    app.include_router(router)

# Serviert hochgeladene Profilbilder statisch (lokale Disk, kein Cloud-Storage
# - siehe Phase-5-Plan, Teil D). Gemountet wird das ELTERN-Verzeichnis von
# ``settings.media_dir`` (nicht ``media_dir`` selbst), da die in der DB
# gespeicherten/an Flutter gelieferten Pfade mit dem Präfix
# ``profile_images/...`` gebildet werden (siehe `user_storage.update_profile_image`-
# Aufrufer in `routers/me.py`) - `/media/profile_images/{user_id}.jpg` muss
# also exakt auf ``media_dir / "{user_id}.jpg"`` auflösen. Verzeichnis wird
# bei Bedarf angelegt, da ``StaticFiles`` sonst beim App-Start crasht, wenn es
# noch nicht existiert (frisches Dev-Setup ohne bisherige Uploads).
settings.media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir.parent), name="media")


@app.on_event("startup")
def on_startup() -> None:
    """Idempotenter Init-Durchlauf - identisch zu den Modul-Level-Aufrufen in
    ``"Party Planning.py"``, sicher parallel zum Streamlit-Prozess gegen
    dieselbe ``responses.db`` aufrufbar."""
    warn_if_insecure_defaults(settings)

    db_path = settings.db_path
    user_storage.init_user_storage(db_path)
    party_storage.init_party_storage(db_path)
    organizers_storage.init_organizer_storage(db_path)
    invitation_storage.init_invitation_storage(db_path)
    notification_storage.init_notifications(db_path)
    event_theme.init_party_settings(db_path)
    music_admin_settings.init_music_admin_settings(db_path)
    party_context_storage.init_party_context_storage(db_path)
    learning_storage.init_learning_storage(db_path)
    profile_storage.init_profile_storage(db_path)
    social_blocks.init_block_storage(db_path)
    social_friendships.init_friendship_storage(db_path)
    social_friend_requests.init_friend_request_storage(db_path)
    social_follows.init_follow_storage(db_path)
    discovery_storage.init_discovery_storage(db_path)
    discover_storage.init_discover_storage(db_path)
    discover_learning.init_discover_learning_storage(db_path)
    spotify_storage.init_spotify_storage(db_path)
    init_catalog_curation(db_path)
    response_storage.init_db(db_path)
    geo_storage.init_geo_storage(db_path)

    # WAL-Modus reduziert "database is locked"-Risiko bei parallelem
    # Schreibzugriff von Streamlit- und FastAPI-Prozess (Plan Schritt 2) -
    # einmalig gesetzt, PRAGMA bleibt danach persistent in der DB-Datei.
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
