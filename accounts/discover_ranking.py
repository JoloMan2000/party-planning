"""Regelbasiertes Ranking fürs Discover-Deck (MVP + Build-Schritt 5 Blended
Ranking - siehe ``discover_nearby_event_engine_full_spec.txt`` §25-41).

Framework-frei, keine sqlite3-/FastAPI-Importe (mirroring
``party_engine``/``music_engine``-Konvention) - reine Scoring-Funktionen,
unabhängig testbar ohne DB. Gelernte Affinitäten (``accounts/discover_learning.py``)
werden deshalb NICHT hier geladen, sondern von ``discover_storage.get_discover_deck``
bereits decayed übergeben (bulk-gefetcht via
``discover_learning.get_learned_affinities_for_user``).

Jeder Score-Term liefert bei fehlendem Signal einen NEUTRALEN Wert (0.5),
nie 0.0 - ein neuer User ohne gesetzte Preferences bekommt dadurch ein
unverzerrtes Deck statt eines leeren/zufällig wirkenden.

Build-Schritt 5 (Bayesian-Shrinkage-Blend, siehe ``_blend_learned``): der
explizite Fit bleibt der PRIOR, gelernte Affinität ergänzt ihn nur, mit
wachsendem Gewicht je mehr Beobachtungen vorliegen (``observation_weight``).
KEIN neuer Gewichts-Term in ``score_candidate`` nötig - der Blend ersetzt den
rohen Explicit-Fit VOR der bestehenden Gewichtung durch
``WEIGHT_EVENT_TYPE_FIT``/``WEIGHT_INTEREST_TAG_FIT``, dadurch bleiben alle
fünf Gewichte unverändert UND der Cold-Start-Fall (keine gelernten Signale)
ist durch Konstruktion IDENTISCH zum Verhalten vor diesem Build-Schritt -
siehe ``tests/test_accounts_discover_ranking.py::test_cold_start_score_ist_identisch_zum_alten_verhalten``."""

from __future__ import annotations

from datetime import datetime, timezone

from accounts.domain import Party, PublicEvent, UserDiscoveryPreferences

WEIGHT_EVENT_TYPE_FIT = 0.45
WEIGHT_INTEREST_TAG_FIT = 0.25
WEIGHT_TIMING_FIT = 0.15
WEIGHT_CITY_FIT = 0.10
WEIGHT_RECENCY_FIT = 0.05

_NEUTRAL = 0.5
_MATCH = 1.0
_MISMATCH = 0.2

# Bayesian-Shrinkage-Prior-Staerke (Build-Schritt 5) - in denselben Einheiten
# wie ``observation_count``/``observation_weight`` aus
# ``accounts/discover_learning.py``: PRIOR_STRENGTH=3.0 bedeutet, ein
# gelerntes Signal braucht ~3 Beobachtungen, um dem expliziten Prior
# gleichwertig zu werden. Je mehr Beobachtungen darueber hinaus, desto mehr
# Gewicht gegenueber dem Prior.
PRIOR_STRENGTH = 3.0

# Typalias nur zur Lesbarkeit: Key = (attribute_category, attribute_value),
# Value = (decayed_fit, observation_weight) - exakt die Rueckgabeform von
# ``discover_learning.get_learned_affinities_for_user``.
LearnedAffinityMap = dict[tuple[str, str], tuple[float, float]]


def _blend_learned(explicit_fit: float, learned: tuple[float, float] | None) -> float:
    """Bayesian-Shrinkage-Blend: gelernte Affinitaet ERGAENZT den expliziten
    Fit, ueberschreibt ihn nie vollstaendig. ``learned=None`` (Cold-Start -
    noch keine Beobachtung fuer dieses Attribut) gibt den expliziten Fit
    UNVERAENDERT zurueck - das ist der Mechanismus, der Build-Schritt 5
    rueckwaertskompatibel zum MVP-Verhalten macht.

    Explicit-Love-Protection-Clamp (``max(effective, explicit_fit)``):
    gelernte Signale duerfen einen Score niemals UNTER den expliziten Fit
    druecken - eine explizite Praeferenz ist ein Boden, keine Decke. Positiv
    duerfen gelernte Signale den Score dagegen sehr wohl ueber den
    expliziten Fit heben (z.B. ein Attribut, das der User nie explizit
    ausgewaehlt hat, aber wiederholt positiv beswiped)."""
    if learned is None:
        return explicit_fit
    learned_fit, observation_weight = learned
    effective = (PRIOR_STRENGTH * explicit_fit + observation_weight * learned_fit) / (
        PRIOR_STRENGTH + observation_weight
    )
    return max(effective, explicit_fit)

