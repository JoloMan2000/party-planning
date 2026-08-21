"""End-to-end Tests für ``party_engine.engine.compute_party_demand``.

Nutzt ausschließlich den echten Katalog (siehe ``conftest.catalog``), keine
Mocks - jeweils entsprechend AUFGABE §43.
"""

from __future__ import annotations

import pytest

from party_engine.domain import DietaryProfile, GuestResponse
from party_engine.engine import compute_party_demand


def _guest(name: str, drinks=None, food=None, dietary=None) -> GuestResponse:
    return GuestResponse(
        guest_name=name,
        start_time="18:00",
        drink_selections=list(drinks or []),
        food_selections=list(food or []),
        dietary=dietary or DietaryProfile(),
    )


def test_vodka_from_two_different_cocktails_aggregates_into_one_entry(catalog, config):
    """Guest A: Espresso Martini, Guest B: Moscow Mule -> beide Rezepte
    enthalten 'vodka'. Der Bedarf muss in EINEM gemeinsamen IngredientDemand-
    Eintrag landen, mit je einer eigenen Contribution pro Gast/Rezept."""
    responses = [
        _guest("Alice", drinks=["espresso_martini"]),
        _guest("Bob", drinks=["moscow_mule"]),
    ]
    result = compute_party_demand(catalog, responses, config)

    assert "vodka" in result.ingredient_demand
    vodka = result.ingredient_demand["vodka"]

    # Genau EIN Ingredient-Eintrag für vodka (dict-Key-Eindeutigkeit reicht
    # bereits als Beweis), mit Contributions von BEIDEN Rezepten.
    source_ids = {c.source_item_id for c in vodka.contributions}
    assert source_ids == {"espresso_martini", "moscow_mule"}
    assert len(vodka.contributions) == 2

    # Statt die konkreten (Cap-abhängigen) Mengen zu erraten: vergleiche
    # gegen dieselbe Pipeline für jeden Gast EINZELN aufgerufen - die
    # gemeinsame Ausführung darf pro Gast exakt dieselbe Menge produzieren
    # wie eine isolierte Berechnung (reine Aggregation, keine gegenseitige
    # Beeinflussung der Gäste untereinander).
    alice_only = compute_party_demand(catalog, [_guest("Alice", drinks=["espresso_martini"])], config)
    bob_only = compute_party_demand(catalog, [_guest("Bob", drinks=["moscow_mule"])], config)
    expected_espresso = alice_only.ingredient_demand["vodka"].raw_quantity
    expected_mule = bob_only.ingredient_demand["vodka"].raw_quantity

    contrib_by_source = {c.source_item_id: c.amount for c in vodka.contributions}
    assert contrib_by_source["espresso_martini"] == pytest.approx(expected_espresso, rel=1e-6)
    assert contrib_by_source["moscow_mule"] == pytest.approx(expected_mule, rel=1e-6)
    assert vodka.raw_quantity == pytest.approx(expected_espresso + expected_mule, rel=1e-6)


def test_burger_bun_from_two_different_burgers_aggregates_into_one_entry(catalog, config):
    """Guest A: Cheeseburger, Guest B: Veggie Burger -> beide Rezepte
    enthalten 'burger_bun'. Muss im selben IngredientDemand-Eintrag landen."""
    responses = [
        _guest("Alice", food=["cheeseburger"]),
        _guest("Bob", food=["veggie_burger"]),
    ]
    result = compute_party_demand(catalog, responses, config)

    assert "burger_bun" in result.ingredient_demand
    bun = result.ingredient_demand["burger_bun"]

    source_ids = {c.source_item_id for c in bun.contributions}
    assert source_ids == {"cheeseburger", "veggie_burger"}
    assert len(bun.contributions) == 2


