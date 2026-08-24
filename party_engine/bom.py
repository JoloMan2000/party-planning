"""
Recipe BOM Explosion & globale Ingredient-Aggregation
======================================================

Setzt die Pipeline-Schritte ``DirectConsumable/Recipe -> Recipe BOM
Explosion -> IngredientDemand -> Global Aggregation -> Production Rules ->
Reserve`` um (AUFGABE §2-3, §12, §34, §36-37, §41).

Wichtig: Es wird NICHT gerundet, bevor nicht alle Portionen aller Gäste in
Ingredients zerlegt und global aggregiert wurden (§36). Die Reserve wird erst
NACH der globalen Aggregation angewendet (§37).
"""

from __future__ import annotations

from party_engine.allocation import GuestAllocation
from party_engine.domain import (
    IngredientDemand,
    IngredientDemandContribution,
    PartyCatalog,
    PartyConfig,
)

# Designentscheidung (Eisbedarf, AUFGABE §13): der Katalog modelliert Eis
# bewusst NICHT als gewöhnliches Ingredient (kein Einkaufsposten je Rezept),
# sondern über ``Recipe.ice_profile``. Diese Heuristik legt einen
# realistischen Eisbedarf in kg pro Portion je Eis-Profil fest, analog zum
# Stil bereits offener Designentscheidungen in drink_model.py.
ICE_KG_PER_SERVING_BY_PROFILE: dict[str, float] = {
    "shaken": 0.06,
    "stirred": 0.05,
    "highball": 0.08,
    "crushed": 0.10,
    "blended": 0.12,
    "no_ice": 0.0,
    "": 0.0,
}

# Reserve-Familie je Ingredient-``family`` (siehe PartyConfig.reserve_percentages).
FAMILY_RESERVE_KEY: dict[str, str] = {
    "spirit": "spirit",
    "liqueur": "liqueur",
    "wine": "wine",
    "fortified_wine": "wine",
    "sparkling_wine": "sparkling_wine",
    "beer": "beer",
    "softdrink": "softdrink",
    "juice": "juice",
    "syrup": "juice",
    "energy": "energy",
    "coffee": "coffee",
    "water": "water",
    "meat_beef": "main_meat",
    "meat_pork": "main_meat",
    "meat_lamb": "main_meat",
    "poultry": "main_meat",
    "fish": "main_meat",
    "veg_protein": "main_vegetarian",
    "vegan_protein": "main_vegetarian",
    "bread": "bread",
    "potato": "side",
    "grain": "side",
    "pasta": "side",
    "salad_green": "salad",
    "vegetable": "fresh",
    "fruit": "fresh",
    "citrus": "fresh",
    "herb": "fresh",
    "dairy": "fresh",
    "plant_milk": "fresh",
    "cheese": "fresh",
    "sauce": "sauce",
    "snack": "snack",
    "dessert_ing": "dessert",
}


def _source_name_with_brand(base_name: str, ingredient_id: str, brand_map: dict[str, str]) -> str:
    brand = brand_map.get(ingredient_id)
    return f"{base_name} ({brand})" if brand else base_name


def _components_for_allocation(alloc: GuestAllocation, catalog: PartyCatalog):
    """Liefert (ingredient_id, amount_per_serving, unit) Tupel für EINE
    Portion des allozierten Items, inkl. angewandter Modifier."""
    item_id, item_type = alloc.item_id, alloc.item_type

    components: list[list] = []  # [ingredient_id, amount, unit] (mutable Liste wg. scale)

    if item_type == "direct_consumable":
        dc = catalog.direct_consumables.get(item_id)
        if dc is None:
            return []
        components.append([dc.ingredient_id, dc.serving_size_l, "l"])
    elif item_type == "recipe":
        recipe = catalog.recipes.get(item_id)
        if recipe is None:
            return []
        for comp in recipe.components:
            components.append([comp.ingredient_id, comp.amount, comp.unit])
    else:
        return []

    for mod_id in alloc.applied_modifiers:
        modifier = catalog.modifiers.get(mod_id)
        if modifier is None:
            continue
        if modifier.effect_type == "add_component" and modifier.target_ingredient_id:
            components.append([modifier.target_ingredient_id, modifier.amount, modifier.unit])
        elif modifier.effect_type == "remove_component" and modifier.target_ingredient_id:
            components = [c for c in components if c[0] != modifier.target_ingredient_id]
        elif modifier.effect_type == "scale" and modifier.amount:
            for c in components:
                c[1] = c[1] * modifier.amount
        # set_brand_preference verändert keine Mengen, nur die Brand-Info.

    return components