# Stunden-Buckets fürs Timing-Fit. ANNAHME: es gibt aktuell keinen
# ``discovery_catalogs.py``-Eintrag für Dayparts - diese vier IDs sind eine
# lokale Konvention dieses Moduls (siehe Plan, Deferred-Abschnitt).
_DAYPART_HOURS = {
    "morning": range(6, 12),
    "afternoon": range(12, 17),
    "evening": range(17, 22),
    # 22-6 Uhr (wrap-around) -> "late_night", per Sonderfall unten behandelt
}


def _daypart_for_hour(hour: int) -> str:
    for daypart, hours in _DAYPART_HOURS.items():
        if hour in hours:
            return daypart
    return "late_night"


def _event_type_fit(publication: PublicEvent, event_type_interests: set[str]) -> float:
    if not event_type_interests:
        return _NEUTRAL
    return _MATCH if publication.event_type in event_type_interests else _MISMATCH


def _interest_tag_fit(publication: PublicEvent, interest_tag_interests: set[str]) -> float:
    if not interest_tag_interests or not publication.interest_tags:
        return _NEUTRAL
    overlap = len(interest_tag_interests.intersection(publication.interest_tags))
    return 0.2 + 0.8 * (overlap / len(interest_tag_interests))


def _timing_fit(party: Party, preferences: UserDiscoveryPreferences | None) -> float:
    if party.starts_at is None:
        return _NEUTRAL
    if preferences is None:
        return _NEUTRAL

    if not preferences.preferred_days:
        day_score = _NEUTRAL
    else:
        weekday_name = party.starts_at.strftime("%A").lower()
        day_score = _MATCH if weekday_name in preferences.preferred_days else _MISMATCH

    if not preferences.preferred_dayparts:
        daypart_score = _NEUTRAL
    else:
        daypart = _daypart_for_hour(party.starts_at.hour)
        daypart_score = _MATCH if daypart in preferences.preferred_dayparts else _MISMATCH

    return (day_score + daypart_score) / 2


def _city_fit(party: Party, preferences: UserDiscoveryPreferences | None) -> float:
    """Bewusst NUR ein weiches Signal, KEIN Hard-Filter (siehe Plan,
    Deferred-Abschnitt: echtes Geocoding/Radius ist nicht Teil des MVP)."""
    if preferences is None or not preferences.discovery_city or not party.location:
        return _NEUTRAL
    city = preferences.discovery_city.lower()
    location = party.location.lower()
    return _MATCH if city in location or location in city else _MISMATCH


def _recency_fit(publication: PublicEvent, now: datetime) -> float:
    published_at = publication.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - published_at).days)
    return 1.0 / (1.0 + age_days)


def score_candidate(
    party: Party,
    publication: PublicEvent,
    preferences: UserDiscoveryPreferences | None,
    event_type_interests: set[str],
    interest_tag_interests: set[str],
    now: datetime | None = None,
    learned_affinities: LearnedAffinityMap | None = None,
) -> float:
    """Gewichtete Summe der einzelnen Fit-Terme, Ergebnis in (0, 1].

    ``learned_affinities=None`` (Default) verhaelt sich exakt wie vor
    Build-Schritt 5 - jeder Aufrufer, der den neuen Parameter nicht kennt,
    bekommt unveraendertes Verhalten (siehe ``_blend_learned``)."""
    now = now or datetime.now(timezone.utc)
    learned_affinities = learned_affinities or {}

    event_type_fit = _blend_learned(
        _event_type_fit(publication, event_type_interests),
        learned_affinities.get(("event_type", publication.event_type)) if publication.event_type else None,
    )
    interest_tag_fit = _interest_tag_fit(publication, interest_tag_interests)
    if publication.interest_tags:
        tag_learned = [
            learned_affinities[("interest_tag", tag)]
            for tag in publication.interest_tags
            if ("interest_tag", tag) in learned_affinities
        ]
        if tag_learned:
            # Mehrere Tags koennen je eigene gelernte Affinitaet haben -
            # Durchschnitt der (fit, weight)-Paare vor dem Blend, damit EIN
            # Blend-Aufruf ausreicht statt N unabhaengiger Ueberschreibungen.
            avg_fit = sum(fit for fit, _ in tag_learned) / len(tag_learned)
            avg_weight = sum(weight for _, weight in tag_learned) / len(tag_learned)
            interest_tag_fit = _blend_learned(interest_tag_fit, (avg_fit, avg_weight))

    return (
        WEIGHT_EVENT_TYPE_FIT * event_type_fit
        + WEIGHT_INTEREST_TAG_FIT * interest_tag_fit
        + WEIGHT_TIMING_FIT * _timing_fit(party, preferences)
        + WEIGHT_CITY_FIT * _city_fit(party, preferences)
        + WEIGHT_RECENCY_FIT * _recency_fit(publication, now)
    )


