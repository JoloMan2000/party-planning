"""Statische Discovery-Kataloge (Onboarding-Spec, Phase 6) - stabile IDs für
Event-Interessen, Musik-Genres, Event-Größen, Event-Settings und Interest-
Tags, damit UI-Text NIE als Datenquelle hardcoded wird (siehe Onboarding-Spec:
"never hardcoded in UI").

Mirrort exakt das Muster aus ``event_theme.EVENT_TYPES``: einfache
Python-Konstanten (``dict[str, dict]``), kein JSON-Loader nötig - das ist der
richtige Grad an Komplexität für kleine, stabile Referenzdaten (im Gegensatz
zum schwergewichtigeren ``party_engine/catalog.py``-JSON-Loader für den
großen Getränke-/Essen-/Track-Katalog).

Bewusst KEIN ``ArtistCatalog`` hier (Phase 6) - Artist-Präferenzen sind
Freitext (``UserArtistPreference.artist_reference``/``display_name``), bis
Phase 7 Spotify-bestätigte Artist-Referenzen hinzufügt."""

from __future__ import annotations

EVENT_INTEREST_CATALOG: dict[str, dict] = {
    "concert": {"label_de": "Konzert", "label_en": "Concert", "emoji": "🎤"},
    "festival": {"label_de": "Festival", "label_en": "Festival", "emoji": "🎪"},
    "club_night": {"label_de": "Clubnacht", "label_en": "Club night", "emoji": "🪩"},
    "food_market": {"label_de": "Food-Markt", "label_en": "Food market", "emoji": "🍜"},
    "art_exhibition": {"label_de": "Kunstausstellung", "label_en": "Art exhibition", "emoji": "🖼️"},
    "sports_event": {"label_de": "Sport-Event", "label_en": "Sports event", "emoji": "🏟️"},
    "outdoor_activity": {"label_de": "Outdoor-Aktivität", "label_en": "Outdoor activity", "emoji": "🥾"},
    "flea_market": {"label_de": "Flohmarkt", "label_en": "Flea market", "emoji": "🧺"},
    "comedy_show": {"label_de": "Comedy-Show", "label_en": "Comedy show", "emoji": "🎭"},
    "networking": {"label_de": "Networking", "label_en": "Networking", "emoji": "🤝"},
    "wellness": {"label_de": "Wellness", "label_en": "Wellness", "emoji": "🧘"},
    "workshop": {"label_de": "Workshop", "label_en": "Workshop", "emoji": "🛠️"},
}

MUSIC_GENRE_CATALOG: dict[str, dict] = {
    "pop": {"label_de": "Pop", "label_en": "Pop"},
    "rock": {"label_de": "Rock", "label_en": "Rock"},
    "indie": {"label_de": "Indie", "label_en": "Indie"},
    "hip_hop": {"label_de": "Hip-Hop", "label_en": "Hip-Hop"},
    "rnb": {"label_de": "R&B", "label_en": "R&B"},
    "techno": {"label_de": "Techno", "label_en": "Techno"},
    "tech_house": {"label_de": "Tech House", "label_en": "Tech House"},
    "house": {"label_de": "House", "label_en": "House"},
    "edm": {"label_de": "EDM", "label_en": "EDM"},
    "drum_and_bass": {"label_de": "Drum & Bass", "label_en": "Drum & Bass"},
    "trance": {"label_de": "Trance", "label_en": "Trance"},
    "reggaeton": {"label_de": "Reggaeton", "label_en": "Reggaeton"},
    "afrobeats": {"label_de": "Afrobeats", "label_en": "Afrobeats"},
    "latin": {"label_de": "Latin", "label_en": "Latin"},
    "jazz": {"label_de": "Jazz", "label_en": "Jazz"},
    "soul_funk": {"label_de": "Soul & Funk", "label_en": "Soul & Funk"},
    "metal": {"label_de": "Metal", "label_en": "Metal"},
    "punk": {"label_de": "Punk", "label_en": "Punk"},
    "classical": {"label_de": "Klassik", "label_en": "Classical"},
    "folk": {"label_de": "Folk", "label_en": "Folk"},
    "country": {"label_de": "Country", "label_en": "Country"},
    "reggae": {"label_de": "Reggae", "label_en": "Reggae"},
    "schlager": {"label_de": "Schlager", "label_en": "Schlager"},
    "disco": {"label_de": "Disco", "label_en": "Disco"},
    "ambient": {"label_de": "Ambient", "label_en": "Ambient"},
}

EVENT_SIZE_CATALOG: dict[str, dict] = {
    "intimate": {"label_de": "Intim (< 20)", "label_en": "Intimate (< 20)"},
    "medium": {"label_de": "Mittel (20-100)", "label_en": "Medium (20-100)"},
    "large": {"label_de": "Groß (100-1000)", "label_en": "Large (100-1000)"},
    "festival": {"label_de": "Festival (1000+)", "label_en": "Festival (1000+)"},
}

EVENT_SETTING_CATALOG: dict[str, dict] = {
    "indoor": {"label_de": "Drinnen", "label_en": "Indoor"},
    "outdoor": {"label_de": "Draußen", "label_en": "Outdoor"},
    "mixed": {"label_de": "Gemischt", "label_en": "Mixed"},
}

INTEREST_TAG_CATALOG: dict[str, dict] = {
    "family_friendly": {"label_de": "Familienfreundlich", "label_en": "Family-friendly"},
    "late_night": {"label_de": "Late Night", "label_en": "Late night"},
    "free_entry": {"label_de": "Freier Eintritt", "label_en": "Free entry"},
    "lgbtq_friendly": {"label_de": "LGBTQ+-freundlich", "label_en": "LGBTQ+-friendly"},
    "accessible": {"label_de": "Barrierefrei", "label_en": "Accessible"},
    "outdoor_seating": {"label_de": "Außenbereich", "label_en": "Outdoor seating"},
}


def as_list(catalog: dict[str, dict]) -> list[dict]:
    """Wandelt einen ``dict[str, dict]``-Katalog in eine Liste von
    ``{"id": ..., **fields}``-Dicts für die REST-Antwort um."""
    return [{"id": item_id, **fields} for item_id, fields in catalog.items()]
