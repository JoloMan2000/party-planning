"""
Musik-Tag-/Genre-/Era-Taxonomie-Registry (Spec §21-23).
==========================================================

Analog zu party_engine/tags.py: das erlaubte Vokabular für
MusicTrack.genres/eras/moods/tags und MusicOccasionProfile.preferred_*/
discouraged_*. Enthält bewusst KEINE Zuordnung "welcher Track hat welchen
Tag" (das lebt im music_catalog/*.json Seed) und KEINE Occasion-Gewichte
(das lebt in music_catalog/occasion_music_profiles.json).

Architektur-Grundsatz (Spec §22 Schlusssatz / §118): "Architektur so bauen,
dass weitere Genres ergänzt werden können" - diese Sets sind das *aktuell*
unterstützte Vokabular, kein hartcodiertes Limit. Ein Track mit einem Genre
außerhalb dieser Liste bricht nichts (siehe catalog.py: unbekannte Genres
werden beim Laden nicht gefiltert, nur bei der Validierung/Tests markiert).
"""

from __future__ import annotations

# --- Funktions-Tags (Spec §21 "FUNCTION") --------------------------------------

FUNCTION_TAGS: frozenset[str] = frozenset({
    "background", "conversation_friendly", "warmup", "build_up", "dancefloor",
    "peak", "singalong", "late_night", "closing",
})

# --- Mood-Tags (Spec §21 "MOOD") -----------------------------------------------

MOOD_TAGS: frozenset[str] = frozenset({
    "happy", "uplifting", "chill", "relaxed", "energetic", "euphoric",
    "nostalgic", "romantic", "dark", "melancholic", "playful", "sexy", "cool",
    "aggressive", "emotional", "warm",
})

# --- Party-Charakter-Tags (Spec §21 "PARTY CHARACTER") -------------------------

PARTY_CHARACTER_TAGS: frozenset[str] = frozenset({
    "party_classic", "crowd_pleaser", "mainstream", "niche", "trendy",
    "timeless", "festival", "club", "bar", "wedding", "summer", "winter",
    "daytime", "nightlife", "social", "celebratory", "anthem",
})

# --- Musik-Charakter-Tags (Spec §21 "MUSIC CHARACTER") -------------------------

MUSIC_CHARACTER_TAGS: frozenset[str] = frozenset({
    "danceable", "high_energy", "medium_energy", "low_energy", "singalong",
    "anthem", "groovy", "funky", "electronic", "acoustic", "bass_heavy",
    "guitar_driven", "vocal_driven", "instrumental", "premium", "throwback",
})

ALL_MUSIC_TAGS: frozenset[str] = (
    FUNCTION_TAGS | MOOD_TAGS | PARTY_CHARACTER_TAGS | MUSIC_CHARACTER_TAGS
)

# --- Genre-Taxonomie (Spec §22) -------------------------------------------------

GENRES: frozenset[str] = frozenset({
    "pop", "dance_pop", "electropop",
    "rock", "classic_rock", "indie_rock", "alternative",
    "hip_hop", "rap", "rnb",
    "house", "deep_house", "progressive_house", "edm", "techno", "trance",
    "drum_and_bass",
    "disco", "nu_disco", "funk", "soul",
    "reggae", "dancehall",
    "latin", "reggaeton",
    "schlager", "german_pop", "german_rap",
    "country",
    "jazz", "lounge",
    "afrobeats",
    "throwback_party",
    "acoustic",
    "other",
})

# --- Era-Taxonomie (Spec §23) ---------------------------------------------------

ERAS: frozenset[str] = frozenset({
    "60s", "70s", "80s", "90s", "2000s", "2010s", "2020s", "current",
})

# Reihenfolge für UI-/Chart-Darstellung (Spec §74: "Ankommen/Aufbau/Peak/..."),
# hier für die Era-Mix-Anzeige (Spec §71 "Era Mix").
ERA_ORDER: list[str] = ["60s", "70s", "80s", "90s", "2000s", "2010s", "2020s", "current"]

# --- Sprachen (leichtgewichtig, kein hartes Enum - nur häufige Werte) ----------

COMMON_LANGUAGES: frozenset[str] = frozenset({
    "en", "de", "es", "fr", "it", "pt", "instrumental",
})
