"""
Zentrale Konfiguration der Party Context Intelligence Layer (Spec §92/§93).
==============================================================================

Alle Thresholds/Multiplikatoren/Gewichte liegen ausschließlich hier, nicht
über den Code verstreut. Werte sind initiale heuristische Planungsparameter
(§93), keine wissenschaftlich exakten Verbrauchswerte - versioniert über
``PARTY_CONTEXT_MODEL_VERSION`` (§91).
"""

from __future__ import annotations

PARTY_CONTEXT_MODEL_VERSION = "1.0"


# --- §5: Saison aus Monat (nördliche/südliche Hemisphäre) ---------------------------

SEASON_BY_MONTH_NORTHERN = {
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
    12: "winter", 1: "winter", 2: "winter",
}

# Südliche Hemisphäre: Jahreszeiten um 6 Monate verschoben.
SEASON_BY_MONTH_SOUTHERN = {
    3: "autumn", 4: "autumn", 5: "autumn",
    6: "winter", 7: "winter", 8: "winter",
    9: "spring", 10: "spring", 11: "spring",
    12: "summer", 1: "summer", 2: "summer",
}


# --- §6/§7: Daypart-Segmente (Minuten seit Mitternacht, halboffen [start, end)) -----
# late_night ist am Anfang und Ende des Tages gesplittet (Mitternachts-Wraparound).

DAYPART_SEGMENTS_MIN: list[tuple[int, int, str]] = [
    (0, 360, "late_night"),      # 00:00-06:00
    (360, 660, "morning"),       # 06:00-11:00
    (660, 780, "brunch"),        # 11:00-13:00
    (780, 1020, "daytime"),      # 13:00-17:00
    (1020, 1140, "afternoon"),   # 17:00-19:00
    (1140, 1380, "evening"),     # 19:00-23:00
    (1380, 1440, "late_night"),  # 23:00-24:00
]

DAYPART_ORDER = ["morning", "brunch", "daytime", "afternoon", "evening", "late_night"]


# --- §46: Temperaturklassen -----------------------------------------------------------

TEMPERATURE_CLASS_THRESHOLDS: list[tuple[float, str]] = [
    (8.0, "cold"),
    (15.0, "cool"),
    (21.0, "mild"),
    (28.0, "warm"),
    # >= 28.0 -> "hot"
]
TEMPERATURE_CLASS_HOT = "hot"

# Fallback-Temperaturklasse je Saison, falls keine Wetterdaten vorhanden sind (§87).
SEASON_FALLBACK_TEMPERATURE_CLASS = {
    "spring": "mild",
    "summer": "warm",
    "autumn": "cool",
    "winter": "cold",
}

RAIN_PROBABILITY_HIGH_THRESHOLD = 0.5
RAIN_WARNING_TEXT = "⚠ Hohe Regenwahrscheinlichkeit – Outdoor-Setup bzw. Überdachung prüfen."

# §28: Food-Safety-Operational-Penalty, niemals als absolute Garantie kommuniziert.
FOOD_SPOILAGE_PENALTY_HIGH = 0.30
FOOD_SPOILAGE_PENALTY_LOW = 0.10
FOOD_SPOILAGE_WARNING_TEXT = "⚠ Kühlpflichtiges Produkt – geeignete Kühlung für diese Location einplanen."


# --- §39: Gästezahl-Klassen -----------------------------------------------------------

GROUP_SIZE_THRESHOLDS: list[tuple[int, str]] = [
    (8, "small_group"),
    (25, "medium_group"),
    (60, "large_group"),
    # > 60 -> "very_large_group"
]
GROUP_SIZE_VERY_LARGE = "very_large_group"


# --- §20/§21/§23/§64: Getränke-Multiplikatoren (Basiswerte + Caps) ------------------

BEVERAGE_MULTIPLIER_CAPS = {
    "water_multiplier": (0.9, 1.5),
    "non_alcoholic_multiplier": (0.9, 1.35),
    "ice_multiplier": (0.7, 1.8),
    "hot_drink_multiplier": (0.7, 1.6),
    "cold_refreshing_drink_multiplier": (0.8, 1.4),
    "cocktail_complexity_penalty": (0.0, 0.35),
}

