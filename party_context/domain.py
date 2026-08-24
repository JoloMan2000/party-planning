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

    # Geografie/Kultur (Geo-Kultur-Erweiterung §2/§3): party_address wird vom
    # Aufrufer aus der bereits bestehenden ``event_theme.party_location``
    # gespiegelt (kein Duplikat-Eingabefeld in der UI). country_code ist ein
    # optionaler Admin-Override (ISO 3166-1 alpha-2) - leer bedeutet
    # "automatisch per Geocoding aus party_address ableiten" (§2 der
    # Geo-Kultur-Spec, analog zum ``season``-Override-Muster oben).
    party_address: str = ""
    country_code: str = ""

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


# --- Geo-Kultur-Erweiterung §2: Geocoding-Architektur ---------------------------------


@dataclass
class GeocodingResult:
    """Ergebnis einer Adress->Land-Auflösung (Geo-Kultur-Spec §2)."""

    country_code: str  # ISO 3166-1 alpha-2, z.B. "DE", "IN", "PE"
    country_name: str = ""
    display_address: str = ""  # von der API normalisierte Adresse (Debug/Log)


class GeocodingProvider(Protocol):
    """Interface für eine Adress->Land-Quelle (Geo-Kultur-Spec §2). Muss NIE
    raisen - jeder Fehler (Netzwerk/Timeout/kein Treffer) liefert ``None``,
    der Aufrufer fällt dann auf den neutralen Fallback zurück (§4)."""

    def geocode(self, address: str) -> GeocodingResult | None: ...


# --- Geo-Kultur-Erweiterung §4: Culture-Stammdaten -------------------------------------


@dataclass
class CultureProfile:
    """Länder-Stammdaten für kulturell geprägte Essens-/Getränke-/Musik-
    Präferenzen (Geo-Kultur-Spec §4). Wirkt ausschließlich als leichtes,
    gecapptes Re-Weighting bestehender Tags - NIE als harte Filterung
    (siehe Modul-Docstring von ``party_context.culture``)."""

    country_code: str
    country_name: str = ""

    preferred_food_tags: dict[str, float] = field(default_factory=dict)
    discouraged_food_tags: dict[str, float] = field(default_factory=dict)
    preferred_beverage_tags: dict[str, float] = field(default_factory=dict)
    discouraged_beverage_tags: dict[str, float] = field(default_factory=dict)

    genre_bias: dict[str, float] = field(default_factory=dict)


# --- Geo-Kultur-Erweiterung §7: Persistentes Cross-Party-Lernen -----------------------


@dataclass
class PartyRunSnapshot:
    """Eingefrorener Kontext-Snapshot einer ABGESCHLOSSENEN Party (Geo-Kultur-
    Spec §7). Wird beim automatischen Party-Lifecycle-Trigger geschrieben und
    danach NIE mehr verändert - stabile Lern-Basis. ``id=None`` vor dem
    Speichern (wird von ``learning_storage.save_party_run`` vergeben)."""

    id: int | None = None
    started_at: datetime | None = None
    occasion_id: str = ""
    country_code: str = ""
    season: str = ""
    temperature_class: str = ""
    location_type: str = ""
    group_size_class: str = ""


@dataclass
class SelectionEvent:
    """Eine einzelne, bewusst ANONYMISIERTE Gast-Auswahl innerhalb eines
    ``PartyRunSnapshot`` (Geo-Kultur-Spec §7). Kein guest_name/keine sonst
    identifizierende Info - getrennt von der operativen ``responses``-Tabelle."""

    id: int | None = None
    party_run_id: int = 0
    item_id: str = ""
    item_type: str = ""  # direct_consumable | recipe | track
    event_type: str = "selected"


@dataclass
class LearningHistory:
    """Aggregierte Sicht über alle vergangenen ``PartyRunSnapshot``s + deren
    ``SelectionEvent``s (Geo-Kultur-Spec §7), Eingabe für
    ``compute_learned_preference_score()``. Leer (keine runs/events) beim
    ersten Lauf ohne Historie - Kaltstart-Pflichtverhalten §7."""

    runs: list[PartyRunSnapshot] = field(default_factory=list)
    events: list[SelectionEvent] = field(default_factory=list)


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

    # Geo-Kultur-Erweiterung §3: country_code bleibt "" (neutral, kein Bias),
    # solange weder Admin-Override noch erfolgreiches Geocoding vorliegen.
    country_code: str = ""
    country_name: str = ""
    country_source: str = "unknown"  # "admin_override" | "geocoded" | "unknown"
    culture_food_tags: dict[str, float] = field(default_factory=dict)
    culture_beverage_tags: dict[str, float] = field(default_factory=dict)
    culture_genre_bias: dict[str, float] = field(default_factory=dict)

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

    # Geo-Kultur-Spec §4/§9: Tag-Overlap zwischen Item und den vom aktiven
    # Länder-``CultureProfile`` gelieferten ``culture_food_tags``/
    # ``culture_beverage_tags``. Neutral 0.5, solange kein Land bekannt ist
    # (kein Bias, siehe ``culture.get_culture_profile``-Fallback).
    culture_score: float = 0.5

    penalties: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
