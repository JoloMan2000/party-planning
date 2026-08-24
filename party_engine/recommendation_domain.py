"""
Recommendation-Domänenmodell (Tag-/Occasion-/Scoring-Datenstrukturen).
========================================================================

Ergänzt party_engine/domain.py um ein rein additives Empfehlungsmodell (siehe
Spezifikations-Erweiterung "VOLLSTÄNDIGES TAG- UND OCCASION-MAPPING", volltext
in der Claude-Code-Memory unter recommendation_engine_full_spec.txt).

Zentrale Regeln (§78/§79):
    Eine Empfehlung erzeugt NIEMALS IngredientDemand. Nur eine tatsächliche
    Gast-Auswahl (Preference) durchläuft die Demand-Pipeline in engine.py.
    "Admin pinned" bedeutet "prominent anbieten", nicht "automatisch kaufen".

Dieses Modul enthält NUR Datenstrukturen. Ableitung/Scoring-Logik lebt in
recommendation_tagging.py (Ableitung) und recommendation.py (Scoring/
Strategien). Occasion-Profile werden aus catalog/occasions/*.json geladen
(siehe occasions.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecommendationMetadata:
    """Empfehlungs-Metadaten eines CatalogItem (§2). Werte liegen in [0.0, 1.0],
    sofern nicht anders angegeben. Alle Felder haben neutrale 0.5-Defaults,
    sodass ein Item ohne explizite Kuratierung trotzdem ein vollständiges,
    sinnvolles Objekt besitzt (siehe derive_recommendation_metadata in
    recommendation_tagging.py)."""

    tags: set[str] = field(default_factory=set)

    # Explizite Ausnahmen für besonders charakteristische Kombinationen (§1).
    # Key = occasion_id, Value = additiver Score-Bonus/Malus (kann negativ sein).
    occasion_affinity_overrides: dict[str, float] = field(default_factory=dict)

    popularity_prior: float = 0.5
    crowd_pleaser_score: float = 0.5

    novelty_score: float = 0.5
    premium_score: float = 0.5

    prep_complexity: float = 0.5
    service_complexity: float = 0.5
    purchase_complexity: float = 0.5

    batchability: float = 0.5
    shareability: float = 0.5
    portability: float = 0.5
    messiness: float = 0.5

    indoor_score: float = 0.5
    outdoor_score: float = 0.5

    daytime_score: float = 0.5
    evening_score: float = 0.5
    late_night_score: float = 0.5

    spring_score: float = 0.5
    summer_score: float = 0.5
    autumn_score: float = 0.5
    winter_score: float = 0.5

    small_group_score: float = 0.5
    large_group_score: float = 0.5

    dietary_coverage: float = 0.5

    recommendation_enabled: bool = True

    # Versionierung (§84) — erlaubt spätere Nachvollziehbarkeit historischer
    # Partys, falls das Scoring-Modell sich weiterentwickelt.
    recommendation_model_version: str = "1.0"


@dataclass
class OccasionProfile:
    """Ein Anlass-Profil (§8-29). Definiert AUSSCHLIESSLICH Tag-Präferenzen und
    Kontext — niemals konkrete Produktlisten (Architekturgrundsatz §85)."""

    id: str
    label_de: str
    label_en: str

    preferred_tags: dict[str, float] = field(default_factory=dict)
    discouraged_tags: dict[str, float] = field(default_factory=dict)

    # Nur für den Admin-Sortiment-Bauassistenten relevant (§8 Beispiel), optional.
    admin_food_slots: dict[str, int] = field(default_factory=dict)
    admin_beverage_slots: dict[str, int] = field(default_factory=dict)

    # Fallback-Vererbung für unbekannte/künftige Anlässe (§68), z.B.
    # "beach_birthday" -> inherits_from=["birthday", "summer_party", "casual_get_together"].
    inherits_from: list[str] = field(default_factory=list)

    profile_version: str = "1.0"


DEFAULT_OCCASION_ID = "casual_get_together"


@dataclass
class RecommendationContext:
    """Kontext-Modifikatoren, unabhängig vom Occasion-Profil (§51/52/69).

    Hinweis: Nicht zu verwechseln mit ``party_context.domain.PartyContext``
    (der zentralen, admin-erfassten Party-Rahmendaten). Dieser Typ hier ist
    bewusst schlank und wird intern von ``score_item_for_occasion()``
    konsumiert; die reichhaltigen, saison-/location-/infrastruktur-bewussten
    Signale kommen künftig zusätzlich über eine separate ContextScore-Schicht
    aus dem neuen ``party_context`` Package (§78 der Party-Context-Engine-Spec)."""

    season: str | None = None  # spring, summer, autumn, winter
    hour_of_day: int | None = None  # 0-23, steuert Tageszeit-Boosts
    guest_count: int | None = None

    # Primärer Anlass zuerst, optionale Sekundär-Anlässe danach (§69).
    occasion_ids: list[str] = field(default_factory=list)


@dataclass
class GroupSignal:
    """Adaptives Gruppen-Feedback für ein einzelnes Item (§62/63)."""

    item_id: str
    supporting_guests: int = 0
    eligible_response_count: int = 0
    shown_count: int = 0
    selected_count: int = 0


@dataclass
class RecommendationExposure:
    """Trackt, wie oft ein Item angezeigt/gewählt wurde (§63). Rein additiv,
    beeinflusst nur zukünftiges Scoring, niemals Demand."""

    item_id: str
    occasion_id: str = ""
    shown_count: int = 0
    selected_count: int = 0

    def selection_rate(self) -> float | None:
        if self.shown_count <= 0:
            return None
        return self.selected_count / self.shown_count


@dataclass
class RecommendationScore:
    """Erklärbares Score-Ergebnis für ein Item in einem Occasion-/Party-Kontext
    (§82/83). `reasons` sind kurze, für Admin/Gast lesbare Texte."""

    item_id: str
    total_score: float = 0.0

    tag_match_score: float = 0.0
    category_score: float = 0.0
    context_score: float = 0.0
    popularity_score: float = 0.0
    crowd_pleaser_score: float = 0.0
    operational_score: float = 0.0
    dietary_score: float = 0.0
    group_score: float = 0.0
    admin_score: float = 0.0

    # §78 (Party-Context-Engine-Spec): eigene, additive Schicht - NICHT in
    # die Basisformel/``context_score`` (Saison/Zeit/Gruppe aus
    # ``RecommendationContext``) hineingemischt. 0.0, solange kein
    # ``derived_context`` an ``score_item_for_occasion`` übergeben wird
    # (Rückwärtskompatibilität).
    context_fit_score: float = 0.0

    penalties: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    is_signature: bool = False