# Additive Deltas (nicht multiplikativ kombiniert, siehe apply_capped_modifier()).
SEASON_BEVERAGE_DELTAS = {
    "summer": {"water_multiplier": 0.15, "non_alcoholic_multiplier": 0.05, "ice_multiplier": 0.20},
    "spring": {"water_multiplier": 0.05, "ice_multiplier": 0.05},
    "autumn": {"hot_drink_multiplier": 0.10},
    "winter": {"hot_drink_multiplier": 0.25},
}

TEMPERATURE_BEVERAGE_DELTAS = {
    "hot": {"water_multiplier": 0.25, "non_alcoholic_multiplier": 0.10, "ice_multiplier": 0.35, "cold_refreshing_drink_multiplier": 0.20},
    "warm": {"water_multiplier": 0.15, "non_alcoholic_multiplier": 0.05, "ice_multiplier": 0.20, "cold_refreshing_drink_multiplier": 0.10},
    "mild": {},
    "cool": {"hot_drink_multiplier": 0.15},
    "cold": {"hot_drink_multiplier": 0.30},
}

OUTDOOR_BEVERAGE_DELTAS = {"ice_multiplier": 0.10, "water_multiplier": 0.05}

NO_BAR_COCKTAIL_COMPLEXITY_PENALTY = 0.25
LARGE_GROUP_COCKTAIL_COMPLEXITY_PENALTY = 0.15


# --- §25/§26/§27: Food-Modifier-Deltas -------------------------------------------------

BEVERAGE_MODIFIER_FIELD_BOUNDS = (0.5, 1.6)
FOOD_MODIFIER_FIELD_BOUNDS = (0.5, 1.6)
MUSIC_MODIFIER_FIELD_BOUNDS = (-1.0, 1.0)

SEASON_FOOD_DELTAS = {
    "summer": {"fresh_food_preference": 0.25, "salad_preference": 0.30, "grill_preference": 0.30, "fingerfood_preference": 0.15, "hot_food_preference": -0.15, "comfort_food_preference": -0.10},
    "spring": {"fresh_food_preference": 0.15, "salad_preference": 0.15, "grill_preference": 0.10},
    "autumn": {"comfort_food_preference": 0.15, "hot_food_preference": 0.15},
    "winter": {"comfort_food_preference": 0.35, "hot_food_preference": 0.35, "dessert_preference": 0.15, "salad_preference": -0.15, "fresh_food_preference": -0.10},
}

TEMPERATURE_FOOD_DELTAS = {
    "hot": {"fresh_food_preference": 0.20, "salad_preference": 0.20, "hot_food_preference": -0.20, "comfort_food_preference": -0.15},
    "warm": {"fresh_food_preference": 0.10, "salad_preference": 0.10, "hot_food_preference": -0.10},
    "mild": {},
    "cool": {"hot_food_preference": 0.10, "comfort_food_preference": 0.10},
    "cold": {"hot_food_preference": 0.25, "comfort_food_preference": 0.25},
}


# --- §31-§37: Musik-Modifier-Deltas -----------------------------------------------------

NEIGHBORS_SENSITIVE_MUSIC_DELTAS = {"bass_penalty": 0.35, "late_night_energy_penalty": 0.35, "energy_modifier": -0.10}
VOLUME_LIMIT_MUSIC_DELTAS = {"bass_penalty": 0.20, "late_night_energy_penalty": 0.15}