def rank_candidates(
    candidates: list[tuple[Party, PublicEvent]],
    preferences: UserDiscoveryPreferences | None,
    event_type_interests: set[str],
    interest_tag_interests: set[str],
    learned_affinities: LearnedAffinityMap | None = None,
) -> list[tuple[Party, PublicEvent, float]]:
    """Sortiert nach Score absteigend, Tie-Break: neuer veröffentlicht
    zuerst. KEIN Diversity-/Exploration-Bucketing (siehe Deferred).

    ``personalized_recommendations_enabled=False`` (Bypass, siehe
    ``discover_storage.get_discover_deck``) wird NICHT hier geprueft -
    der Caller uebergibt in diesem Fall einfach ``learned_affinities=None``,
    identisch zum Cold-Start-Pfad. Kein Sonderfall in dieser Funktion noetig."""
    now = datetime.now(timezone.utc)
    scored = [
        (
            party,
            publication,
            score_candidate(
                party, publication, preferences, event_type_interests, interest_tag_interests, now, learned_affinities
            ),
        )
        for party, publication in candidates
    ]
    scored.sort(key=lambda item: (item[2], item[1].published_at), reverse=True)
    return scored


# Build-Schritt 6: Diversity + Exploration Post-Pass.
# Nach hoechstens 2 Karten desselben event_type wird eine andere
# Kategorie bevorzugt (weich - siehe _apply_diversity, kein Hard-Filter).
DIVERSITY_MAX_CONSECUTIVE_SAME_EVENT_TYPE = 2
# Jeder 5. Deck-Slot ist ein Exploration-Slot (siehe apply_diversity_and_exploration).
EXPLORATION_SLOT_EVERY_N = 5


def _apply_diversity(
    items: list[tuple[Party, PublicEvent, float]], max_consecutive: int
) -> list[tuple[Party, PublicEvent, float]]:
    """Greedy Re-Sortierung: waehlt bei jedem Schritt den bestplatzierten
    verbleibenden Kandidaten, der den ``max_consecutive``-gleicher-event_type-
    Deckel nicht verletzt. Ist KEIN Kandidat verfuegbar, der den Deckel
    einhaelt (z.B. Deck besteht komplett aus einem event_type), wird der
    Deckel gebrochen statt Kandidaten wegzulassen - Diversity ist ein
    weiches Reordering-Signal, nie ein Filter (mirrort die Konvention aller
    Fit-Terme oben: neutral/soft statt hart, wo kein Hard-Filter noetig ist)."""
    remaining = sorted(items, key=lambda item: item[2], reverse=True)
    result: list[tuple[Party, PublicEvent, float]] = []
    last_event_type: str | None = None
    consecutive = 0
    while remaining:
        chosen_index = 0
        for i, (_party, publication, _score) in enumerate(remaining):
            if publication.event_type != last_event_type or consecutive < max_consecutive:
                chosen_index = i
                break
        chosen = remaining.pop(chosen_index)
        if chosen[1].event_type == last_event_type:
            consecutive += 1
        else:
            consecutive = 1
            last_event_type = chosen[1].event_type
        result.append(chosen)
    return result


