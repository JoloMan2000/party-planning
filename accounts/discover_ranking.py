"""Regelbasiertes Ranking fürs Discover-Deck (MVP - siehe
``discover_nearby_event_engine_full_spec.txt`` §25-41 für das später
geplante, hier bewusst NICHT gebaute Learned-Ranking).

Framework-frei, keine sqlite3-/FastAPI-Importe (mirroring
``party_engine``/``music_engine``-Konvention) - reine Scoring-Funktionen,
unabhängig testbar ohne DB.

Jeder Score-Term liefert bei fehlendem Signal einen NEUTRALEN Wert (0.5),
nie 0.0 - ein neuer User ohne gesetzte Preferences bekommt dadurch ein
unverzerrtes Deck statt eines leeren/zufällig wirkenden."""

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
) -> float:
    """Gewichtete Summe der einzelnen Fit-Terme, Ergebnis in (0, 1]."""
    now = now or datetime.now(timezone.utc)
    return (
        WEIGHT_EVENT_TYPE_FIT * _event_type_fit(publication, event_type_interests)
        + WEIGHT_INTEREST_TAG_FIT * _interest_tag_fit(publication, interest_tag_interests)
        + WEIGHT_TIMING_FIT * _timing_fit(party, preferences)
        + WEIGHT_CITY_FIT * _city_fit(party, preferences)
        + WEIGHT_RECENCY_FIT * _recency_fit(publication, now)
    )


def rank_candidates(
    candidates: list[tuple[Party, PublicEvent]],
    preferences: UserDiscoveryPreferences | None,
    event_type_interests: set[str],
    interest_tag_interests: set[str],
) -> list[tuple[Party, PublicEvent, float]]:
    """Sortiert nach Score absteigend, Tie-Break: neuer veröffentlicht
    zuerst. KEIN Diversity-/Exploration-Bucketing (siehe Deferred)."""
    now = datetime.now(timezone.utc)
    scored = [
        (party, publication, score_candidate(party, publication, preferences, event_type_interests, interest_tag_interests, now))
        for party, publication in candidates
    ]
    scored.sort(key=lambda item: (item[2], item[1].published_at), reverse=True)
    return scored


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

    print("accounts/discover_ranking.py sanity check OK.")
