"""Lädt ``catalog/equipment/*.json`` in einen ``EquipmentCatalog`` -
mirrort ``party_engine/catalog.py`` (gleiches ``lru_cache``-Caching-Muster,
gleiche Datei-pro-Kollektionstyp-Konvention). Abweichung: hier werden JSON-
Zeilen NICHT blind per ``Cls(**row)`` entpackt, sondern über explizite
``_build_*``-Helfer konstruiert, damit set-getypte Felder (``tags``,
``required_capabilities``, ...) korrekt aus JSON-Listen in echte ``set``s
konvertiert werden (ein rohes ``**row`` würde dort Listen belassen)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from equipment_engine.domain import (
    EquipmentCatalog,
    EquipmentCategory,
    EquipmentDemandRule,
    EquipmentItem,
    EquipmentRecommendationMetadata,
    PurchaseSKU,
)

_DEFAULT_CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog" / "equipment"


def _read_json(path: Path) -> dict | list:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_category(row: dict) -> EquipmentCategory:
    return EquipmentCategory(
        id=row["id"],
        name=row["name"],
        parent_id=row.get("parent_id"),
        description=row.get("description", ""),
    )


def _build_recommendation(row: dict | None) -> EquipmentRecommendationMetadata:
    row = row or {}
    return EquipmentRecommendationMetadata(
        tags=set(row.get("tags", [])),
        required_capabilities=set(row.get("required_capabilities", [])),
        preferred_capabilities=set(row.get("preferred_capabilities", [])),
    )


def _build_item(row: dict) -> EquipmentItem:
    return EquipmentItem(
        id=row["id"],
        name=row["name"],
        category_id=row["category_id"],
        subcategory_id=row.get("subcategory_id"),
        equipment_type=row.get("equipment_type", "consumable"),
        unit=row.get("unit", "pcs"),
        tags=set(row.get("tags", [])),
        recommendation=_build_recommendation(row.get("recommendation")),
        demand_rule_id=row.get("demand_rule_id"),
        reserve_pct=row.get("reserve_pct", 0.05),
        always_on=row.get("always_on", True),
        active=row.get("active", True),
    )


def _build_demand_rule(row: dict) -> EquipmentDemandRule:
    return EquipmentDemandRule(
        id=row["id"],
        driver_type=row["driver_type"],
        base_quantity=row.get("base_quantity", 0.0),
        per_guest=row.get("per_guest"),
        per_station=row.get("per_station"),
        capacity_per_unit=row.get("capacity_per_unit"),
        minimum_quantity=row.get("minimum_quantity"),
        maximum_quantity=row.get("maximum_quantity"),
        station_id=row.get("station_id"),
        target_item_id=row.get("target_item_id"),
    )


def _build_purchase_skus(item_id: str, rows: list[dict]) -> list[PurchaseSKU]:
    return [
        PurchaseSKU(
            ingredient_id=item_id,
            size=row["size"],
            unit=row["unit"],
            pack_label=row.get("pack_label", ""),
            pack_count=row.get("pack_count", 1),
        )
        for row in rows
    ]


@lru_cache(maxsize=8)
def _load_catalog_cached(catalog_dir_str: str) -> EquipmentCatalog:
    catalog_dir = Path(catalog_dir_str)

    categories = {k: _build_category(v) for k, v in _read_json(catalog_dir / "categories.json").items()}
    items = {k: _build_item(v) for k, v in _read_json(catalog_dir / "items.json").items()}
    demand_rules = {k: _build_demand_rule(v) for k, v in _read_json(catalog_dir / "demand_rules.json").items()}

    purchase_skus_raw = _read_json(catalog_dir / "purchase_skus.json")
    purchase_skus = {item_id: _build_purchase_skus(item_id, rows) for item_id, rows in purchase_skus_raw.items()}

    return EquipmentCatalog(
        categories=categories,
        items=items,
        demand_rules=demand_rules,
        purchase_skus=purchase_skus,
    )


def load_catalog(catalog_dir: str | Path | None = None) -> EquipmentCatalog:
    resolved = Path(catalog_dir) if catalog_dir is not None else _DEFAULT_CATALOG_DIR
    return _load_catalog_cached(str(resolved.resolve()))


def clear_catalog_cache() -> None:
    """Nur für Tests - erzwingt einen Reload beim nächsten ``load_catalog()``."""
    _load_catalog_cached.cache_clear()


if __name__ == "__main__":
    catalog = load_catalog()
    assert 50 <= len(catalog.items) <= 80, f"expected 50-80 items, got {len(catalog.items)}"
    for item in catalog.items.values():
        assert item.category_id in catalog.categories, f"{item.id}: unknown category {item.category_id}"
        if item.subcategory_id is not None:
            sub = catalog.categories[item.subcategory_id]
            assert sub.parent_id == item.category_id, f"{item.id}: subcategory {sub.id} parent mismatch"
        if item.demand_rule_id is not None:
            assert item.demand_rule_id in catalog.demand_rules, f"{item.id}: unknown demand_rule_id {item.demand_rule_id}"
    for rule in catalog.demand_rules.values():
        if rule.driver_type == "per_station":
            assert rule.station_id and rule.target_item_id, f"{rule.id}: per_station rule missing station_id/target_item_id"
            assert rule.target_item_id in catalog.items, f"{rule.id}: unknown target_item_id {rule.target_item_id}"
    for item_id in catalog.purchase_skus:
        assert item_id in catalog.items, f"purchase_skus.json: unknown item_id {item_id}"
    print(f"OK: {len(catalog.items)} items, {len(catalog.categories)} categories, "
          f"{len(catalog.demand_rules)} demand rules, {len(catalog.purchase_skus)} items with purchase SKUs.")
