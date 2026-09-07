"""Pytest-Unit-Tests für ``accounts/discover_ranking.py`` (regelbasiertes
Discover-Scoring, MVP). Framework-frei/kein DB-Zugriff - ergänzt den
``__main__``-Selbsttest im Modul selbst."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import accounts.discover_ranking as discover_ranking
from accounts.domain import Party, PublicEvent, UserDiscoveryPreferences

NOW = datetime.now(timezone.utc)


def _party(**kwargs) -> Party:
    defaults = dict(id="p", host_user_id="host", name="Party", starts_at=NOW + timedelta(days=1), location="Berlin")
    defaults.update(kwargs)
    return Party(**defaults)


def _publication(**kwargs) -> PublicEvent:
    defaults = dict(id="pe", party_id="p", event_type="club_event", interest_tags=["techno"], published_at=NOW)
    defaults.update(kwargs)
    return PublicEvent(**defaults)


def test_score_candidate_cold_start_bleibt_neutral_und_stuerzt_nicht_ab():
    score = discover_ranking.score_candidate(_party(), _publication(), None, set(), set(), now=NOW)
    assert 0.0 < score <= 1.0


def test_score_candidate_ohne_starts_at_bleibt_neutral_bei_timing():
    party = _party(starts_at=None)
    score = discover_ranking.score_candidate(party, _publication(), None, set(), set(), now=NOW)
    assert 0.0 < score <= 1.0


def test_event_type_match_erhoeht_score_gegenueber_mismatch():
    matching = discover_ranking.score_candidate(
        _party(), _publication(event_type="club_event"), None, {"club_event"}, set(), now=NOW
    )
    mismatching = discover_ranking.score_candidate(
        _party(), _publication(event_type="cultural_event"), None, {"club_event"}, set(), now=NOW
    )
    assert matching > mismatching


def test_interest_tag_overlap_erhoeht_score():
    full_overlap = discover_ranking.score_candidate(
        _party(), _publication(interest_tags=["techno", "outdoor"]), None, set(), {"techno", "outdoor"}, now=NOW
    )
    no_overlap = discover_ranking.score_candidate(
        _party(), _publication(interest_tags=["jazz"]), None, set(), {"techno", "outdoor"}, now=NOW
    )
    assert full_overlap > no_overlap


def test_timing_fit_bevorzugt_passenden_wochentag():
    saturday = NOW + timedelta(days=(5 - NOW.weekday()) % 7)
    party = _party(starts_at=saturday)
    prefs = UserDiscoveryPreferences(user_id="u", preferred_days=["saturday"])
    other_prefs = UserDiscoveryPreferences(user_id="u", preferred_days=["monday"])
    matching = discover_ranking.score_candidate(party, _publication(), prefs, set(), set(), now=NOW)
    mismatching = discover_ranking.score_candidate(party, _publication(), other_prefs, set(), set(), now=NOW)
    assert matching > mismatching


def test_city_fit_soft_match_erhoeht_score():
    party = _party(location="Berlin")
    prefs = UserDiscoveryPreferences(user_id="u", discovery_city="Berlin")
    other_prefs = UserDiscoveryPreferences(user_id="u", discovery_city="Munich")
    matching = discover_ranking.score_candidate(party, _publication(), prefs, set(), set(), now=NOW)
    mismatching = discover_ranking.score_candidate(party, _publication(), other_prefs, set(), set(), now=NOW)
    assert matching > mismatching


def test_recency_fit_bevorzugt_neuere_veroeffentlichung():
    fresh = discover_ranking.score_candidate(_party(), _publication(published_at=NOW), None, set(), set(), now=NOW)
    old = discover_ranking.score_candidate(
        _party(), _publication(published_at=NOW - timedelta(days=30)), None, set(), set(), now=NOW
    )
    assert fresh > old


def test_rank_candidates_sortiert_absteigend_nach_score():
    party_a = _party(id="a")
    party_b = _party(id="b")
    pub_a = _publication(id="pe-a", party_id="a", event_type="club_event")
    pub_b = _publication(id="pe-b", party_id="b", event_type="cultural_event")
    ranked = discover_ranking.rank_candidates([(party_a, pub_a), (party_b, pub_b)], None, {"club_event"}, set())
    assert ranked[0][0].id == "a"
    assert ranked[0][2] >= ranked[1][2]