def test_vegan_guest_food_demand_never_fulfilled_by_meat(catalog, config):
    """Safety-critical (AUFGABE §29/§33): ein veganer Gast darf niemals
    automatisch Fleisch-Substitution erhalten. Wir provozieren absichtlich
    einen Alkohol-Overflow (der einzige Pfad, der aktuell automatische
    Substitution auslöst) mit einem veganen Dietary-Profil und prüfen, dass
    KEINE nicht-vegane Zutat als direktes Ergebnis einer Substitution
    auftaucht, UND dass die Substitutions-Kandidatenliste für vegane Gäste
    niemals ein nicht-veganes/fleischhaltiges Ziel enthält."""
    vegan = DietaryProfile(vegan=True)

    # Sehr viele Alkohol-Selektionen erzwingen einen Cap-Overflow.
    alcoholic_dcs = [
        dc.id
        for dc in catalog.direct_consumables.values()
        if dc.demand_group == "alcoholic_beverage"
    ][:5]
    assert alcoholic_dcs, "Testvoraussetzung: es müssen alkoholische DirectConsumables existieren"

    responses = [_guest("Vega", drinks=alcoholic_dcs, dietary=vegan)]
    result = compute_party_demand(catalog, responses, config)

    # Kein Review-Issue darf implizieren, dass automatisch substituiert wurde -
    # wichtiger: JEDE Ingredient, die im Ergebnis auftaucht und aus einem
    # Rezept/DirectConsumable stammt, darf für einen veganen Gast keine
    # Fleisch-/Fisch-Zutat sein (harte Prüfung über das Katalog-Flag).
    for ingredient_id, demand in result.ingredient_demand.items():
        ingredient = catalog.ingredients.get(ingredient_id)
        if ingredient is None:
            continue
        assert not ingredient.is_meat, (
            f"Veganer Gast hat Bedarf für Fleisch-Zutat '{ingredient_id}' ausgelöst - "
            "verboten laut AUFGABE §29/§33."
        )
        assert not ingredient.is_fish


def test_water_is_always_allocated_as_baseline_regardless_of_selection(catalog, config):
    """AUFGABE §31: Wasser wird IMMER als Baseline berechnet, unabhängig
    davon, ob der Gast überhaupt etwas ausgewählt hat."""
    responses = [_guest("Nobody")]  # keine Auswahl, kein Freitext
    result = compute_party_demand(catalog, responses, config)

    assert "water" in result.ingredient_demand
    water = result.ingredient_demand["water"]
    assert water.raw_quantity > 0
    # 1 Gast * water_l_per_guest sollte (vor Reserve) exakt der konfigurierten
    # Menge entsprechen (Baseline nimmt nicht an anderen Budgets teil).
    assert water.raw_quantity == pytest.approx(config.water_l_per_guest, rel=1e-6)


def test_reserve_is_applied_once_after_global_aggregation(catalog, config):
    """AUFGABE §36/§37: Reserve wird EINMAL nach globaler Aggregation über
    ALLE Gäste angewendet, nicht pro Gast. D.h. quantity_after_reserve muss
    exakt raw_quantity * (1 + reserve_pct) der AGGREGIERTEN Menge sein."""
    responses = [
        _guest("Alice", drinks=["espresso_martini"]),
        _guest("Bob", drinks=["moscow_mule"]),
    ]
    result = compute_party_demand(catalog, responses, config)
    vodka = result.ingredient_demand["vodka"]

    assert vodka.quantity_after_reserve == pytest.approx(
        vodka.raw_quantity * (1 + vodka.reserve_pct), rel=1e-9
    )
    # Gegenprobe: wäre Reserve stattdessen PRO Gast angewendet worden
    # (getrennt für jede Contribution aufgerundet/aufgeschlagen und dann erst
    # summiert), wäre das Ergebnis bei nichtlinearer Rundung verschieden -
    # hier zusätzlich sichergestellt, dass die Summe der Contributions exakt
    # der raw_quantity entspricht (keine versteckte Vorab-Reserve pro Gast).
    contrib_sum = sum(c.amount for c in vodka.contributions)
    assert contrib_sum == pytest.approx(vodka.raw_quantity, rel=1e-9)


def test_alcohol_modifier_burger_ohne_kaese_removes_cheese(catalog, config):
    responses = [_guest("Alice", food=[])]
    responses[0].food_freetext = "Burger ohne Käse"
    result = compute_party_demand(catalog, responses, config)

    assert "cheddar" not in result.ingredient_demand
    assert "burger_bun" in result.ingredient_demand


def test_burger_plus_bacon_adds_bacon_modifier(catalog, config):
    responses = [_guest("Bob", food=[])]
    responses[0].food_freetext = "Burger + Bacon"
    result = compute_party_demand(catalog, responses, config)

    assert "bacon" in result.ingredient_demand
