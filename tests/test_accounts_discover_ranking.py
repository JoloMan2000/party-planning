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


# --- Build-Schritt 5: Blended Ranking -----------------------------------


def test_cold_start_score_ist_identisch_zum_alten_verhalten():
    """PFLICHT-Regressionstest (siehe Plan): ``learned_affinities=None``
    (impliziter Default) MUSS bit-identisch zum Verhalten vor Build-Schritt 5
    sein - kein User ohne gelernte Signale darf durch die Blend-Logik
    einen anderen Score bekommen als zuvor. Deckt jeden bestehenden
    Test-Case oben nochmal ab, plus explizit `learned_affinities={}`."""
    cases = [
        (_party(), _publication(), None, set(), set()),
        (_party(), _publication(event_type="club_event"), None, {"club_event"}, set()),
        (_party(), _publication(interest_tags=["techno", "outdoor"]), None, set(), {"techno", "outdoor"}),
        (_party(location="Berlin"), _publication(), UserDiscoveryPreferences(user_id="u", discovery_city="Berlin"), set(), set()),
    ]
    for party, publication, preferences, event_types, interest_tags in cases:
        without_param = discover_ranking.score_candidate(party, publication, preferences, event_types, interest_tags, now=NOW)
        with_none = discover_ranking.score_candidate(
            party, publication, preferences, event_types, interest_tags, now=NOW, learned_affinities=None
        )
        with_empty = discover_ranking.score_candidate(
            party, publication, preferences, event_types, interest_tags, now=NOW, learned_affinities={}
        )
        assert without_param == with_none == with_empty


def test_blend_learned_cold_start_gibt_explicit_fit_unveraendert():
    assert discover_ranking._blend_learned(0.7, None) == 0.7


def test_blend_learned_wenig_beobachtungen_bleibt_nah_am_prior():
    # observation_weight=0.1 << PRIOR_STRENGTH=3.0 -> kaum Einfluss.
    blended = discover_ranking._blend_learned(0.5, (1.0, 0.1))
    assert 0.5 < blended < 0.55


def test_blend_learned_viele_beobachtungen_naehert_sich_learned_fit():
    # observation_weight >> PRIOR_STRENGTH -> dominiert das gelernte Signal.
    blended = discover_ranking._blend_learned(0.5, (1.0, 1000.0))
    assert blended > 0.99


def test_blend_learned_explicit_love_protection_clamp():
    # Ein negatives gelerntes Signal darf einen hohen expliziten Fit nie
    # UNTER den expliziten Fit selbst druecken.
    blended = discover_ranking._blend_learned(0.9, (0.1, 1000.0))
    assert blended >= 0.9


def test_blend_learned_positiv_darf_ueber_explicit_fit_heben():
    blended = discover_ranking._blend_learned(0.5, (1.0, 1000.0))
    assert blended > 0.5


def test_score_candidate_mit_positivem_learned_signal_uebertrifft_cold_start():
    publication = _publication(event_type="club_event")
    cold = discover_ranking.score_candidate(_party(), publication, None, set(), set(), now=NOW)
    warm = discover_ranking.score_candidate(
        _party(), publication, None, set(), set(), now=NOW,
        learned_affinities={("event_type", "club_event"): (1.0, 10.0)},
    )
    assert warm > cold


def test_score_candidate_learned_signal_wirkt_nur_auf_passendes_attribut():
    publication = _publication(event_type="club_event", interest_tags=["techno"])
    baseline = discover_ranking.score_candidate(_party(), publication, None, set(), set(), now=NOW)
    with_unrelated_signal = discover_ranking.score_candidate(
        _party(), publication, None, set(), set(), now=NOW,
        learned_affinities={("event_type", "cultural_event"): (1.0, 10.0)},
    )
    assert baseline == with_unrelated_signal


