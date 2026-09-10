"""Domain-Modell für den Account-basierten Multi-Tenant-Pivot (Phase 1).

Framework-freie Dataclasses + Enums, mirroring die Konvention von
``party_engine``/``music_engine``/``party_context`` (keine FastAPI-/sqlite3-
Importe hier, nur reine Datenstrukturen).

WICHTIG: ``Party`` hier ist ein NEUES, eigenständiges Konzept (Multi-Tenant,
ein User kann mehrere Parties hosten/besuchen) - komplett getrennt von der
bestehenden Singleton-Party-Config (``party_engine.domain.PartyConfig`` /
``event_theme.party_settings``). Phase 1 verdrahtet diese beiden Welten
bewusst NICHT miteinander (siehe Plan, Abschnitt "Explicit deferral list").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum


class RsvpStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    TENTATIVE = "tentative"
    DECLINED = "declined"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PartyRole(str, Enum):
    HOST = "host"
    CO_HOST = "co_host"
    GUEST = "guest"


@dataclass
class User:
    """Öffentliches User-Modell (AUFGABE-Spec §4). Enthält bewusst KEIN
    ``password_hash``-Feld - Auth-Geheimnisse gehören nicht in dieses Modell
    und werden nie über diese Dataclass serialisiert."""

    id: str
    email: str
    display_name: str
    profile_image: str = ""
    is_verified: bool = False
    email_verified: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Party:
    """Multi-Tenant-Party (AUFGABE-Spec §26 PartyProfile, minimale Phase-1-
    Variante). NICHT dasselbe wie ``party_engine.domain.PartyConfig``."""

    id: str
    host_user_id: str
    name: str
    description: str = ""
    starts_at: datetime | None = None
    location: str = ""
    cover_image: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PartyMembership:
    """Tatsächliche Beziehung User<->Party (AUFGABE-Spec §40) - bewusst
    getrennt von ``Invitation`` (der Einladung/RSVP-Anfrage)."""

    id: str
    party_id: str
    user_id: str
    role: PartyRole
    rsvp_status: RsvpStatus
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Invitation:
    """Einladung als echtes Domain-Objekt (AUFGABE-Spec §8), kein Notification."""

    id: str
    party_id: str
    host_user_id: str
    invited_user_id: str
    status: RsvpStatus = RsvpStatus.PENDING
    invitation_message: str = ""
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    viewed_at: datetime | None = None
    responded_at: datetime | None = None


@dataclass
class Notification:
    """In-App-Benachrichtigung (Phase 5, Poll-basiert - siehe
    ``backend/app/routers/notifications.py`` für den TODO zu echtem Push).
    Bewusst getrennt von ``Invitation``: eine Invitation ist die eigentliche
    Einladung/RSVP-Anfrage, eine Notification ist nur ein Hinweis-Datensatz
    für die Inbox (kann mehrere pro Invitation/Party geben, z.B. auch für
    RSVP-Antworten an den Host)."""

    id: str
    user_id: str
    party_id: str | None
    kind: str
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    read: bool = False


@dataclass
class UserProfile:
    """Social-Profile-/Onboarding-Layer (Onboarding-Spec, Phase 6) - bewusst
    GETRENNT von ``User`` (Account Identity, ``accounts/user_storage.py``):
    ``birth_date`` ist geschützt (kein normales PATCH, siehe
    ``apply_birth_date_correction``), ``gender`` ist optional/frei editierbar.
    ``display_name``/``profile_image`` bleiben pragmatisch auf ``User`` (dort
    bereits verdrahtet über den bestehenden Profile-Image-Upload-Endpoint) -
    keine schema-brechende Migration nur für die Layer-Trennung.

    ``username`` (Social-Graph-Phase-1) ist der stabile öffentliche
    Social-Identifier - bewusst auf ``UserProfile``, NICHT auf ``User``
    (Account/Auth-Identity bleibt E-Mail-basiert; ``username`` ist rein
    sozial/öffentlich und optional, bis der User ihn setzt). Anders als
    ``User.email`` (immer auf lowercase normalisiert gespeichert, siehe
    ``user_storage.create_user``) bleibt die vom User gewählte
    Groß-/Kleinschreibung hier erhalten - Eindeutigkeit wird stattdessen
    ausschließlich über den ``COLLATE NOCASE``-Unique-Index in
    ``accounts/profile_storage.py`` erzwungen.

    Die fünf folgenden Felder (Social-Graph-Phase-3 + Phase-7) sind bewusst
    VERHALTENS-Policies, keine Identitäts-Felder wie ``username`` - sie
    werden nicht vom User selbst "angezeigt", sondern steuern, was ANDERE
    User über diesen User sehen/tun dürfen (siehe Durchsetzung in
    ``backend/app/routers/social.py``: ``GET /users/{id}/friends``,
    ``search_users``, ``send_friend_request``, ``GET /users/{id}/following/*``).
    ``friend_request_privacy`` kennt bewusst NUR "nobody"/"everyone" - die
    vom Spec vorgeschlagene dritte Stufe "Friends of Friends" wurde für
    Phase 3 explizit gestrichen, da sie eine Zwei-Hop-Graph-Query braucht,
    ein deutlich größerer technischer Aufwand als der Rest dieser
    "Polish"-Phase.

    ``following_visibility`` (Social-Graph-Phase-7, Spec §110) steuert, ob
    ANDERE die Listen der gefolgten Organizer/Events dieses Users sehen
    dürfen. Default ist bewusst die restriktivste Stufe ("nobody" =
    "privat", genau die Empfehlung des Spec: "Ob andere sehen dürfen ...
    soll nicht automatisch öffentlich sein. Empfehlung Default: private").
    Durchgesetzt identisch zu ``friend_list_visibility``."""

    user_id: str
    birth_date: date
    gender: str = ""
    bio: str = ""
    username: str = ""
    friend_list_visibility: str = "friends"  # "nobody" | "friends" | "everyone"
    friend_request_privacy: str = "everyone"  # "nobody" | "everyone"
    discoverable_by_username: bool = True
    discoverable_by_name: bool = True
    following_visibility: str = "nobody"  # "nobody" (= Spec "private") | "friends" | "everyone"
    onboarding_completed_at: datetime | None = None
    profile_completion_version: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserDiscoveryPreferences:
    """Explicit-Discovery-Preferences-Layer (Onboarding-Spec, Phase 6) -
    Radius/Ort/Timing/Preis/Mainstream-Slider. Musik-Genres/Artists/
    Event-Interessen leben in eigenen Tabellen (siehe unten), da sie
    Listen statt Skalarwerte sind."""

    user_id: str
    discovery_radius_km: float = 25.0
    allow_major_events_outside_radius: bool = False
    discovery_city: str = ""
    discovery_lat: float | None = None
    discovery_lon: float | None = None
    preferred_days: list[str] = field(default_factory=list)
    preferred_dayparts: list[str] = field(default_factory=list)
    price_preference: str = ""
    mainstream_discovery: float = 0.5
    personalized_recommendations_enabled: bool = True
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExplicitDiscoveryPreference:
    """Event-Typ-/Interest-Tag-Auswahl (generische Kategorie+Item-Auswahl,
    siehe ``accounts/discovery_catalogs.py`` für die stabilen IDs). Musik-
    Genres/Artists haben eigene, feldreichere Dataclasses (siehe unten)."""

    id: str
    user_id: str
    category: str  # "event_type" | "interest_tag"
    item_id: str
    source: str = "manual"  # "manual" | "spotify_confirmed" (Phase 7)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserMusicPreference:
    """Bewusst OHNE Live-Spotify-Abhängigkeit - ``genre_id`` referenziert
    ``accounts.discovery_catalogs.MUSIC_GENRE_CATALOG`` (App-eigene, stabile
    IDs), niemals eine Spotify-Genre-ID direkt (Provider-Unabhängigkeit)."""

    user_id: str
    genre_id: str
    preference_level: str  # love | like | neutral | dislike | excluded
    source: str = "manual"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserArtistPreference:
    """``artist_reference`` ist in Phase 6 freier Text (App-eigene ID gibt es
    noch nicht) - Phase 7 fügt Spotify-bestätigte Referenzen mit
    ``source="spotify_confirmed"`` hinzu, ohne dieses Feld umzubauen."""

    user_id: str
    artist_reference: str
    display_name: str
    preference_level: str
    source: str = "manual"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SpotifyConnection:
    """Öffentlich sichtbarer Verbindungsstatus zu Spotify (Onboarding-Spec,
    Phase 7) - enthält NIE Rohtokens (analog zu ``User`` ohne
    ``password_hash``). Access-/Refresh-Token leben verschlüsselt
    ausschließlich in ``accounts.spotify_storage``, nie in dieser Dataclass
    oder einer API-Response."""

    user_id: str
    spotify_user_id: str
    scope: str
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BirthDateCorrection:
    """Audit-Eintrag für den kontrollierten Geburtsdatum-Korrektur-Flow
    (Onboarding-Spec: ``birth_date`` ist NICHT über das normale
    Profil-PATCH änderbar). Bewusst ein einfaches Audit-Log, keine
    Admin-Review-Queue - dafür gibt es in dieser App aktuell keinen
    Support-/Moderations-Workflow."""

    id: str
    user_id: str
    previous_birth_date: date | None
    new_birth_date: date
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DiscoverAction(str, Enum):
    """Ergebnis einer Swipe-Geste im Discover-Deck (MVP, siehe
    ``discover_nearby_event_engine_full_spec.txt``). Bewusst GETRENNT von
    ``RsvpStatus`` - Discover ist ein eigener Einstiegspfad für bereits
    registrierte User (Swipe rechts = Sofort-Beitritt via
    ``party_storage.upsert_membership``), nicht die bestehende Button-RSVP
    für per E-Mail eingeladene Gäste (``invitations.py``), die unangetastet
    bleibt."""

    GOING = "going"
    MAYBE = "maybe"
    NOT_INTERESTED = "not_interested"


class DiscoverNotInterestedReason(str, Enum):
    """Optionaler Grund bei ``NOT_INTERESTED`` (Discover-Engine-Phase-1,
    Build-Schritt 3) - bewusst NUR bei ``NOT_INTERESTED`` erlaubt (siehe
    Validierung in ``backend/app/schemas/discover.py``), da ein positives
    Swipe-Ergebnis (``GOING``/``MAYBE``) keinen Ablehnungsgrund braucht.
    Zero-Friction: der Grund ist immer optional, ein Swipe ohne Angabe bleibt
    ein vollwertiges Signal (leerer String, kein Pflichtfeld). Feed für die
    spätere Learned-Affinity-Auswertung (Build-Schritt 4) - jeder Wert ist
    bewusst so gewählt, dass er ein unterscheidbares Lern-Signal trägt
    (z.B. ``WRONG_VIBE`` sollte künftig stärker auf Genre-/Tag-Affinität
    wirken als ``TOO_FAR`` auf die Distanz-Komponente)."""

    WRONG_VIBE = "wrong_vibe"
    TOO_FAR = "too_far"
    BAD_TIMING = "bad_timing"
    NOT_INTERESTED_IN_ORGANIZER = "not_interested_in_organizer"
    OTHER = "other"


@dataclass
class PublicEvent:
    """Discovery-Projektion einer bereits existierenden ``Party`` - kein
    eigenständiges Event-/Organizer-Konzept (MVP-Scope-Entscheidung: Hosts
    veröffentlichen bestehende private Parties, statt eines separaten
    Event-Erstellungs-Flows). Eine Zeile pro veröffentlichter Party;
    Unpublish löscht die Zeile (siehe ``accounts/discover_storage.py``)."""

    id: str
    party_id: str
    event_type: str = ""
    interest_tags: list[str] = field(default_factory=list)
    max_guests: int = 0
    # Geo Platform (Spec §123-124): schaltet für Discover-Radius-Eligibility
    # einen erweiterten Radius frei, WENN der User zusätzlich
    # ``allow_major_events_outside_radius`` gesetzt hat (siehe
    # ``accounts/discover_storage.py::MAJOR_EVENT_RADIUS_KM``).
    is_major_event: bool = False
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DiscoverActionRecord:
    """Auditierbare Swipe-Aktion eines Users auf eine ``PublicEvent`` -
    UNIQUE(user_id, party_id), damit erneutes Swipen überschreibt statt
    Duplikate anzuhäufen (siehe ``discover_storage.upsert_discover_action``).

    ``reason`` (Build-Schritt 3) ist ein freier String statt direkt
    ``DiscoverNotInterestedReason`` - Persistenz-Ebene ist bewusst permissiv
    (leerer String = kein Grund angegeben), die Enum-Validierung passiert
    ausschließlich an der API-Grenze (``backend/app/schemas/discover.py``),
    damit ein künftiger neuer Reason-Wert nicht sofort alte, bereits
    gespeicherte Zeilen invalidiert."""

    id: str
    user_id: str
    party_id: str
    action: DiscoverAction
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EventRecommendationExposure:
    """Auditiert, dass eine ``PublicEvent`` einem User tatsächlich im Deck
    GEZEIGT wurde (Discover-Engine-Spec §74-75) - ohne diesen Datensatz lässt
    sich "nie gezeigt" nicht von "gezeigt, aber ignoriert" unterscheiden, was
    für spätere Learning-Auswertungen (Phase 1, ``accounts/discover_learning.py``)
    kritisch ist. Bewusst append-only, keine Deduplizierung: jeder Deck-Abruf
    ist ein eigenes Exposure-Ereignis, auch für dieselbe Party."""

    id: str
    user_id: str
    party_id: str
    rank: int
    model_version: str
    shown_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BlockedOrganizer:
    """Harter Ausschluss eines Organizers (Discover-Engine-Phase-1, Spec §40) -
    bewusst GETRENNT von einem einzelnen ``NOT_INTERESTED``-Swipe: ein Block
    ist eine explizite Nutzer-Entscheidung, keine gelernte/inferierte
    Präferenz, und übersteht deshalb auch ein ``reset-learning`` (siehe
    ``accounts/discover_learning.py::reset_learned_profile``). Wirkt als
    Hard-Filter VOR jedem Ranking (``list_candidate_publications``), niemals
    durch Diversity/Exploration überschreibbar."""

    id: str
    user_id: str
    organizer_user_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LearnedAffinitySignal:
    """Gelernte Affinität zu EINEM Attribut (Discover-Engine-Phase-1,
    Build-Schritt 4) - bewusst GETRENNT von den expliziten Preferences
    (``UserDiscoveryPreferences``/``ExplicitDiscoveryPreference``): dieser
    Datensatz entsteht ausschließlich aus beobachtetem Verhalten (Swipes,
    siehe ``accounts/discover_learning.py::record_signal_from_action``), nie
    aus einer direkten User-Eingabe, und darf explizite Preferences im
    späteren Blended Ranking (Build-Schritt 5) deshalb nur ERGÄNZEN, nie
    überschreiben.

    ``value`` ist ein laufender gewichteter Mittelwert der pro Swipe
    beobachteten Fit-Ziele, auf derselben (0, 1]-Skala wie die Fit-Terme in
    ``accounts/discover_ranking.py`` (0.5 = neutral) - bewusst NICHT bereits
    decayed gespeichert: die Alters-Abschwächung (Halbwertszeit, siehe
    ``AFFINITY_HALF_LIFE_DAYS``) passiert ausschließlich LESEND in
    ``get_learned_affinity``, damit ``updated_at`` immer den Zeitpunkt der
    letzten tatsächlichen Beobachtung trägt statt eines künstlich
    vorgealterten Werts. ``observation_count`` ist das Konfidenzmaß, das
    Build-Schritt 5 als ``observation_weight`` im Bayesian-Shrinkage-Blend
    verwendet - je mehr Beobachtungen, desto mehr Gewicht gegenüber dem
    expliziten Prior."""

    id: str
    user_id: str
    attribute_category: str  # "event_type" | "interest_tag"
    attribute_value: str
    value: float = 0.5
    observation_count: float = 0.0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RsvpHistoryEntry:
    """Auditierbare Statusänderung (AUFGABE-Spec §42)."""

    id: str
    invitation_id: str
    party_id: str
    user_id: str  # die eingeladene Person, um die es in diesem Eintrag geht
    previous_status: RsvpStatus
    new_status: RsvpStatus
    changed_by_user_id: str  # eingeladene Person bei normalem RSVP, Host bei Revoke
    client_request_id: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
