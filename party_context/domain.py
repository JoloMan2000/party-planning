"""
Domain-Modell der Party Context Intelligence Layer (Spec §2/§8/§12/§19/§24/§30/§51/§72/§74).
================================================================================================

Dieses Modul enthält NUR Datenstrukturen (dataclasses), keine Logik. Zentrale
Architekturregel (Spec §97/§98): jede Party liefert genau EINEN ``PartyContext``
(admin-erfasste Rahmendaten), aus dem die ``PartyContextEngine`` genau EINEN
``DerivedPartyContext`` ableitet. Beverage-, Food-, Music- und Recommendation-
Engine konsumieren ausschließlich diesen fertig abgeleiteten Kontext - keine
Engine berechnet Saison/Tageszeit/Temperaturklasse eigenständig (§10).

Hinweis Namenskollision: ``party_engine.recommendation_domain.RecommendationContext``
(vormals ``PartyContext``) ist ein anderer, schlankerer Typ, der ausschließlich
intern von ``score_item_for_occasion()`` konsumiert wird. Nicht verwechseln.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


# --- §2: zentrales Eingabe-Objekt (Party Setup) -----------------------------------


@dataclass
class PartyContext:
    """Admin-erfasste Rahmendaten einer Party (Spec §2/§49/§50)."""

    occasion_id: str = ""

    start_datetime: datetime | None = None
    duration_hours: float = 4.0
    guest_count: int = 1

    # Datum / Saison - season kann admin-override sein, sonst aus start_datetime
    # abgeleitet (§5).
    season: str | None = None
    month: int | None = None

    # Location (§3/§4) - location_type und indoor_outdoor sind bewusst getrennt.
    location_type: str = "other"
    indoor_outdoor: str = "outdoor"  # indoor, outdoor, mixed

    # Infrastruktur (§49/§50)
    has_grill: bool = False
    has_kitchen: bool = False
    has_fridge: bool = False
    has_freezer: bool = False
    has_ice_machine: bool = False
    has_bar: bool = False
    has_coffee_machine: bool = False
    has_power: bool = False
    has_running_water: bool = False

    # Musik / Umgebung
    music_volume_limit: str | None = None
    dancing_possible: bool = False
    neighbors_sensitive: bool = False

    # Wetter (optional, §44/§45/§73)
    expected_temperature_c: float | None = None
    weather_condition: str | None = None
    rain_probability: float | None = None

    # Partyorganisation
    seating_ratio: float | None = None
    self_service: bool = True

    # optionale freie Kontext-Tags
    context_tags: set[str] = field(default_factory=set)


# --- §12: Context-Affinität für empfehlbare Items -----------------------------------


@dataclass
class ContextAffinity:
    """Kontext-Fit-Metadaten eines empfehlbaren Items (Spec §12/§13/§14).

    Alle Werte 0..1 (0 = unpassend, 1 = ideal). Fehlende Keys werden vom
    Scoring als neutral (0.5) behandelt (siehe context_fit.py)."""

    seasons: dict[str, float] = field(default_factory=dict)
    locations: dict[str, float] = field(default_factory=dict)
    indoor_outdoor: dict[str, float] = field(default_factory=dict)
    dayparts: dict[str, float] = field(default_factory=dict)

    weather_conditions: dict[str, float] = field(default_factory=dict)

    min_temperature_c: float | None = None
    max_temperature_c: float | None = None

    required_capabilities: set[str] = field(default_factory=set)
    preferred_capabilities: set[str] = field(default_factory=set)


# --- §19/§24/§30: Engine-spezifische Kontext-Modifier ---------------------------------


@dataclass
class BeverageContextModifiers:
    """Demand-Modifier für die Beverage Engine (Spec §19-§23).

    WICHTIG (§21): Es gibt bewusst KEIN ``alcohol_demand_multiplier``-Feld -
    Hitze/Sommer/Outdoor dürfen den Alkoholbedarf niemals direkt erhöhen.
    Wetterbedingter Mehrbedarf fließt ausschließlich in Wasser/Eis/alkoholfrei."""

    water_multiplier: float = 1.0
    non_alcoholic_multiplier: float = 1.0
    ice_multiplier: float = 1.0
    hot_drink_multiplier: float = 1.0
    cold_refreshing_drink_multiplier: float = 1.0
    cocktail_complexity_penalty: float = 0.0


@dataclass
class FoodContextModifiers:
    """Recommendation-/Operational-Modifier für die Food Engine (Spec §24-§28)."""

    fresh_food_preference: float = 1.0
    hot_food_preference: float = 1.0
    comfort_food_preference: float = 1.0
    salad_preference: float = 1.0
    grill_preference: float = 1.0
    fingerfood_preference: float = 1.0
    dessert_preference: float = 1.0
    spoilage_operational_penalty: float = 0.0


@dataclass
class MusicContextModifiers:
    """Ranking-/Dramaturgie-Modifier für die Music Engine (Spec §30-§37).

    WICHTIG (§66): Musik kennt KEIN Demand-Multiplier-Modell - diese Werte
    verändern Genre-Gewichte/Energy-Curve/Danceability/Phasen-Strategie, nie
    die Musikmenge (die ergibt sich ausschließlich aus der Party-Dauer)."""

    energy_modifier: float = 0.0
    danceability_modifier: float = 0.0
    conversation_modifier: float = 0.0
    bass_penalty: float = 0.0
    late_night_energy_penalty: float = 0.0
    outdoor_modifier: float = 0.0


# --- §51: Location-Stammdaten --------------------------------------------------------


@dataclass
class LocationProfile:
    """Stammdaten je Location-Typ (Spec §51-§60)."""

    id: str
    label_de: str = ""
    label_en: str = ""

    default_indoor_outdoor: str = "outdoor"
    default_capabilities: dict[str, bool] = field(default_factory=dict)

    preferred_tags: dict[str, float] = field(default_factory=dict)
    discouraged_tags: dict[str, float] = field(default_factory=dict)

    music_characteristics: dict[str, float] = field(default_factory=dict)
    food_characteristics: dict[str, float] = field(default_factory=dict)
    beverage_characteristics: dict[str, float] = field(default_factory=dict)


# --- §72: Admin-Override -------------------------------------------------------------


@dataclass
class PartyContextOverride:
    """Ein einzelner Admin-Override, stärker als abgeleitete Defaults (Spec §71/§72)."""

    key: str
    value: Any
    reason: str | None = None


# --- §73/§74: Wetter-Architektur (optional, v1 ohne konkreten Provider) --------------


@dataclass
class WeatherContext:
    """Momentaufnahme einer Wettervorhersage (Spec §74)."""

    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    condition: str | None = None
    precipitation_probability: float | None = None
    wind_speed: float | None = None
    fetched_at: datetime | None = None


class WeatherProvider(Protocol):
    """Interface für eine künftige externe Wetterquelle (Spec §73). Version 1
    der App funktioniert vollständig ohne konkrete Implementierung (Fallback
    auf saisonale Defaults, siehe engine.py/derive_context())."""

    def get_party_weather(
        self, location_type: str, start_datetime: datetime | None
    ) -> WeatherContext | None: ...


# --- §8: zentrales Ergebnis-Objekt ---------------------------------------------------


@dataclass
class DerivedPartyContext:
    """Zentrale, von der ``PartyContextEngine`` abgeleitete Wahrheit über die
    Party (Spec §8/§9). Alle nachgelagerten Engines konsumieren ausschließlich
    dieses Objekt - keine Engine hält eine isolierte Vorstellung der Party (§98)."""

    season: str = "summer"

    daypart_primary: str = "evening"
    daypart_weights: dict[str, float] = field(default_factory=dict)

    temperature_class: str = "mild"  # cold, cool, mild, warm, hot
    weather_is_actual: bool = False  # True falls expected_temperature_c gesetzt war (§45)
    temperature_c: float | None = None
    weather_condition: str | None = None

    indoor_outdoor: str = "outdoor"
    location_type: str = "other"

    group_size_class: str = "medium_group"

    location_tags: set[str] = field(default_factory=set)

    available_capabilities: set[str] = field(default_factory=set)
    operational_constraints: set[str] = field(default_factory=set)

    recommendation_tags: dict[str, float] = field(default_factory=dict)

    beverage_modifiers: BeverageContextModifiers = field(default_factory=BeverageContextModifiers)
    food_modifiers: FoodContextModifiers = field(default_factory=FoodContextModifiers)
    music_modifiers: MusicContextModifiers = field(default_factory=MusicContextModifiers)

    explanations: list[str] = field(default_factory=list)

    context_model_version: str = "1.0"


# --- §42: Erklärbares Context-Fit-Ergebnis pro Item -----------------------------------


@dataclass
class ContextFitScore:
    """Erklärbarer Context-Fit eines einzelnen Items (Spec §42/§43)."""

    total_score: float = 0.0

    season_score: float = 0.5
    location_score: float = 0.5
    indoor_outdoor_score: float = 0.5
    daypart_score: float = 0.5
    weather_score: float = 0.5
    infrastructure_score: float = 0.5

    penalties: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
