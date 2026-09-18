"""Food/Beverage-Plan-Integration (Phase 3, Spec §49/§51/§150). Übersetzt
das REALE Ergebnis der separaten Food+Beverage "Demand Engine"
(``party_engine.engine.compute_party_demand``) in die beiden Router-Level-
Eingaben, die ``equipment_engine.engine.calculate_equipment_demand`` bereits
seit Phase 1/2 kennt (siehe deren Docstring: ``capacity_need_overrides`` ist
explizit als "vom Aufrufer VOR diesem Funktionsaufruf gemergt" dokumentiert).
Bewusst KEINE Änderung an ``calculate_equipment_demand``/``equipment_engine
.demand`` - dieses Modul lebt eine Ebene darüber, mirrort den Router-Merge-
Stil von ``equipment_engine.context.compute_seating_and_table_capacity_needs``
(Phase 2)."""

from __future__ import annotations

from party_engine.domain import PartyCatalog, PartyDemandResult

# Ingredient.family-Werte (party_engine/domain.py, gegen catalog/ingredients.json
# verifiziert), die typischerweise GEKÜHLT serviert werden und daher zum
# "large_beverage_cooler"-Kapazitätsbedarf beitragen (Spec §51). Planungs-
# Default, NICHT spec-belegt: Spirituosen/Wein/Likör werden üblicherweise
# nicht im selben Kühler-Volumen wie Bier/Softdrinks/Wasser gekühlt.
_COLD_BEVERAGE_FAMILIES = {"beer", "softdrink", "water", "juice", "energy"}

# Exakt die "Kuchen"-Gruppe aus party_engine/recommendation_tagging.py:1073-1077
# (dort NUR Empfehlungs-Tagging, hier erstmals als echte Demand-Trigger-Regel
# verwendet, Spec §150 "Cake hinzugefügt. Engine ergänzt: cake knife, cake
# server..."). BEWUSST NICHT die Nachbar-Gruppe "tiramisu/panna_cotta/
# mousse_au_chocolat/cheesecake_im_glas/dessert_im_glas" (ebd.) - das sind
# portionierte "Dessert im Glas"-Rezepte, die mit dem Löffel gegessen werden
# und keinen Tortenheber/kein Tortenmesser brauchen.
_CAKE_RECIPE_IDS = {
    "kaesekuchen", "schokokuchen", "marmorkuchen",
    "apfelkuchen", "zitronenkuchen", "blechkuchen",
}


def compute_beverage_capacity_needs(result: PartyDemandResult, catalog: PartyCatalog) -> dict[str, float]:
    """Liefert ROHE Bedarfswerte in der jeweiligen Regel-Treiber-Einheit
    (mirrort ``compute_seating_and_table_capacity_needs``'s Docstring-Regel:
    NICHT vordividieren, das übernimmt die ``capacity_based``-Regel selbst -
    siehe ``equipment_engine/context.py``).

    ``large_beverage_cooler``: Summe von ``quantity_after_reserve`` (Liter,
    bereits reserve-behaftet - dieselbe Zahl, die der Host auch in der
    Shopping List sieht) über alle Ingredients mit gekühlter Familie.
    ``ice_bag``: ``result.ice_demand_kg`` direkt - bereits ein fertig
    berechnetes kg-Aggregat (siehe ``party_engine.bom.compute_ice_demand_kg``),
    keine eigene Herleitung nötig."""
    cold_liters = 0.0
    for ingredient_id, demand in result.ingredient_demand.items():
        ingredient = catalog.ingredients.get(ingredient_id)
        if ingredient is not None and ingredient.family in _COLD_BEVERAGE_FAMILIES:
            cold_liters += demand.quantity_after_reserve
    return {"large_beverage_cooler": cold_liters, "ice_bag": result.ice_demand_kg}


def compute_food_triggered_item_ids(result: PartyDemandResult) -> set[str]:
    """Spec §150: ein Kuchen (>0 erwartete Portionen) im Food-Plan löst ECHTEN
    Demand für Tortenmesser/Tortenheber aus ("ergänzt", nicht nur "empfiehlt"
    - anders als die advisory-only Wetter-Empfehlungen aus Phase 2, siehe
    ``equipment_engine.context.compute_context_recommendations``). Der
    Aufrufer UNIONiert das Ergebnis mit den vom Host explizit gewählten
    ``selected_item_ids`` - ``dessert_plate`` braucht keinen Eintrag hier,
    das ist bereits ein ``always_on``-Item seit Phase 1."""
    has_cake = any(
        item.item_id in _CAKE_RECIPE_IDS and item.expected_servings > 0 for item in result.item_demand
    )
    return {"cake_knife", "cake_server"} if has_cake else set()