def explode_to_ingredient_demand(
    allocations: list[GuestAllocation], catalog: PartyCatalog
) -> dict[str, IngredientDemand]:
    """Explodiert alle Guest-Allocations in Ingredient-Contributions und
    aggregiert sie GLOBAL über alle Gäste/Rezepte/Items hinweg (§2-3, §41).
    Liefert Rohbedarf (KEINE Reserve, KEINE Rundung)."""
    demand: dict[str, IngredientDemand] = {}

    for alloc in allocations:
        item = catalog.get_item(alloc.item_id)
        if item is None:
            continue
        item_name = item.name

        brand_map: dict[str, str] = {}
        if alloc.brand:
            if alloc.item_type == "direct_consumable":
                dc = catalog.direct_consumables.get(alloc.item_id)
                if dc:
                    brand_map[dc.ingredient_id] = alloc.brand
            else:
                for mod_id in alloc.applied_modifiers:
                    modifier = catalog.modifiers.get(mod_id)
                    if modifier and modifier.effect_type == "set_brand_preference":
                        brand_map[modifier.target_ingredient_id] = alloc.brand

        for ingredient_id, amount_per_serving, unit in _components_for_allocation(alloc, catalog):
            ingredient = catalog.ingredients.get(ingredient_id)
            if ingredient is None:
                continue
            contribution_amount = amount_per_serving * alloc.servings
            if contribution_amount <= 0:
                continue

            entry = demand.get(ingredient_id)
            if entry is None:
                entry = IngredientDemand(
                    ingredient_id=ingredient_id,
                    name=ingredient.name,
                    unit=ingredient.unit,
                    raw_quantity=0.0,
                )
                demand[ingredient_id] = entry

            entry.raw_quantity += contribution_amount
            entry.contributions.append(
                IngredientDemandContribution(
                    source_item_id=alloc.item_id,
                    source_item_name=_source_name_with_brand(item_name, ingredient_id, brand_map),
                    amount=contribution_amount,
                    unit=unit,
                )
            )

    return demand


def compute_ice_demand_kg(
    allocations: list[GuestAllocation], catalog: PartyCatalog, ice_multiplier: float = 1.0
) -> float:
    """``ice_multiplier`` (§77/§19 Party-Context-Engine-Spec, optional):
    ``derived_context.beverage_modifiers.ice_multiplier`` - skaliert den
    gesamten Eisbedarf (z.B. Hitze/Sommer/Outdoor -> mehr Eis), ohne die
    Rezept-Vorgaben (``ICE_KG_PER_SERVING_BY_PROFILE``) selbst zu ändern."""
    total = 0.0
    for alloc in allocations:
        if alloc.item_type != "recipe":
            continue
        recipe = catalog.recipes.get(alloc.item_id)
        if recipe is None:
            continue
        per_serving = ICE_KG_PER_SERVING_BY_PROFILE.get(recipe.ice_profile, 0.0)
        total += per_serving * alloc.servings
    return total * ice_multiplier


def apply_production_rules(
    demand: dict[str, IngredientDemand], catalog: PartyCatalog
) -> dict[str, IngredientDemand]:
    """Expandiert Ingredients ohne direkten Einkaufsweg (``purchasable=False``
    oder keine hinterlegten ``PurchaseSKU``s) über ``ProductionRule``s in ihre
    Input-Zutaten (§34). Läuft iterativ, um Ketten (max. 5 Runden) aufzulösen.
    """
    rules_by_output = {rule.output_ingredient_id: rule for rule in catalog.production_rules}

    for _round in range(5):
        expanded_any = False
        for ingredient_id in list(demand.keys()):
            ingredient = catalog.ingredients.get(ingredient_id)
            if ingredient is None:
                continue
            has_purchase_path = ingredient.purchasable and bool(catalog.purchase_skus.get(ingredient_id))
            if has_purchase_path:
                continue
            rule = rules_by_output.get(ingredient_id)
            if rule is None:
                continue

            entry = demand[ingredient_id]
            output_quantity = entry.raw_quantity
            if output_quantity <= 0:
                continue

            for input_spec in rule.inputs:
                input_id = input_spec.get("ingredient_id")
                ratio = input_spec.get("ratio", 1.0)
                input_ingredient = catalog.ingredients.get(input_id)
                if input_ingredient is None:
                    continue
                added_amount = output_quantity * ratio

                target = demand.get(input_id)
                if target is None:
                    target = IngredientDemand(
                        ingredient_id=input_id,
                        name=input_ingredient.name,
                        unit=input_ingredient.unit,
                        raw_quantity=0.0,
                    )
                    demand[input_id] = target
                target.raw_quantity += added_amount
                target.contributions.append(
                    IngredientDemandContribution(
                        source_item_id=f"production:{ingredient_id}",
                        source_item_name=f"Produktion: {entry.name}",
                        amount=added_amount,
                        unit=input_ingredient.unit,
                    )
                )
                expanded_any = True

            # Output selbst wird nicht direkt eingekauft -> aus dem
            # Einkaufs-Ingredient-Demand entfernen, aber Contributions bleiben
            # für Nachvollziehbarkeit im Objekt erhalten (nur nicht mehr im
            # finalen dict), daher: raw_quantity auf 0 setzen und aus dem
            # Purchase-relevanten Demand-Dict entfernen.
            del demand[ingredient_id]

        if not expanded_any:
            break

    return demand


def _reserve_key_for(ingredient_family: str) -> str:
    return FAMILY_RESERVE_KEY.get(ingredient_family, "default")


def apply_reserve(
    demand: dict[str, IngredientDemand], catalog: PartyCatalog, config: PartyConfig
) -> dict[str, IngredientDemand]:
    """Wendet die konfigurierte Reserve NACH globaler Aggregation an (§37).
    Mutiert und liefert dieselben ``IngredientDemand``-Objekte zurück."""
    for ingredient_id, entry in demand.items():
        ingredient = catalog.ingredients.get(ingredient_id)
        family = ingredient.family if ingredient else "misc"
        reserve_key = _reserve_key_for(family)
        reserve_pct = config.reserve_percentages.get(reserve_key, config.reserve_percentages.get("default", 0.1))
        entry.reserve_pct = reserve_pct
        entry.quantity_after_reserve = entry.raw_quantity * (1 + reserve_pct)
    return demand
