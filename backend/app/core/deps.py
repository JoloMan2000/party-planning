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

from functools import lru_cache
from pathlib import Path

from backend.app.core.config import settings
from music_engine.catalog import load_music_catalog
from music_engine.domain import MusicCatalog, MusicOccasionProfile
from music_engine.occasions import load_all_music_occasions
from party_engine.catalog import load_catalog
from party_engine.domain import PartyCatalog
from party_engine.occasions import load_all_occasions
from party_engine.recommendation_domain import OccasionProfile


def get_db_path() -> Path:
    return settings.db_path


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
