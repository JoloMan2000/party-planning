"""Tests für ``equipment_engine.activity_integration`` (Phase 4) - reine
Funktionstests, mirrort ``tests/test_equipment_food_beverage_integration.py``'s
Stil."""

from __future__ import annotations

from equipment_engine.activity_integration import compute_station_activity_interest


def test_twenty_votes_at_eight_per_station_ceils_to_three():
    assert compute_station_activity_interest({"beer_pong": 20}) == {"beer_pong": 3}


def test_exactly_eight_votes_is_one_station():
    assert compute_station_activity_interest({"beer_pong": 8}) == {"beer_pong": 1}


def test_one_vote_still_rounds_up_to_one_station():
    assert compute_station_activity_interest({"beer_pong": 1}) == {"beer_pong": 1}


def test_zero_votes_is_absent_from_result():
    assert compute_station_activity_interest({"beer_pong": 0}) == {}


def test_unknown_station_id_is_ignored():
    assert compute_station_activity_interest({"karaoke": 15}) == {}


def test_empty_input_returns_empty_dict():
    assert compute_station_activity_interest({}) == {}


def test_mixed_known_and_unknown_stations():
    result = compute_station_activity_interest({"beer_pong": 16, "karaoke": 5})
    assert result == {"beer_pong": 2}
