"""Location-Stammdaten: 20 Location-Typen mit UI-Labels, Smart Defaults und
``LocationProfile`` (Spec §3/§4/§50-§60)."""

from __future__ import annotations

from functools import lru_cache

from party_context.domain import LocationProfile

LOCATION_TYPES: list[str] = [
    "private_home",
    "apartment",
    "garden",
    "terrace",
    "rooftop",
    "pool",
    "beach",
    "park",
    "forest",
    "event_hall",
    "club",
    "bar",
    "restaurant",
    "barn",
    "festival_ground",
    "campsite",
    "office",
    "community_hall",
    "holiday_home",
    "other",
]

# (label_de, label_en) je Location-Typ (§3).
LOCATION_LABELS: dict[str, tuple[str, str]] = {
    "private_home": ("Privathaus", "Private home"),
    "apartment": ("Wohnung", "Apartment"),
    "garden": ("Garten", "Garden"),
    "terrace": ("Terrasse", "Terrace"),
    "rooftop": ("Dachterrasse", "Rooftop terrace"),
    "pool": ("Pool", "Pool"),
    "beach": ("Strand", "Beach"),
    "park": ("Park", "Park"),
    "forest": ("Wald", "Forest"),
    "event_hall": ("Eventhalle", "Event hall"),
    "club": ("Club", "Club"),
    "bar": ("Bar", "Bar"),
    "restaurant": ("Restaurant", "Restaurant"),
    "barn": ("Scheune", "Barn"),
    "festival_ground": ("Festival-/Outdoorfläche", "Festival / outdoor ground"),
    "campsite": ("Campingplatz", "Campsite"),
    "office": ("Büro", "Office"),
    "community_hall": ("Gemeindesaal", "Community hall"),
    "holiday_home": ("Ferienhaus", "Holiday home"),
    "other": ("Sonstiges", "Other"),
}

# Plausible Infrastruktur-Defaults je Location (§50) - Admin kann jederzeit
# überschreiben (siehe party_context/domain.PartyContextOverride).
LOCATION_SMART_DEFAULTS: dict[str, dict[str, bool]] = {
    "private_home": {"has_power": True, "has_running_water": True, "has_kitchen": True, "has_fridge": True},
    "apartment": {"has_power": True, "has_running_water": True, "has_kitchen": True, "has_fridge": True},
    "garden": {"has_power": True, "has_running_water": True},
    "terrace": {"has_power": True, "has_running_water": True},
    "rooftop": {"has_power": True},
    "pool": {"has_power": False, "has_running_water": False},
    "beach": {"has_power": False, "has_running_water": False, "has_kitchen": False, "has_fridge": False},
    "park": {"has_power": False, "has_running_water": False, "has_kitchen": False, "has_fridge": False},
    "forest": {"has_power": False, "has_running_water": False, "has_kitchen": False, "has_fridge": False},
    "event_hall": {"has_power": True, "has_running_water": True, "has_kitchen": True},
    "club": {"has_power": True, "has_running_water": True, "has_bar": True},
    "bar": {"has_power": True, "has_running_water": True, "has_bar": True, "has_fridge": True},
    "restaurant": {"has_power": True, "has_running_water": True, "has_kitchen": True, "has_fridge": True},
    "barn": {"has_power": False, "has_running_water": False},
    "festival_ground": {"has_power": False, "has_running_water": False, "has_kitchen": False, "has_fridge": False},
    "campsite": {"has_power": False, "has_running_water": False, "has_kitchen": False, "has_fridge": False},
    "office": {"has_power": True, "has_running_water": True, "has_kitchen": True, "has_fridge": True},
    "community_hall": {"has_power": True, "has_running_water": True, "has_kitchen": True},
    "holiday_home": {"has_power": True, "has_running_water": True, "has_kitchen": True, "has_fridge": True},
    "other": {},
}