# Location-spezifische Musik-Modifier-Deltas (§31-§36) für die explizit im Spec
# ausgearbeiteten Locations. Nicht gelistete Locations erhalten keine Deltas
# (neutral) - Season-/Daypart-/Neighbors-Deltas wirken weiterhin.
LOCATION_MUSIC_MODIFIER_DELTAS: dict[str, dict[str, float]] = {
    "garden": {"conversation_modifier": 0.30, "danceability_modifier": 0.10, "energy_modifier": 0.10},
    "apartment": {"bass_penalty": 0.20, "late_night_energy_penalty": 0.15, "conversation_modifier": 0.10},
    "rooftop": {"energy_modifier": 0.15, "danceability_modifier": 0.20, "conversation_modifier": 0.15},
    "pool": {"danceability_modifier": 0.25, "energy_modifier": 0.15, "outdoor_modifier": 0.20},
    "event_hall": {"energy_modifier": 0.10, "danceability_modifier": 0.15},
    "restaurant": {"conversation_modifier": 0.40, "energy_modifier": -0.30, "danceability_modifier": -0.30, "bass_penalty": 0.30},
    "club": {"energy_modifier": 0.40, "danceability_modifier": 0.40, "conversation_modifier": -0.30},
    "park": {"conversation_modifier": 0.20, "outdoor_modifier": 0.10},
    "festival_ground": {"energy_modifier": 0.35, "danceability_modifier": 0.20, "outdoor_modifier": 0.30},
}


# --- §40: Gruppengröße Operational Fit -------------------------------------------------

LARGE_GROUP_OPERATIONAL_TAGS_BOOST = {"batchable": 0.20, "buffet_friendly": 0.20, "easy_service": 0.20, "large_group_friendly": 0.25}
LARGE_GROUP_OPERATIONAL_TAGS_PENALTY = {"fresh_to_order": -0.20, "high_service_complexity": -0.20, "individual_customization": -0.15}


# --- §41: Recommendation-Kombinationsformel (konfigurierbar, keine harte Wahrheit) ---

RECOMMENDATION_SCORE_WEIGHTS = {
    "occasion_fit": 0.25,
    "season_fit": 0.15,
    "location_fit": 0.15,
    "daypart_fit": 0.10,
    "weather_fit": 0.10,
    "group_preference_fit": 0.10,
    "popularity_fit": 0.05,
    "coverage_fit": 0.05,
    "operational_fit": 0.05,
}

# Sub-Gewichte für ContextFitScore.total_score (§42), unabhängig von obiger
# Gesamt-Recommendation-Formel (die ContextScore ist nur EIN Summand davon, §78).
CONTEXT_FIT_SUBSCORE_WEIGHTS = {
    "season_score": 0.25,
    "location_score": 0.25,
    "indoor_outdoor_score": 0.15,
    "daypart_score": 0.15,
    "weather_score": 0.10,
    "infrastructure_score": 0.10,
}


def classify_group_size(guest_count: int) -> str:
    """small_group / medium_group / large_group / very_large_group (§39)."""
    for threshold, label in GROUP_SIZE_THRESHOLDS:
        if guest_count <= threshold:
            return label
    return GROUP_SIZE_VERY_LARGE


def apply_capped_modifier(base: float, deltas: list[float], cap_min: float, cap_max: float) -> float:
    """Kombiniert mehrere additive Deltas auf einen Basiswert und begrenzt das
    Ergebnis (Spec §64) - verhindert unkontrolliertes Aufschaukeln bei z.B.
    summer + hot + outdoor gleichzeitig."""
    value = base + sum(deltas)
    return max(cap_min, min(cap_max, value))


if __name__ == "__main__":
    assert apply_capped_modifier(1.0, [0.15, 0.25, 0.10], 0.9, 1.5) == 1.5
    assert apply_capped_modifier(1.0, [-5.0], 0.9, 1.5) == 0.9
    assert apply_capped_modifier(1.0, [0.05], 0.9, 1.5) == 1.05
    assert classify_group_size(5) == "small_group"
    assert classify_group_size(8) == "small_group"
    assert classify_group_size(9) == "medium_group"
    assert classify_group_size(25) == "medium_group"
    assert classify_group_size(26) == "large_group"
    assert classify_group_size(60) == "large_group"
    assert classify_group_size(61) == "very_large_group"
    print("party_context/config.py sanity check OK.")
