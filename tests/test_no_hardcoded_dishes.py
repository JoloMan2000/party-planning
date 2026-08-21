"""Strukturelle Absicherung von AUFGABE §46: die Berechnungsengine darf
keine konkreten Gerichte/Cocktails hardcoden.

Diese Prüfung durchsucht die Engine-/Logik-Module (NICHT Tests, NICHT
Dokumentation) nach String-Literalen, die mit einer konkreten Rezept-,
DirectConsumable- oder Ingredient-ID aus dem Katalog übereinstimmen, und
lässt genau die dokumentierten, spec-mandatierten Ausnahmen zu (z.B. die
universelle Wasser-Baseline, AUFGABE §31, sowie generische Ingredient-
``family``-Namen, die zufällig mit einer Ingredient-ID kollidieren, z.B.
"water" als Reserve-Familienschlüssel)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_FILES = [
    "party_engine/allocation.py",
    "party_engine/bom.py",
    "party_engine/engine.py",
    "party_engine/substitution.py",
    "party_engine/purchasing.py",
]

# Spec-mandatierte / strukturell unvermeidbare Ausnahmen:
#  - "water": universelle Baseline-ID (AUFGABE §31, Wasser IMMER als
#    Baseline).
#  - FAMILY_RESERVE_KEY-Schlüssel/-Werte (party_engine.bom): das ist eine
#    generische Ingredient.family -> Reserve-Kategorie Taxonomie (jede
#    Ingredient mit passendem "family"-Attribut wird erfasst, unabhängig vom
#    konkreten Katalogeintrag) - einige Family-Namen kollidieren rein
#    textuell zufällig mit einer einzelnen Ingredient-ID (z.B. "potato"),
#    das ist aber KEINE dish-spezifische Verzweigung im Sinne von §46.
from party_engine.bom import FAMILY_RESERVE_KEY  # noqa: E402

_ALLOWED_LITERALS = {"water"} | set(FAMILY_RESERVE_KEY.keys()) | set(FAMILY_RESERVE_KEY.values())


def _string_literals(text: str) -> set[str]:
    return set(re.findall(r"[\"']([a-zA-Z0-9_]+)[\"']", text))


def test_engine_modules_do_not_hardcode_catalog_item_ids(catalog):
    catalog_ids = set(catalog.recipes) | set(catalog.direct_consumables) | set(catalog.ingredients)

    offenders: dict[str, set[str]] = {}
    for rel_path in ENGINE_FILES:
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        literals = _string_literals(text)
        hits = (literals & catalog_ids) - _ALLOWED_LITERALS
        if hits:
            offenders[rel_path] = hits

    assert not offenders, (
        "Engine-Module enthalten hartcodierte Katalog-IDs (verboten laut "
        f"AUFGABE §46): {offenders}"
    )