def test_score_candidate_mehrere_interest_tags_werden_gemittelt():
    publication = _publication(interest_tags=["techno", "jazz"])
    warm = discover_ranking.score_candidate(
        _party(), publication, None, set(), set(), now=NOW,
        learned_affinities={
            ("interest_tag", "techno"): (1.0, 10.0),
            ("interest_tag", "jazz"): (0.1, 10.0),
        },
    )
    cold = discover_ranking.score_candidate(_party(), publication, None, set(), set(), now=NOW)
    # Ein starkes Plus- und ein starkes Minus-Signal mitteln sich - Ergebnis
    # bleibt nah am Cold-Start-Wert, crasht insbesondere nicht.
    assert abs(warm - cold) < 0.3


def test_rank_candidates_mit_learned_affinities_bevorzugt_gelernte_praeferenz():
    party_a = _party(id="a")
    party_b = _party(id="b")
    pub_a = _publication(id="pe-a", party_id="a", event_type="club_event")
    pub_b = _publication(id="pe-b", party_id="b", event_type="cultural_event")
    ranked = discover_ranking.rank_candidates(
        [(party_b, pub_b), (party_a, pub_a)], None, set(), set(),
        learned_affinities={("event_type", "club_event"): (1.0, 20.0)},
    )
    assert ranked[0][0].id == "a"


# --- Build-Schritt 6: Diversity + Exploration ----------------------------


def _ranked_item(id_: str, event_type: str, score: float):
    return (_party(id=id_), _publication(id=f"pe-{id_}", party_id=id_, event_type=event_type), score)


def test_apply_diversity_haelt_deckel_bei_ausgeglichenem_pool_ein():
    # 4 club + 4 jazz, gleich viele -> immer erfuellbar mit Deckel=2.
    items = []
    for i in range(4):
        items.append(_ranked_item(f"club{i}", "club_event", 0.9 - i * 0.05))
        items.append(_ranked_item(f"jazz{i}", "jazz_event", 0.85 - i * 0.05))
    result = discover_ranking._apply_diversity(items, max_consecutive=2)
    assert len(result) == len(items)
    assert {r[0].id for r in result} == {i[0].id for i in items}
    consecutive = 1
    for i in range(1, len(result)):
        consecutive = consecutive + 1 if result[i][1].event_type == result[i - 1][1].event_type else 1
        assert consecutive <= 2


def test_apply_diversity_bricht_deckel_wenn_unvermeidbar():
    # Ausschliesslich ein einziger event_type -> Deckel kann nicht eingehalten
    # werden, Funktion crasht trotzdem nicht und liefert alle Items zurueck.
    items = [_ranked_item(f"c{i}", "club_event", 1.0 - i * 0.1) for i in range(5)]
    result = discover_ranking._apply_diversity(items, max_consecutive=2)
    assert len(result) == 5
    assert [r[0].id for r in result] == [i[0].id for i in items]  # bleibt score-sortiert


def test_apply_diversity_and_exploration_liefert_hoechstens_limit_items():
    items = [_ranked_item(f"c{i}", "club_event", 1.0 - i * 0.01) for i in range(20)]
    deck = discover_ranking.apply_diversity_and_exploration(items, limit=6)
    assert len(deck) == 6


def test_apply_diversity_and_exploration_pool_kleiner_als_limit():
    items = [_ranked_item(f"c{i}", "club_event", 1.0 - i * 0.01) for i in range(3)]
    deck = discover_ranking.apply_diversity_and_exploration(items, limit=6)
    assert len(deck) == 3


def test_apply_diversity_and_exploration_reserviert_slot_ausserhalb_naivem_schnitt():
    # 10 Items desselben Typs, streng absteigend sortiert - Diversity ist
    # hier ein No-Op (kein zweiter Typ vorhanden), Exploration bleibt isoliert
    # testbar: der naive Top-6-Schnitt (Index 0-5) darf NICHT das komplette
    # Deck sein, ein Kandidat jenseits davon muss dabei sein.
    items = [_ranked_item(f"c{i}", "club_event", 1.0 - i * 0.05) for i in range(10)]
    deck = discover_ranking.apply_diversity_and_exploration(items, limit=6)
    naive_top_ids = {items[i][0].id for i in range(6)}
    deck_ids = {d[0].id for d in deck}
    assert not deck_ids.issubset(naive_top_ids)
    assert len(deck) == 6