# Default indoor/outdoor je Location-Typ (§4) - Admin kann jederzeit auf
# "mixed" umstellen (z.B. "Restaurant mit Terrasse").
LOCATION_DEFAULT_INDOOR_OUTDOOR: dict[str, str] = {
    "private_home": "indoor",
    "apartment": "indoor",
    "garden": "outdoor",
    "terrace": "outdoor",
    "rooftop": "outdoor",
    "pool": "outdoor",
    "beach": "outdoor",
    "park": "outdoor",
    "forest": "outdoor",
    "event_hall": "indoor",
    "club": "indoor",
    "bar": "indoor",
    "restaurant": "indoor",
    "barn": "indoor",
    "festival_ground": "outdoor",
    "campsite": "outdoor",
    "office": "indoor",
    "community_hall": "indoor",
    "holiday_home": "indoor",
    "other": "outdoor",
}


def _profile(
    location_id: str,
    *,
    preferred_tags: dict[str, float] | None = None,
    discouraged_tags: dict[str, float] | None = None,
    music: dict[str, float] | None = None,
    food: dict[str, float] | None = None,
    beverage: dict[str, float] | None = None,
) -> LocationProfile:
    label_de, label_en = LOCATION_LABELS[location_id]
    return LocationProfile(
        id=location_id,
        label_de=label_de,
        label_en=label_en,
        default_indoor_outdoor=LOCATION_DEFAULT_INDOOR_OUTDOOR.get(location_id, "outdoor"),
        default_capabilities=LOCATION_SMART_DEFAULTS.get(location_id, {}),
        preferred_tags=preferred_tags or {},
        discouraged_tags=discouraged_tags or {},
        music_characteristics=music or {},
        food_characteristics=food or {},
        beverage_characteristics=beverage or {},
    )


# Explizit ausgearbeitete Profile für die im Spec detailliert beschriebenen
# Locations (§52-§60). Alle übrigen Location-Typen erhalten über
# ``get_location_profile()`` ein plausibles generisches Fallback-Profil -
# spiegelt das etablierte "kuratierte Teilmenge + Fallback"-Muster des Projekts.
LOCATION_PROFILES: dict[str, LocationProfile] = {
    "garden": _profile(
        "garden",
        preferred_tags={"garden": 1.0, "outdoor": 1.0, "social": 0.8, "casual": 0.8, "grill_possible": 1.0, "buffet_possible": 0.7, "summer_friendly": 0.9},
        music={"conversation_friendly": 0.8, "pop": 0.7, "indie": 0.6, "funk": 0.6, "nu_disco": 0.6},
        food={"grill": 1.0, "salad": 0.8, "bread": 0.6, "fingerfood": 0.6},
        beverage={"refreshing": 0.9, "beer": 0.7, "spritz": 0.9, "schorle": 0.8, "hydration": 0.9},
    ),
    "apartment": _profile(
        "apartment",
        preferred_tags={"indoor": 1.0, "small_space": 0.8, "neighbors_possible": 0.6},
        discouraged_tags={"large_grill_setup": 0.8, "smoky_preparation": 0.6},
        music={"bass_penalty": 0.3, "late_night_energy_penalty": 0.3},
        food={"pizza": 0.8, "snacks": 0.8, "fingerfood": 0.8, "low_mess": 0.9},
        beverage={"simple_service": 0.8, "complex_bar": -0.5},
    ),
    "rooftop": _profile(
        "rooftop",
        preferred_tags={"outdoor": 0.9, "urban": 0.8, "premium": 0.7, "social": 0.8, "sunset": 0.7},
        music={"nu_disco": 0.8, "house": 0.7, "funk": 0.6, "pop": 0.6},
        food={"fingerfood": 0.8, "light_food": 0.8},
        beverage={"spritz": 0.9, "wine": 0.7, "cocktails": 0.8},
    ),
    "pool": _profile(
        "pool",
        preferred_tags={"outdoor": 1.0, "poolside": 1.0, "summer": 0.9},
        music={"danceable": 0.7, "summer": 0.9, "house": 0.6, "pop": 0.6, "latin": 0.5},
        food={"handheld": 0.7, "fruit": 0.8, "light_food": 0.8},
        beverage={"hydration": 1.0, "summer_drinks": 0.9},
    ),
    "event_hall": _profile(
        "event_hall",
        preferred_tags={"large_group": 0.8, "indoor": 0.8, "buffet_possible": 0.9},
        music={"crowd_pleaser": 0.8},
        food={"buffet": 0.9, "batchable": 0.8},
        beverage={"easy_service": 0.8, "large_batch": 0.8},
    ),
    "restaurant": _profile(
        "restaurant",
        preferred_tags={"indoor": 0.9, "seated": 0.8, "table_service": 0.8},
        discouraged_tags={"high_energy": 0.5, "aggressive": 0.6, "bass_heavy": 0.6},
        music={"conversation_friendly": 0.9, "background": 0.9, "soul": 0.5, "jazz": 0.5, "lounge": 0.5, "funk": 0.4, "soft_pop": 0.4},
        food={},
        beverage={},
    ),
    "club": _profile(
        "club",
        preferred_tags={"indoor": 0.7, "nightlife": 0.9, "dancefloor": 1.0},
        music={"dancefloor": 1.0, "electronic": 0.9, "high_energy": 0.9, "bass_heavy": 0.9, "club": 0.9, "nightlife": 0.9},
        food={},
        beverage={},
    ),
    "park": _profile(
        "park",
        preferred_tags={"outdoor": 0.9, "portable": 0.9, "casual": 0.7},
        discouraged_tags={"fresh_to_order": 0.6, "complex_hot_food": 0.6},
        music={"portable_speaker_context": 0.6, "conversation_friendly": 0.6},
        food={"portable": 0.9, "handheld": 0.9, "low_mess": 0.8, "cold_food": 0.8, "sandwich": 0.7, "wrap": 0.7, "fruit": 0.7},
        beverage={"portable": 0.9, "hydration": 0.9, "easy_service": 0.8},
    ),
    "festival_ground": _profile(
        "festival_ground",
        preferred_tags={"outdoor": 0.9, "large_group": 0.8, "festival": 0.9},
        music={"anthem": 0.9, "high_energy": 0.9, "festival": 0.9, "crowd_pleaser": 0.8, "large_group": 0.7},
        food={"handheld": 0.8, "fast_service": 0.8, "large_group": 0.7},
        beverage={"hydration": 0.9, "easy_service": 0.9, "large_group": 0.8},
    ),
}


