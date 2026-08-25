"""Tests für die Gäste-Antworten-Storage (``party_engine/response_storage.py``).

Extrahiert aus ``"Party Planning.py"`` (Backend-Migration Phase 1, Schritt 0a).
Nutzt eine temporäre sqlite-DB (``tmp_path``) für die Persistenz-Tests.
"""

from __future__ import annotations

import json

from party_engine.response_storage import (
    _classify_item_type,
    init_db,
    load_responses,
    save_response,
)


def test_init_ist_idempotent(tmp_path):
    db_path = tmp_path / "responses.db"
    init_db(db_path)
    init_db(db_path)  # darf nicht crashen

    assert load_responses(db_path) == []


def test_save_und_reload_roundtrip(tmp_path):
    db_path = tmp_path / "responses.db"
    init_db(db_path)

    save_response(
        db_path,
        name="Max",
        start_time="19:00",
        drinks=["beer_pils"],
        drinks_freetext="",
        food=["pizza_margherita"],
        food_freetext="",
        songs=[{"artist": "Queen", "title": "Bohemian Rhapsody"}],
    )

    rows = load_responses(db_path)
    assert len(rows) == 1
    assert rows[0]["name"] == "Max"
    assert json.loads(rows[0]["drinks"]) == ["beer_pils"]
    assert json.loads(rows[0]["food"]) == ["pizza_margherita"]
    assert json.loads(rows[0]["songs"])[0]["artist"] == "Queen"


def test_load_responses_ordnet_nach_id(tmp_path):
    db_path = tmp_path / "responses.db"
    init_db(db_path)

    save_response(db_path, "Erste", "18:00", [], "", [], "", [])
    save_response(db_path, "Zweite", "19:00", [], "", [], "", [])

    rows = load_responses(db_path)
    assert [row["name"] for row in rows] == ["Erste", "Zweite"]


def test_classify_item_type_erkennt_rezepte_und_direct_consumables(catalog):
    recipe_id = next(iter(catalog.recipes))
    direct_id = next(iter(catalog.direct_consumables))
    assert _classify_item_type(recipe_id, catalog) == "recipe"
    assert _classify_item_type(direct_id, catalog) == "direct_consumable"


def test_classify_item_type_unbekannte_id_gibt_leeren_string(catalog):
    assert _classify_item_type("nicht_existierende_id", catalog) == ""
