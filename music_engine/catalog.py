"""
MusicCatalog-Loader
=====================

Lädt den statischen Track-Seed-Katalog aus ``music_catalog/tracks.json`` (siehe
``/tmp``-Build-Skript, das diese Datei einmalig erzeugt hat - analog zu
``build_catalog.py`` für den Haupt-PartyCatalog) und baut daraus ein
vollständig typisiertes ``MusicCatalog``-Objekt inkl. vorberechneter
Resolver-Indizes (Spec §93).

Framework-agnostisch: Dieses Modul importiert Streamlit NICHT. Caching erfolgt
über ``functools.lru_cache`` (analog zu party_engine/catalog.py), damit die
JSON-Datei nicht bei jedem Streamlit-Rerun neu geparst wird.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from music_engine.domain import MusicCatalog, MusicTrack

# Default: <repo_root>/music_catalog  (dieses Modul liegt in <repo_root>/music_engine/)
_DEFAULT_CATALOG_DIR = Path(__file__).resolve().parent.parent / "music_catalog"

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")

# Häufige Zusätze, die für die Normalisierung/Dedup ignoriert werden sollen
# (Spec §96 Testfall "Mr Brightside" / "Mr. Brightside" / "The Killers - Mr
# Brightside" müssen auf denselben Track auflösen).
_NOISE_WORDS = {
    "feat", "featuring", "ft", "remaster", "remastered", "remix", "edit",
    "radio", "version", "live", "acoustic", "original", "single",
}


def normalize_text_key(text: str) -> str:
    """Normalisiert einen beliebigen Text für Vergleichs-/Index-Zwecke:
    Kleinbuchstaben, Akzente entfernt, Satzzeichen entfernt, Whitespace
    vereinheitlicht (Spec §78/§96 Duplikat-Erkennung)."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = _NON_ALNUM_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def normalize_artist_key(artist: str) -> str:
    return normalize_text_key(artist)


def normalize_title_key(title: str) -> str:
    """Normalisierter Titel-Key ohne Artist-Anker und ohne Noise-Wörter
    (feat./remaster/...) - Basis für Freitext-Resolution ohne Artist-Angabe
    (Spec §6 Beispiel "Mr Brightside" ohne "The Killers")."""
    title_key = normalize_text_key(title)
    title_words = [w for w in title_key.split(" ") if w and w not in _NOISE_WORDS]
    return " ".join(title_words)


def normalize_song_key(artist: str, title: str) -> str:
    """Normalisierter "artist - title"-Key ohne Noise-Wörter (feat./remaster/...),
    die Musik-Resolver-Basis für Duplikat-Erkennung (Spec §78/§96)."""
    artist_key = normalize_artist_key(artist)
    title_key = normalize_title_key(title)
    return f"{artist_key}|{title_key}"


def derive_canonical_song_id(artist: str, title: str) -> str:
    """Fällt auf den normalisierten Song-Key zurück, falls ein Track keine
    explizite ``canonical_song_id`` mitbringt (Spec §79)."""
    return normalize_song_key(artist, title)


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_track(row: dict) -> MusicTrack:
    row = dict(row)
    row["genres"] = set(row.get("genres", []))
    row["eras"] = set(row.get("eras", []))
    row["moods"] = set(row.get("moods", []))
    row["tags"] = set(row.get("tags", []))
    row.setdefault("provider_ids", {})
    track = MusicTrack(**row)
    if not track.canonical_song_id:
        track.canonical_song_id = derive_canonical_song_id(track.artist, track.title)
    return track


def _build_indices(tracks: dict[str, MusicTrack]) -> MusicCatalog:
    catalog = MusicCatalog(tracks=tracks)
    for track in tracks.values():
        song_key = normalize_song_key(track.artist, track.title)
        # Erster Treffer gewinnt (Seed-Reihenfolge = Sortierung nach id) -
        # exakte Kollisionen sind bei realen Titeln extrem selten und sollen
        # den Katalog nicht crashen lassen.
        catalog.normalized_song_index.setdefault(song_key, track.id)

        title_key = normalize_title_key(track.title)
        catalog.normalized_title_index.setdefault(title_key, []).append(track.id)

        artist_key = normalize_artist_key(track.artist)
        catalog.normalized_artist_index.setdefault(artist_key, []).append(track.id)

        for genre in track.genres:
            catalog.genre_index.setdefault(genre, []).append(track.id)
        for era in track.eras:
            catalog.era_index.setdefault(era, []).append(track.id)
        for tag in track.tags:
            catalog.tag_index.setdefault(tag, []).append(track.id)

        catalog.canonical_song_index.setdefault(track.canonical_song_id, []).append(track.id)

    return catalog


@lru_cache(maxsize=4)
def _load_music_catalog_cached(catalog_dir_str: str) -> MusicCatalog:
    catalog_dir = Path(catalog_dir_str)
    tracks_raw = _read_json(catalog_dir / "tracks.json")
    tracks = {row["id"]: _build_track(row) for row in tracks_raw}
    return _build_indices(tracks)


def load_music_catalog(catalog_dir: Path | str | None = None) -> MusicCatalog:
    """Lädt (bzw. liefert aus dem Cache) den vollständigen ``MusicCatalog``.

    Wiederholte Aufrufe mit demselben (aufgelösten) Pfad geben dieselbe
    ``MusicCatalog``-Instanz zurück, ohne ``tracks.json`` erneut zu parsen
    (Spec §93: "Statische Daten nicht bei jedem Streamlit-Rerun neu laden.").
    """
    resolved = Path(catalog_dir) if catalog_dir else _DEFAULT_CATALOG_DIR
    return _load_music_catalog_cached(str(resolved.resolve()))


def clear_music_catalog_cache() -> None:
    """Nur für Tests: erzwingt beim nächsten ``load_music_catalog()`` ein
    Neuladen."""
    _load_music_catalog_cached.cache_clear()


if __name__ == "__main__":
    _catalog = load_music_catalog()
    print(f"Loaded {len(_catalog.tracks)} tracks.")
    assert len(_catalog.tracks) >= 300, f"expected >= 300 tracks, got {len(_catalog.tracks)}"

    # Spec §96 Duplikat-Test (Normalisierung, nicht Dedup selbst - siehe
    # resolver.py): alle drei Schreibweisen müssen auf denselben Song-Key
    # normalisieren, sobald ein Artist-Präfix entfernt wird.
    k1 = normalize_song_key("The Killers", "Mr Brightside")
    k2 = normalize_song_key("The Killers", "Mr. Brightside")
    assert k1 == k2, (k1, k2)
    print(f"normalize_song_key OK -> {k1!r}")

    print(f"genres indexed: {len(_catalog.genre_index)}")
    print(f"eras indexed: {len(_catalog.era_index)}")
    print(f"tags indexed: {len(_catalog.tag_index)}")
    print(f"unique artists: {len(_catalog.normalized_artist_index)}")

    print("music_engine/catalog.py sanity check OK.")