@lru_cache(maxsize=None)
def get_location_profile(location_type: str) -> LocationProfile:
    """Liefert das ``LocationProfile`` für einen Location-Typ. Fällt für nicht
    explizit kuratierte Typen (z.B. ``barn``/``campsite``/``office``/``other``)
    auf ein generisches, aber weiterhin location-typisches Profil zurück -
    niemals eine Exception (mirrors ``music_engine`` Fallback-Konvention)."""
    if location_type in LOCATION_PROFILES:
        return LOCATION_PROFILES[location_type]
    if location_type in LOCATION_TYPES:
        return _profile(location_type)
    return _profile("other") if "other" in LOCATION_LABELS else _profile("other")


def smart_defaults_for_location(location_type: str) -> dict[str, bool]:
    """Plausible Infrastruktur-Defaults für die Admin-Setup-UX (§50)."""
    return dict(LOCATION_SMART_DEFAULTS.get(location_type, {}))


def default_indoor_outdoor_for_location(location_type: str) -> str:
    return LOCATION_DEFAULT_INDOOR_OUTDOOR.get(location_type, "outdoor")


if __name__ == "__main__":
    assert len(LOCATION_TYPES) == 20
    assert set(LOCATION_LABELS.keys()) == set(LOCATION_TYPES)
    assert set(LOCATION_DEFAULT_INDOOR_OUTDOOR.keys()) == set(LOCATION_TYPES)

    garden = get_location_profile("garden")
    assert garden.preferred_tags["grill_possible"] == 1.0
    assert garden.beverage_characteristics["spritz"] == 0.9

    apartment = get_location_profile("apartment")
    assert apartment.discouraged_tags["large_grill_setup"] == 0.8

    unknown_but_valid = get_location_profile("barn")
    assert unknown_but_valid.id == "barn"
    assert unknown_but_valid.label_de == "Scheune"

    fully_unknown = get_location_profile("totally_made_up_location")
    assert fully_unknown.id == "other"

    assert smart_defaults_for_location("private_home")["has_power"] is True
    assert smart_defaults_for_location("park") == {"has_power": False, "has_running_water": False, "has_kitchen": False, "has_fridge": False}
    assert default_indoor_outdoor_for_location("restaurant") == "indoor"
    print("party_context/locations.py sanity check OK.")
