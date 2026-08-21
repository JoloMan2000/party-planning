"""
PartyCatalog-Loader
====================

Lädt die statischen Stammdaten aus ``catalog/*.json`` (siehe ``build_catalog.py``,
welches diese Dateien einmalig erzeugt hat) und baut daraus ein vollständig
typisiertes ``PartyCatalog``-Objekt (dataclass-Instanzen statt Rohdicts).

Framework-agnostisch: Dieses Modul importiert Streamlit NICHT. Es funktioniert
mit reinem ``python3`` / ``pytest``. Caching erfolgt über ``functools.lru_cache``
auf einer internen Funktion, die über den (aufgelösten) Katalogpfad indiziert
wird - dadurch werden die JSON-Dateien nicht bei jedem Aufruf/Streamlit-Rerun
neu geparst (siehe AUFGABE §44).

Designentscheidung: Die eigentliche Streamlit-Cache-Anbindung (``st.cache_resource``)
erfolgt bewusst NICHT hier, sondern soll später beim UI-Wiring den hier
bereitgestellten (bereits gecachten) ``load_catalog()`` zusätzlich mit
``st.cache_resource`` umschließen. So bleibt ``party_engine`` unabhängig von
Streamlit testbar.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from party_engine.domain import (
    Alias,
    DirectConsumable,
    Ingredient,
    Modifier,
    PartyCatalog,
    ProductionRule,
    PurchaseSKU,
    Recipe,
    RecipeComponent,
    SubstitutionRule,
)

# Default: <repo_root>/catalog  (dieses Modul liegt in <repo_root>/party_engine/)
_DEFAULT_CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_ingredient(row: dict) -> Ingredient:
    return Ingredient(**row)


def _build_direct_consumable(row: dict) -> DirectConsumable:
    return DirectConsumable(**row)


def _build_recipe(row: dict) -> Recipe:
    row = dict(row)
    components_raw = row.pop("components", [])
    components = [RecipeComponent(**c) for c in components_raw]
    return Recipe(components=components, **row)


def _build_modifier(row: dict) -> Modifier:
    return Modifier(**row)


def _build_alias(row: dict) -> Alias:
    return Alias(**row)


def _build_substitution_rule(row: dict) -> SubstitutionRule:
    return SubstitutionRule(**row)


def _build_production_rule(row: dict) -> ProductionRule:
    return ProductionRule(**row)


def _build_purchase_skus(ingredient_id: str, rows: list[dict]) -> list[PurchaseSKU]:
    return [PurchaseSKU(ingredient_id=ingredient_id, **row) for row in rows]


@lru_cache(maxsize=8)
def _load_catalog_cached(catalog_dir_str: str) -> PartyCatalog:
    catalog_dir = Path(catalog_dir_str)

    ingredients = {
        k: _build_ingredient(v) for k, v in _read_json(catalog_dir / "ingredients.json").items()
    }
    direct_consumables = {
        k: _build_direct_consumable(v)
        for k, v in _read_json(catalog_dir / "direct_consumables.json").items()
    }
    recipes = {k: _build_recipe(v) for k, v in _read_json(catalog_dir / "recipes.json").items()}
    modifiers = {
        k: _build_modifier(v) for k, v in _read_json(catalog_dir / "modifiers.json").items()
    }
    aliases = [_build_alias(row) for row in _read_json(catalog_dir / "aliases.json")]
    substitution_rules = [
        _build_substitution_rule(row) for row in _read_json(catalog_dir / "substitution_rules.json")
    ]
    production_rules = [
        _build_production_rule(row) for row in _read_json(catalog_dir / "production_rules.json")
    ]
    purchase_skus_raw = _read_json(catalog_dir / "purchase_skus.json")
    purchase_skus = {
        ingredient_id: _build_purchase_skus(ingredient_id, rows)
        for ingredient_id, rows in purchase_skus_raw.items()
    }

    return PartyCatalog(
        ingredients=ingredients,
        direct_consumables=direct_consumables,
        recipes=recipes,
        modifiers=modifiers,
        aliases=aliases,
        substitution_rules=substitution_rules,
        production_rules=production_rules,
        purchase_skus=purchase_skus,
    )


def load_catalog(catalog_dir: Path | str | None = None) -> PartyCatalog:
    """Lädt (bzw. liefert aus dem Cache) das vollständige ``PartyCatalog``.

    Wiederholte Aufrufe mit demselben (aufgelösten) Pfad geben dieselbe
    ``PartyCatalog``-Instanz zurück, ohne die JSON-Dateien erneut zu parsen.
    """
    resolved = Path(catalog_dir) if catalog_dir else _DEFAULT_CATALOG_DIR
    return _load_catalog_cached(str(resolved.resolve()))


def clear_catalog_cache() -> None:
    """Nur für Tests: erzwingt beim nächsten ``load_catalog()`` ein Neuladen."""
    _load_catalog_cached.cache_clear()
