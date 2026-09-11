"""Gemeinsame FastAPI-Dependencies: DB-Pfad + gecachte Katalog-Loader.

``get_db_path`` ist als eigene Dependency geschnitten (statt Router direkt
``settings.db_path`` importieren zu lassen), damit API-Tests sie per
``app.dependency_overrides`` auf eine temporäre ``tmp_path``-DB umbiegen
können (Phase-1-Plan Schritt 7) - der Live-Dev-DB (``responses.db``) wird so
in Tests nie angefasst.

Katalog-/Occasion-Loader werden wie im Streamlit-Pendant
(``@st.cache_resource``) genau einmal pro Prozess geladen (``functools.lru_cache``,
das FastAPI-Äquivalent für einen langlebigen Prozess ohne Rerun-Modell)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.app.core.config import settings
from equipment_engine.catalog import load_catalog as load_equipment_catalog
from equipment_engine.domain import EquipmentCatalog
from geo.providers import GeoSearchProvider, get_default_geo_search_provider
from music_engine.catalog import load_music_catalog
from music_engine.domain import MusicCatalog, MusicOccasionProfile
from music_engine.occasions import load_all_music_occasions
from party_engine.catalog import load_catalog
from party_engine.domain import PartyCatalog
from party_engine.occasions import load_all_occasions
from party_engine.recommendation_domain import OccasionProfile


def get_db_path() -> Path:
    return settings.db_path


def get_media_dir() -> Path:
    return settings.media_dir


@lru_cache(maxsize=1)
def get_catalog() -> PartyCatalog:
    return load_catalog()


@lru_cache(maxsize=1)
def get_occasions() -> dict[str, OccasionProfile]:
    return load_all_occasions()


@lru_cache(maxsize=1)
def get_music_catalog() -> MusicCatalog:
    return load_music_catalog()


@lru_cache(maxsize=1)
def get_music_occasions() -> dict[str, MusicOccasionProfile]:
    return load_all_music_occasions()


@lru_cache(maxsize=1)
def get_equipment_catalog() -> EquipmentCatalog:
    return load_equipment_catalog()


@dataclass
class SpotifyOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    encryption_key: bytes


@lru_cache(maxsize=1)
def get_geo_search_provider() -> GeoSearchProvider:
    """Ein Prozess-weiter Provider (analog ``get_catalog``) - wichtig für
    ``NominatimGeoSearchProvider``, dessen Suggest->Retrieve-Cache sonst bei
    jedem Request neu und leer wäre."""
    return get_default_geo_search_provider(settings)


def get_spotify_oauth_config() -> SpotifyOAuthConfig:
    return SpotifyOAuthConfig(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        encryption_key=settings.spotify_token_encryption_key.encode(),
    )
