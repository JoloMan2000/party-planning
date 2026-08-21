"""
Substitution
============

Hierarchische, asymmetrische Substitution (AUFGABE §33). Wird ausschließlich
für die Umverteilung von OVERFLOW nach der Grundallokation verwendet (siehe
``party_engine/allocation.py``), niemals für die Grundallokation selbst.

Sicherheitsregel (safety-critical, siehe AUFGABE §29/§33):
    Dietary Constraints schlagen jede Substitution. Ein veganer Gast darf
    NIEMALS automatisch eine Fleisch- oder Nicht-vegane Variante erhalten.
    Vegane Portionen dürfen vegetarische Nachfrage substituieren (aber nicht
    umgekehrt). Alkohol -> alkoholfrei ist als Overflow erlaubt, niemals
    umgekehrt automatisch.
"""

from __future__ import annotations

from party_engine.domain import DietaryProfile, PartyCatalog


def _underlying_flags(target_id: str, catalog: PartyCatalog) -> tuple[bool, bool, bool, list[str]]:
    """Liefert (is_vegetarian, is_vegan, contains_alcohol, allergens) für ein
    Recipe, DirectConsumable oder Ingredient, unabhängig vom konkreten Typ."""
    recipe = catalog.recipes.get(target_id)
    if recipe is not None:
        return (recipe.is_vegetarian, recipe.is_vegan, recipe.contains_alcohol, [])

    dc = catalog.direct_consumables.get(target_id)
    if dc is not None:
        ingredient = catalog.ingredients.get(dc.ingredient_id)
        if ingredient is not None:
            return (
                ingredient.is_vegetarian,
                ingredient.is_vegan,
                ingredient.contains_alcohol or dc.abv > 0,
                ingredient.allergens,
            )
        return (True, False, dc.abv > 0, [])

    ingredient = catalog.ingredients.get(target_id)
    if ingredient is not None:
        return (ingredient.is_vegetarian, ingredient.is_vegan, ingredient.contains_alcohol, ingredient.allergens)

    return (True, False, False, [])


def _dietary_compatible(target_id: str, catalog: PartyCatalog, dietary: DietaryProfile | None) -> bool:
    if dietary is None or dietary.is_empty():
        return True
    is_vegetarian, is_vegan, _alcohol, allergens = _underlying_flags(target_id, catalog)
    if dietary.vegan and not is_vegan:
        return False
    if dietary.vegetarian and not is_vegetarian:
        return False
    if dietary.allergies:
        # Wir können ohne strukturierte Allergen-Zuordnung pro Gast keine
        # automatische "sicher"-Aussage treffen -> im Zweifel keine
        # automatische Substitution auf ein Item mit bekannten Allergenen,
        # die in der Gast-Allergieliste auftauchen.
        lowered_allergies = {a.strip().lower() for a in dietary.allergies}
        lowered_allergens = {a.strip().lower() for a in allergens}
        if lowered_allergies & lowered_allergens:
            return False
    return True


def get_substitution_candidates(
    source_id: str,
    catalog: PartyCatalog,
    dietary: DietaryProfile | None = None,
) -> list[tuple[str, float]]:
    """Liefert dietätisch sichere Substitutions-Kandidaten für ``source_id``,
    absteigend nach Kompatibilität sortiert. Wird nur für Overflow-
    Umverteilung verwendet, nie für die Grundallokation.

    Regeln:
        - ``direction == "bidirectional"``: Regel gilt in beide Richtungen.
        - ``direction == "one_way"``: Regel gilt nur von ``from_id`` nach
          ``to_id`` (z.B. Alkohol -> alkoholfrei, vegan -> vegetarisch).
        - Zusätzliches hartes Sicherheitsnetz (unabhängig von den Katalog-
          Daten): alkoholfrei -> Alkohol ist NIEMALS erlaubt, selbst wenn
          eine (fehlerhafte) Katalogregel das nahelegen würde.
        - Dietary Constraints schlagen jede Substitution.
    """
    _src_veg, _src_vegan, source_alcohol, _src_allerg = _underlying_flags(source_id, catalog)

    candidates: list[tuple[str, float]] = []
    for rule in catalog.substitution_rules:
        target_id: str | None = None
        if rule.from_id == source_id:
            target_id = rule.to_id
        elif rule.direction == "bidirectional" and rule.to_id == source_id:
            target_id = rule.from_id
        if target_id is None:
            continue

        _tgt_veg, _tgt_vegan, target_alcohol, _tgt_allerg = _underlying_flags(target_id, catalog)

        # Hartes Sicherheitsnetz: alkoholfrei -> Alkohol niemals automatisch.
        if not source_alcohol and target_alcohol:
            continue

        if not _dietary_compatible(target_id, catalog, dietary):
            continue

        candidates.append((target_id, rule.compatibility))

    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return candidates
