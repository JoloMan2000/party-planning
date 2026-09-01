"""Äquivalenz-Test: die Shopping-List-API muss exakt dasselbe Ergebnis liefern
wie ein direkter Aufruf von ``compute_party_demand`` mit denselben Eingaben
(Phase-1-Plan Schritt 7) - die API darf die zugrundeliegende Berechnung nicht
verändern."""

from __future__ import annotations

import event_theme
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from backend.app.core.dataclass_json import to_jsonable
from party_engine.domain import PartyConfig
from party_engine.engine import compute_party_demand
from party_engine.legacy_adapter import guest_response_from_row


def _seed_responses(db_path):
    response_storage.save_response(
        db_path,
        name="Anna",
        start_time="18:30",
        drinks=["beer_pils"],
        drinks_freetext="",
        food=["pizza_margherita"],
        food_freetext="",
        songs=[],
    )
    response_storage.save_response(
        db_path,
        name="Ben",
        start_time="19:00",
        drinks=["cola"],
        drinks_freetext="",
        food=["pizza_margherita"],
        food_freetext="",
        songs=[],
    )


def test_shopping_list_api_entspricht_direktem_compute_party_demand(api_client, admin_headers, catalog):
    _seed_responses(api_client.db_path)

    resp = api_client.post("/api/v1/admin/shopping-list", headers=admin_headers)
    assert resp.status_code == 200
    api_result = resp.json()

    settings = event_theme.get_party_settings(api_client.db_path)
    rows = response_storage.load_responses(api_client.db_path)
    guest_responses = [guest_response_from_row(row, catalog) for row in rows]
    derived_context = context_orchestration.get_derived_party_context(api_client.db_path, settings, len(rows))
    expected = to_jsonable(compute_party_demand(catalog, guest_responses, PartyConfig(), derived_context=derived_context))

    # Router reichert jede Zutat zusätzlich um `family` an (siehe
    # admin_shopping_list.py::compute_shopping_list) - das ist der einzige
    # erlaubte Unterschied zum rohen compute_party_demand()-Ergebnis.
    api_ingredient_demand = api_result.pop("ingredient_demand")
    expected_ingredient_demand = expected.pop("ingredient_demand")
    assert api_result == expected

    assert set(api_ingredient_demand.keys()) == set(expected_ingredient_demand.keys())
    for ingredient_id, api_demand in api_ingredient_demand.items():
        assert "family" in api_demand
        enriched_demand = {k: v for k, v in api_demand.items() if k != "family"}
        assert enriched_demand == expected_ingredient_demand[ingredient_id]