def test_apply_diversity_and_exploration_leerer_pool():
    assert discover_ranking.apply_diversity_and_exploration([], limit=6) == []


def test_apply_diversity_and_exploration_limit_null():
    items = [_ranked_item("c0", "club_event", 1.0)]
    assert discover_ranking.apply_diversity_and_exploration(items, limit=0) == []


# --- Build-Schritt 7: Explainability -------------------------------------


def test_explain_candidate_niemals_leer():
    reason = discover_ranking.explain_candidate(_party(), _publication(), None, set(), set())
    assert reason


def test_explain_candidate_bevorzugt_expliziten_event_type_match():
    reason = discover_ranking.explain_candidate(
        _party(), _publication(event_type="club_event"), None, {"club_event"}, set()
    )
    assert "club event" in reason.lower()


def test_explain_candidate_bevorzugt_expliziten_interest_tag_match():
    reason = discover_ranking.explain_candidate(
        _party(), _publication(event_type="other", interest_tags=["techno"]), None, set(), {"techno"}
    )
    assert "techno" in reason.lower()


def test_explain_candidate_explicit_hat_vorrang_vor_learned():
    reason = discover_ranking.explain_candidate(
        _party(),
        _publication(event_type="club_event"),
        None,
        {"club_event"},
        set(),
        learned_affinities={("event_type", "club_event"): (0.99, 50.0)},
    )
    assert "club event" in reason.lower()
    assert "shown interest" not in reason.lower()  # explizite Formulierung, nicht die gelernte


def test_explain_candidate_learned_signal_ohne_explizite_praeferenz():
    reason = discover_ranking.explain_candidate(
        _party(), _publication(event_type="cultural_event"), None, set(), set(),
        learned_affinities={("event_type", "cultural_event"): (0.9, 5.0)},
    )
    assert "cultural event" in reason.lower()
    assert "shown interest" in reason.lower()


def test_explain_candidate_schwaches_learned_signal_zaehlt_nicht():
    # observation_weight < _EXPLANATION_MIN_OBSERVATION_WEIGHT -> kein
    # Learned-Grund, faellt weiter durch zum Fallback.
    reason = discover_ranking.explain_candidate(
        _party(), _publication(event_type="cultural_event"), None, set(), set(),
        learned_affinities={("event_type", "cultural_event"): (0.9, 0.1)},
    )
    assert "shown interest" not in reason.lower()


def test_explain_candidate_negatives_learned_signal_zaehlt_nicht():
    reason = discover_ranking.explain_candidate(
        _party(), _publication(event_type="cultural_event"), None, set(), set(),
        learned_affinities={("event_type", "cultural_event"): (0.1, 5.0)},
    )
    assert "shown interest" not in reason.lower()


def test_explain_candidate_timing_fallback():
    saturday = NOW + timedelta(days=(5 - NOW.weekday()) % 7)
    party = _party(starts_at=saturday)
    prefs = UserDiscoveryPreferences(user_id="u", preferred_days=["saturday"])
    reason = discover_ranking.explain_candidate(party, _publication(event_type="other"), prefs, set(), set())
    assert "day" in reason.lower()


def test_explain_candidate_city_fallback():
    party = _party(location="Berlin")
    prefs = UserDiscoveryPreferences(user_id="u", discovery_city="Berlin")
    reason = discover_ranking.explain_candidate(party, _publication(event_type="other"), prefs, set(), set())
    assert "berlin" in reason.lower()


def test_explain_candidate_generischer_fallback_ohne_jegliches_signal():
    reason = discover_ranking.explain_candidate(_party(), _publication(event_type="other"), None, set(), set())
    assert reason == "Recently published near you"
