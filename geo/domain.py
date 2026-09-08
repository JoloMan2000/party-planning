"""Domain-Modell der Geo Platform (AUFGABE-Spec, siehe
``~/.claude/projects/.../memory/geo_platform_full_spec.txt``, Phase 1: Core
Platform + Party Location + Discover Radius).

Framework-freie Dataclasses + Enums, mirroring die Konvention von
``accounts/domain.py``/``party_engine``/``music_engine`` (keine FastAPI-/
sqlite3-Importe hier, nur reine Datenstrukturen).

Diese Datei enthält die GEMEINSAMEN Bausteine (``GeoPoint``, ``GeoAddress``,
``GeoPlace``, ``GeoSuggestion``, ``GeoSearchContext``) sowie das fachliche
``PartyLocation``/``PartyLocationView``-Modell (Spec §18, §75). Spec §148
verlangt ausdrücklich EINE gemeinsame Plattform statt paralleler
Implementierungen - künftige fachliche Objekte (``PublicEventLocation`` etc.,
siehe Backlog) sollen dieselben Bausteine wiederverwenden."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


@dataclass(frozen=True)
class GeoPoint:
    """WGS84/EPSG:4326-Koordinate (Spec §3). Absichtlich ein eigener Typ statt
    loser ``(lat, lon)``-Tupel, damit Verwechslungen der Reihenfolge an der
    Typgrenze auffallen, nicht erst zur Laufzeit."""

    latitude: float
    longitude: float


@dataclass(frozen=True)
class GeoAddress:
    """Strukturierte Adresse (Spec §8). Alle Teile optional außer
    ``formatted_address`` - Provider liefern unterschiedlich vollständige
    Adressdetails, das darf niemals einen Absturz verursachen."""

    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    district: str | None = None
    region: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    formatted_address: str = ""


class LocationPrecision(str, Enum):
    """Wie genau ein aufgelöster Ort ist (Spec §36) - z.B. eine reine
    Stadt-Auswahl (Discovery-Präferenzen) ist bewusst ``city``, keine
    vorgetäuschte ``exact``-Genauigkeit."""

    EXACT = "exact"
    ADDRESS = "address"
    STREET = "street"
    NEIGHBORHOOD = "neighborhood"
    CITY = "city"
    APPROXIMATE = "approximate"


@dataclass(frozen=True)
class GeoPlace:
    """Vollständiger, bestätigter Ort - Ergebnis von ``retrieve()``/
    ``reverse_geocode()`` (Spec §8). ``provider_place_id`` ist IMMER eine
    externe Provider-Referenz, nie eine interne Domain-ID (Spec §68)."""

    id: str
    name: str
    place_type: str
    address: GeoAddress
    point: GeoPoint | None
    provider: str
    provider_place_id: str
    precision: LocationPrecision = LocationPrecision.APPROXIMATE


@dataclass(frozen=True)
class GeoSuggestion:
    """Leichtgewichtiger Autocomplete-Vorschlag - Stufe 1 des Suggest->
    Retrieve-Flows (Spec §7, §70). Volle Adress-/Koordinatendaten werden
    bewusst NICHT bei jedem Tastenanschlag geladen/persistiert, sondern erst
    bei ``retrieve()`` nach expliziter Auswahl."""

    provider_place_id: str
    primary_text: str
    secondary_text: str
    place_type: str
    provider: str
    distance_meters: float | None = None


@dataclass(frozen=True)
class GeoSearchContext:
    """Such-Kontext für Bias (nicht Hard-Filter, Spec §12) + Session-Tracking
    (Spec §13, §139 - mappt bei Google Places auf den echten, kostenrelevanten
    ``sessiontoken``)."""

    bias_point: GeoPoint | None = None
    bias_country_code: str | None = None
    language: str | None = None
    search_session_id: str | None = None


class VisibilityPolicy(str, Enum):
    """Sichtbarkeitsregel für eine ``PartyLocation`` (Spec §26-29) - steuert,
    wann ein Gast die exakte Adresse/Koordinate sehen darf. Default ist
    bewusst ``exact_after_accept`` (nicht ``exact_immediately``), da die
    bestehende Codebase bislang GAR KEINE RSVP-Gate für den Ort kennt."""

    EXACT_AFTER_ACCEPT = "exact_after_accept"
    EXACT_AFTER_ACCEPT_OR_MAYBE = "exact_after_accept_or_maybe"
    EXACT_IMMEDIATELY = "exact_immediately"
    APPROXIMATE_ONLY = "approximate_only"


class LocationSource(str, Enum):
    """Woher eine ``PartyLocation`` stammt (Spec §24) - z.B. um eine manuell
    verschobene Pin-Position von einer Provider-Auswahl zu unterscheiden."""

    SEARCH_PROVIDER = "search_provider"
    MANUAL_PIN = "manual_pin"
    CURRENT_DEVICE_LOCATION = "current_device_location"
    SELECTED_CITY = "selected_city"
    ORGANIZER_ENTRY = "organizer_entry"


@dataclass
class PartyLocation:
    """Strukturierter, privacy-gegateter Party-Ort (Spec §18) - lebt in der
    NEUEN, additiven Tabelle ``party_locations``, komplett getrennt vom
    bestehenden ``Party.location``-Freitextfeld (siehe Plan: Backward-
    Compat-Entscheidung). ``public_location_label`` ist der einzige Text,
    der VOR RSVP-Freigabe sicher angezeigt werden darf."""

    id: str
    party_id: str
    place_name: str | None = None
    address: GeoAddress | None = None
    point: GeoPoint | None = None
    precision: LocationPrecision = LocationPrecision.APPROXIMATE
    provider: str | None = None
    provider_place_id: str | None = None
    public_location_label: str = ""
    visibility_policy: VisibilityPolicy = VisibilityPolicy.EXACT_AFTER_ACCEPT
    arrival_instructions: str | None = None
    source: LocationSource = LocationSource.ORGANIZER_ENTRY
    manually_adjusted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class PartyLocationView:
    """Die für einen KONKRETEN Betrachter freigegebene Projektion einer
    ``PartyLocation`` (Spec §75) - Ergebnis von
    ``geo.privacy.build_party_location_view``. Bei fehlender Berechtigung
    sind ``formatted_address``/``point``/``arrival_instructions`` IMMER
    ``None`` (nie nur UI-seitig verborgen, siehe ``geo/privacy.py``)."""

    visibility_level: str  # "exact" | "approximate"
    display_label: str
    formatted_address: str | None
    point: GeoPoint | None
    arrival_instructions: str | None