def apply_diversity_and_exploration(
    ranked: list[tuple[Party, PublicEvent, float]], limit: int
) -> list[tuple[Party, PublicEvent, float]]:
    """Post-Pass NACH ``rank_candidates`` (das bereits den vollstaendigen,
    unbeschraenkten Kandidaten-Pool sortiert zurueckgibt) - ersetzt das
    vormals nackte ``ranked[:limit]`` in ``discover_storage.get_discover_deck``.

    Exploration (Spec-Prinzip: kein reiner Filterbubble-Feedback-Loop):
    reserviert bis zu ``limit // EXPLORATION_SLOT_EVERY_N`` Plaetze fuer die
    bestplatzierten Kandidaten AUSSERHALB des naiven Top-``limit``-Schnitts -
    ohne das wuerden diese Kandidaten NIE gezeigt und dadurch NIE ein
    Lern-Signal erzeugen koennen (siehe Build-Schritt 4), selbst wenn ihr
    tatsaechlicher Fit gut waere. Deterministisch (kein RNG) - nimmt immer
    die bestplatzierten Explore-Kandidaten, keine Zufallsauswahl, bleibt
    damit reproduzierbar testbar (mirrort den regelbasierten Charakter
    dieses gesamten Moduls).

    Diversity: die finale Reihenfolge (Exploit + Exploration zusammen)
    durchlaeuft danach ``_apply_diversity``, damit weder der reine
    Top-N-Schnitt noch die Exploration-Slots isoliert lange Ketten
    desselben event_type erzeugen."""
    if limit <= 0 or not ranked:
        return []

    exploit_pool = ranked[:limit]
    exploration_pool = ranked[limit:]

    num_exploration_slots = min(len(exploration_pool), max(1, limit // EXPLORATION_SLOT_EVERY_N)) if exploration_pool else 0
    exploration_slots = exploration_pool[:num_exploration_slots]
    exploit_slots = exploit_pool[: limit - num_exploration_slots] if num_exploration_slots else exploit_pool

    combined = exploit_slots + exploration_slots
    return _apply_diversity(combined, DIVERSITY_MAX_CONSECUTIVE_SAME_EVENT_TYPE)


# Build-Schritt 7: Explainability. Ein Beobachtungs-Schwellwert, ab dem eine
# gelernte Affinität als "genug Signal fuer eine Erklaerung" gilt - bewusst
# STRENGER als der reine Blend-Einfluss (der schon ab jeder Beobachtung
# > 0 wirkt), damit "Because you've shown interest in..." nicht nach einem
# einzelnen zweideutigen Swipe angezeigt wird.
_EXPLANATION_MIN_OBSERVATION_WEIGHT = 1.0


def explain_candidate(
    party: Party,
    publication: PublicEvent,
    preferences: UserDiscoveryPreferences | None,
    event_type_interests: set[str],
    interest_tag_interests: set[str],
    learned_affinities: LearnedAffinityMap | None = None,
) -> str:
    """Liefert GENAU EINEN kurzen, für den User verständlichen Grund - keine
    versteckte Black Box (Spec-Prinzip §158 des Social-Graph-Specs gilt
    sinngemäß auch hier). Prioritätsreihenfolge, stärkstes Signal zuerst:
    explizite Übereinstimmung (vom User selbst gesetzt) > gelernte Affinität
    (aus Verhalten abgeleitet, siehe Build-Schritt 4) > Timing/Ort (weiche
    Preferences) > generischer Recency-Fallback (NIE 'kein Grund' - jede
    Karte bekommt eine Erklärung).

    Bewusst getrennt von ``score_candidate`` statt in dessen Rückgabewert
    verwoben - Scoring bleibt eine reine Zahl, Explainability eine separate,
    unabhängig testbare Projektion derselben Eingaben (mirrort, wie
    ``get_discover_deck`` Scoring und Distanz-Berechnung bereits getrennt
    hält)."""
    learned_affinities = learned_affinities or {}

    if publication.event_type and publication.event_type in event_type_interests:
        return f"Matches your interest in {publication.event_type.replace('_', ' ')}"

    matching_tags = interest_tag_interests.intersection(publication.interest_tags)
    if matching_tags:
        return f"Matches your interest in {sorted(matching_tags)[0].replace('_', ' ')}"

    if publication.event_type:
        learned = learned_affinities.get(("event_type", publication.event_type))
        if (
            learned is not None
            and learned[0] > _NEUTRAL
            and learned[1] >= _EXPLANATION_MIN_OBSERVATION_WEIGHT
        ):
            return f"Because you've shown interest in {publication.event_type.replace('_', ' ')} events"

    positive_tag_signals = [
        (tag, learned_affinities[("interest_tag", tag)])
        for tag in publication.interest_tags
        if ("interest_tag", tag) in learned_affinities
        and learned_affinities[("interest_tag", tag)][0] > _NEUTRAL
        and learned_affinities[("interest_tag", tag)][1] >= _EXPLANATION_MIN_OBSERVATION_WEIGHT
    ]
    if positive_tag_signals:
        best_tag = max(positive_tag_signals, key=lambda item: item[1][0])[0]
        return f"Because you've shown interest in {best_tag.replace('_', ' ')} events"

    if preferences is not None and party.starts_at is not None:
        if preferences.preferred_days and party.starts_at.strftime("%A").lower() in preferences.preferred_days:
            return "Happening on a day you usually prefer"
        if preferences.preferred_dayparts and _daypart_for_hour(party.starts_at.hour) in preferences.preferred_dayparts:
            return "Happening at a time you usually prefer"

    if preferences is not None and preferences.discovery_city and party.location:
        city = preferences.discovery_city.lower()
        location = party.location.lower()
        if city in location or location in city:
            return f"Near {party.location}"

    return "Recently published near you"


if __name__ == "__main__":
    from datetime import timedelta

    from accounts.domain import DiscoverAction  # noqa: F401  (Re-Export-Sanity-Check)

    now = datetime.now(timezone.utc)
    party_a = Party(id="a", host_user_id="host", name="Techno Night", starts_at=now + timedelta(days=1), location="Berlin")
    party_b = Party(id="b", host_user_id="host", name="Jazz Brunch", starts_at=now + timedelta(days=2), location="Munich")
    pub_a = PublicEvent(id="pe-a", party_id="a", event_type="club_event", interest_tags=["techno"], published_at=now)
    pub_b = PublicEvent(id="pe-b", party_id="b", event_type="cultural_event", interest_tags=["jazz"], published_at=now)

    # Cold Start (keine Preferences) - darf nicht crashen, alle Scores neutral-ish.
    cold_ranked = rank_candidates([(party_a, pub_a), (party_b, pub_b)], None, set(), set())
    assert len(cold_ranked) == 2
    assert all(0.0 < score <= 1.0 for _, _, score in cold_ranked)

    # Mit passenden Preferences soll der Club-Event-Fan Party A vorne sehen.
    ranked = rank_candidates([(party_a, pub_a), (party_b, pub_b)], None, {"club_event"}, {"techno"})
    assert ranked[0][0].id == "a"

    prefs = UserDiscoveryPreferences(user_id="user-1", discovery_city="Berlin")
    city_ranked = rank_candidates([(party_a, pub_a), (party_b, pub_b)], prefs, set(), set())
    assert city_ranked[0][0].id == "a"

    # Build-Schritt 6: Diversity + Exploration - Sanity-Check (die
    # strikte Deckel-Einhaltung wird in tests/test_accounts_discover_ranking.py
    # an einem gezielt konstruierten, immer erfuellbaren Szenario geprueft;
    # der Deckel ist bewusst weich und kann bei zu wenig Vielfalt im Pool
    # nicht immer eingehalten werden, siehe _apply_diversity-Doku).
    many_club = [
        (
            Party(id=f"c{i}", host_user_id="host", name=f"Club {i}", starts_at=now + timedelta(days=1), location="Berlin"),
            PublicEvent(id=f"pe-c{i}", party_id=f"c{i}", event_type="club_event", published_at=now - timedelta(hours=i)),
        )
        for i in range(8)
    ]
    other_types = [
        (
            Party(id=f"o{i}", host_user_id="host", name=f"Other {i}", starts_at=now + timedelta(days=1), location="Berlin"),
            PublicEvent(id=f"pe-o{i}", party_id=f"o{i}", event_type=f"other_type_{i}", published_at=now - timedelta(hours=i)),
        )
        for i in range(4)
    ]
    ranked_mixed = rank_candidates(many_club + other_types, None, {"club_event"}, set())
    deck = apply_diversity_and_exploration(ranked_mixed, limit=6)
    assert len(deck) == 6

    # Exploration: mit einem Pool groesser als limit muss mindestens ein
    # Kandidat AUSSERHALB des naiven Top-limit-Schnitts im Deck landen.
    naive_top_ids = {item[0].id for item in ranked_mixed[:6]}
    deck_ids = {item[0].id for item in deck}
    assert not deck_ids.issubset(naive_top_ids)

    # Leerer Pool / limit=0 -> leere Liste, kein Crash.
    assert apply_diversity_and_exploration([], limit=6) == []
    assert apply_diversity_and_exploration(ranked_mixed, limit=0) == []

    # Build-Schritt 7: Explainability - immer ein Grund, nie leer.
    explicit_reason = explain_candidate(party_a, pub_a, None, {"club_event"}, set())
    assert "club event" in explicit_reason.lower()

    learned_reason = explain_candidate(
        party_b, pub_b, None, set(), set(), learned_affinities={("event_type", "cultural_event"): (0.9, 5.0)}
    )
    assert "cultural event" in learned_reason.lower()

    fallback_reason = explain_candidate(party_a, pub_a, None, set(), set())
    assert fallback_reason  # nie leer

    print("accounts/discover_ranking.py sanity check OK.")
