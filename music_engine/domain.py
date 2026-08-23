"""
Domain-Modell der Music Recommendation & Party Playlist Engine.
==================================================================

Reine Datenstrukturen (dataclasses), keine Logik (siehe party_engine/domain.py
für dieselbe Konvention). Felder/Namen orientieren sich eng an den
Beispiel-Snippets der Spec (music_engine_full_spec.txt, §4-9/17/20/46/60/
62-63/80-81/90-91), teils mit zusätzlichen sinnvollen Defaults, damit Objekte
auch ohne vollständige Kuratierung sofort nutzbar sind (analog zu
RecommendationMetadata's neutralen 0.5-Defaults in
party_engine/recommendation_domain.py).

Zentrale Regel (Spec §3/§13/§119): Spotify ist Resolver/Export-Layer, nicht
das Domain-Modell. ``MusicTrack.spotify_uri`` ist rein optional/extern.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Katalog / Track --------------------------------------------------------


@dataclass
class MusicTrack:
    """Ein interner Track (Spec §5). Die interne ``id`` ist die kanonische
    Referenz überall in der Engine - ``spotify_uri`` wird erst ganz am Ende
    vom SpotifyAdapter verwendet (Spec §3)."""

    id: str

    title: str
    artist: str

    duration_ms: int | None = None

    genres: set[str] = field(default_factory=set)
    eras: set[str] = field(default_factory=set)
    moods: set[str] = field(default_factory=set)

    language: str | None = None

    energy_score: float | None = None
    danceability_score: float | None = None

    familiarity_prior: float = 0.5
    party_score: float = 0.5
    singalong_score: float = 0.3

    explicit: bool | None = None

    tags: set[str] = field(default_factory=set)

    spotify_uri: str | None = None
    provider_ids: dict[str, str] = field(default_factory=dict)

    # Spec §79: Versionsvarianten (Original/Remaster/Live/Remix/...) desselben
    # Songs teilen dieselbe ``canonical_song_identity``, damit die Engine
    # standardmäßig nicht mehrere Versionen desselben Songs gleichzeitig
    # einplant (siehe resolver.py: canonical_song_identity()).
    version_type: str = "original"  # original, remaster, live, acoustic, radio_edit, remix, cover
    canonical_song_id: str = ""  # wird beim Laden aus title+artist abgeleitet, falls leer

    # Spec §89: Datentrennung - woher stammen Metadaten/Features.
    metadata_source: str = "seed_catalog"  # seed_catalog, spotify, admin, dynamic_resolution


@dataclass
class MusicCatalog:
    """Vollständiger, geladener Track-Katalog inkl. vorberechneter
    Resolver-Indizes (Spec §93: normalized_song_key/normalized_artist_key/
    genre-/era-/tag-Index), analog zu ``PartyCatalog`` in party_engine/domain.py.

    Die Indizes werden von ``music_engine/catalog.py`` beim Laden befüllt,
    damit Resolver/Candidate-Provider sie ohne erneutes Scannen des gesamten
    Katalogs nutzen können.
    """

    tracks: dict[str, MusicTrack] = field(default_factory=dict)

    # normalisierter "artist - title"-Key -> track_id (Spec §93/§78: Basis der
    # Dedup-/Resolution-Logik in resolver.py).
    normalized_song_index: dict[str, str] = field(default_factory=dict)

    # normalisierter Titel-Key (ohne Artist-Anker) -> Liste von track_ids.
    # Ermöglicht Resolution reiner Titel-Freitexte ("Mr Brightside" ohne
    # Artist-Angabe), siehe resolver.py.
    normalized_title_index: dict[str, list[str]] = field(default_factory=dict)

    # normalisierter Artist-Name -> Liste von track_ids.
    normalized_artist_index: dict[str, list[str]] = field(default_factory=dict)

    genre_index: dict[str, list[str]] = field(default_factory=dict)
    era_index: dict[str, list[str]] = field(default_factory=dict)
    tag_index: dict[str, list[str]] = field(default_factory=dict)

    # canonical_song_id -> Liste von track_ids (alle Versionen desselben Songs,
    # Spec §79 Versionsvarianten).
    canonical_song_index: dict[str, list[str]] = field(default_factory=dict)

    def get_track(self, track_id: str) -> MusicTrack | None:
        return self.tracks.get(track_id)


# --- Songwünsche -------------------------------------------------------------


@dataclass
class RawSongRequest:
    """Ein roher, ungefilterter Gästewunsch (Spec §6). ``guest_id`` ist in
    dieser App der (getrimmte) Gästename, da kein separates Gast-ID-System
    existiert (siehe legacy_adapter.py)."""

    guest_id: str
    text: str

    submitted_at: str = ""

    # Zusatzfeld (nicht in der Spec-Skizze, aber nötig, um den ursprünglichen
    # {"artist", "title"}-Freitext der bestehenden UI verlustfrei durchzureichen,
    # statt "Artist - Title" wieder zusammenzubauen und erneut parsen zu müssen).
    artist_hint: str = ""
    title_hint: str = ""


@dataclass
class ResolvedSongRequest:
    """Ergebnis der Track-Resolution eines ``RawSongRequest`` (Spec §7)."""

    guest_id: str

    original_text: str

    resolution_type: str = "unresolved"  # track, artist, genre, era, mood, unresolved

    track_id: str | None = None

    artist: str | None = None
    genre: str | None = None
    era: str | None = None

    confidence: float = 0.0

    needs_review: bool = False


@dataclass
class TrackPreference:
    """Aggregierte, deduplizierte Präferenz für einen Track nach Normalisierung
    (Spec §9)."""

    track_id: str

    supporting_guests: set[str] = field(default_factory=set)

    request_count: int = 0

    source: str = "guest_request"  # guest_request, admin_request, recommendation

    guest_priority_score: float = 0.0

    admin_priority_score: float = 0.0

    confidence: float = 1.0


# --- Occasion / Group Taste --------------------------------------------------


@dataclass
class MusicOccasionProfile:
    """Musikalischer Prior eines Anlasses (Spec §19/§20)."""

    occasion_id: str

    preferred_genres: dict[str, float] = field(default_factory=dict)
    discouraged_genres: dict[str, float] = field(default_factory=dict)

    preferred_eras: dict[str, float] = field(default_factory=dict)

    preferred_moods: dict[str, float] = field(default_factory=dict)

    preferred_tags: dict[str, float] = field(default_factory=dict)
    discouraged_tags: dict[str, float] = field(default_factory=dict)

    familiarity_target: float = 0.6
    danceability_target: float = 0.5

    mainstream_target: float = 0.6

    # Statt list["MusicPhase"] (Spec-Skizze) referenziert das Profil hier nur
    # die Phasen-IDs mit Ziel-Energie -- die tatsächlichen start/end-Fraktionen
    # werden erst von phases.py aus der Partydauer abgeleitet (Spec §47:
    # "Die tatsächlichen Minuten ergeben sich aus der Gesamtdauer"). Das
    # vermeidet eine zirkuläre Abhängigkeit domain.py -> phases-Logik.
    energy_curve: dict[str, float] = field(default_factory=dict)

    diversity_rules: dict = field(default_factory=dict)

    default_explicit_policy: str = "allow"  # allow, avoid, ban

    inherits_from: list[str] = field(default_factory=list)
    profile_version: str = "1.0"


DEFAULT_MUSIC_OCCASION_ID = "casual_get_together"


@dataclass
class GroupMusicProfile:
    """Aus allen Songwünschen abgeleitetes Gruppenprofil (Spec §17/§18)."""

    genre_weights: dict[str, float] = field(default_factory=dict)
    era_weights: dict[str, float] = field(default_factory=dict)
    mood_weights: dict[str, float] = field(default_factory=dict)

    energy_target: float = 0.5
    danceability_target: float = 0.5

    familiarity_target: float = 0.6
    singalong_target: float = 0.4

    language_weights: dict[str, float] = field(default_factory=dict)

    artist_weights: dict[str, float] = field(default_factory=dict)

    confidence: float = 0.0

    request_count: int = 0
    unique_requesting_guests: int = 0


# --- Phasen / Strategie -------------------------------------------------------


@dataclass
class MusicPhase:
    """Eine Dramaturgie-Phase der Party (Spec §46)."""

    id: str

    start_fraction: float = 0.0
    end_fraction: float = 1.0

    target_energy: float = 0.5
    target_danceability: float = 0.5
    target_familiarity: float = 0.6

    preferred_tags: dict[str, float] = field(default_factory=dict)

    label_de: str = ""
    label_en: str = ""


@dataclass
class MusicStrategy:
    """Konkretes, für einen Party-Lauf berechnetes Strategie-Objekt: das
    (occasion-prior x group-taste, Bayesian-shrinkage-kombinierte, Spec §50)
    Zielprofil plus die daraus abgeleiteten Phasen. Wird vom MusicDirector
    (engine.py: build_music_strategy()) erzeugt und ist die Grundlage für
    Candidate Generation + Scoring."""

    occasion_id: str

    genre_weights: dict[str, float] = field(default_factory=dict)
    era_weights: dict[str, float] = field(default_factory=dict)
    mood_weights: dict[str, float] = field(default_factory=dict)
    tag_weights: dict[str, float] = field(default_factory=dict)

    familiarity_target: float = 0.6
    danceability_target: float = 0.5
    energy_target: float = 0.5

    phases: list[MusicPhase] = field(default_factory=list)

    group_weight: float = 0.0  # Spec §50: request_count / (request_count + 15)
    explicit_policy: str = "allow"

    model_version: str = "1.0"


# --- Kandidaten / Scoring -----------------------------------------------------


@dataclass
class TrackCandidate:
    """Ein von einem CandidateProvider vorgeschlagener Track (Spec §51)."""

    track_id: str
    source: str = "exploration"
    # requested_track, admin, occasion_seed, group_taste,
    # artist_neighbourhood, genre_era, exploration
    supporting_guests: set[str] = field(default_factory=set)
    request_count: int = 0
    admin_status: str | None = None  # must_play, preferred, neutral, avoid, banned (falls überschrieben)


@dataclass
class TrackScore:
    """Erklärbares Score-Ergebnis für einen TrackCandidate (Spec §49/§70)."""

    track_id: str
    total_score: float = 0.0

    guest_preference_weight: float = 0.0
    occasion_fit: float = 0.0
    group_taste_fit: float = 0.0
    phase_fit: float = 0.0
    familiarity_fit: float = 0.0
    diversity_fit: float = 0.0
    admin_fit: float = 0.0

    reasons: list[str] = field(default_factory=list)
    source: str = "exploration"
    supporting_guests: set[str] = field(default_factory=set)


# --- Playlist ------------------------------------------------------------------


@dataclass
class PlaylistSlot:
    """Ein finaler Playlist-Eintrag (Spec §91)."""

    position: int

    phase_id: str

    track_id: str

    source: str = "exploration"

    supporting_guests: list[str] = field(default_factory=list)

    recommendation_score: float = 0.0

    reasons: list[str] = field(default_factory=list)


@dataclass
class PlaylistPlan:
    """Container für die vollständig geplante (aber noch nicht auf Spotify
    aufgelöste) Playlist - Zwischenergebnis zwischen SequenceOptimizer und
    SpotifyAdapter (Spec §77: "Die fertig geplante interne Trackliste wird
    erst am Ende auf Spotify-Tracks aufgelöst")."""

    slots: list[PlaylistSlot] = field(default_factory=list)
    target_duration_ms: int = 0
    actual_duration_ms: int = 0
    run_id: str = ""
    generated_at: str = ""
    random_seed: int = 0


# --- Admin-Steuerung -----------------------------------------------------------


@dataclass
class AdminMusicSettings:
    """Admin-Steuerparameter für die Playlist-Generierung (Spec §60)."""

    playlist_duration_buffer: float = 0.08  # Spec §13: Default 8%

    party_intensity: float = 0.5  # 0 = entspannt, 1 = Eskalation
    mainstream_discovery: float = 0.7  # 0 = nur Entdeckungen, 1 = nur bekannte Hits

    guest_request_priority: float = 0.7  # 0 = mehr kuratieren, 1 = strikt priorisieren

    explicit_allowed: bool = True

    preferred_genres: set[str] = field(default_factory=set)
    discouraged_genres: set[str] = field(default_factory=set)

    banned_genres: set[str] = field(default_factory=set)

    preferred_eras: set[str] = field(default_factory=set)
    discouraged_eras: set[str] = field(default_factory=set)

    max_tracks_per_artist: int = 3  # Spec §55: MAX_TRACKS_PER_ARTIST_AUTO

    exploration_share: float = 0.10  # Spec §59

    closing_style: str = "singalong"  # singalong, chill_out, big_finish

    random_seed: int = 42


@dataclass
class AdminTrackOverride:
    """Spec §62."""

    track_id: str
    status: str = "neutral"  # must_play, preferred, neutral, avoid, banned


@dataclass
class AdminArtistOverride:
    """Spec §63."""

    artist_id: str
    status: str = "neutral"  # preferred, neutral, avoid, banned


# --- Exposure / Feedback (Spec §80/§81) ----------------------------------------


@dataclass
class RecommendationExposure:
    """Trackt, wie oft ein automatisch empfohlener Track angezeigt/übernommen
    wurde (Spec §80). Rein additiv, beeinflusst nur künftiges Scoring bzw.
    dient künftigem Learning-to-Rank (Spec §88)."""

    party_id: str

    track_id: str = ""

    source: str = "exploration"

    rank: int | None = None

    recommended_at: str = ""

    accepted: bool = False
    rejected: bool = False


@dataclass
class MusicFeedback:
    """Vorbereitung für zukünftiges Feedback-Lernen (Spec §81/§82: NUR
    tatsächlich vorhandene Daten, keine fiktiven Listening-Daten)."""

    party_id: str
    track_id: str | None = None

    feedback_type: str = "admin_moved_song"
    # admin_removed_recommendation, admin_moved_song, admin_marked_must_play,
    # guest_requested_track, admin_liked_playlist, party_playlist_regenerated

    value: float | str | bool = True

    source: str = "admin"


# --- Ergebnis-Container ---------------------------------------------------------


@dataclass
class MusicPlanningResult:
    """Rückgabe der Core-API ``plan_party_music()`` (Spec §90)."""

    target_duration_ms: int = 0

    actual_duration_ms: int = 0

    total_tracks: int = 0

    requested_tracks_selected: int = 0
    requested_tracks_total: int = 0

    guest_coverage: float = 0.0

    phases: list[MusicPhase] = field(default_factory=list)

    playlist: list[PlaylistSlot] = field(default_factory=list)

    group_profile: GroupMusicProfile = field(default_factory=GroupMusicProfile)

    unresolved_requests: list[ResolvedSongRequest] = field(default_factory=list)

    review_issues: list[str] = field(default_factory=list)

    explanations: list[str] = field(default_factory=list)

    model_version: str = "1.0"

    # Zusatzfelder für die Admin-UI (Spec §71/§72), rein additiv zur
    # Spec-Skizze: sparen der UI-Schicht eigene Nachberechnungen.
    requested_songs_total_count: int = 0
    requested_songs_fitting_count: int = 0
    unique_guests_with_requests: int = 0
    unique_guests_covered: int = 0
