"""Gäste-Katalog (Getränke/Essen/Anlässe) - anonym, kein Auth nötig.

``_DRINK_DEMAND_GROUPS``/``_FOOD_DEMAND_GROUPS`` mirroring die gleichnamigen
Konstanten in ``"Party Planning.py"`` (dort UI-Gruppierungs-Helfer ohne
Fachlogik, siehe Kommentar dort) - die feingranulare Tab-Gruppierung
(``_DRINK_GROUP_ORDER`` etc.) ist reine Streamlit-Widget-Anzeige und bleibt
bewusst dort; die Mobile-App gruppiert client-seitig selbst anhand von
``category``."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path, get_occasions
from party_engine.catalog_curation import filter_items_by_curation, get_catalog_curation_settings
from party_engine.domain import PartyCatalog

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

_DRINK_DEMAND_GROUPS = {"alcoholic_beverage", "non_alcoholic_beverage", "energy", "beverage_general"}
_FOOD_DEMAND_GROUPS = {"main", "side", "snack", "dessert", "condiment", "salad"}


def _selectable(catalog: PartyCatalog, demand_groups: set[str], db_path) -> list[dict]:
    items = list(catalog.direct_consumables.values()) + list(catalog.recipes.values())
    items = [i for i in items if i.demand_group in demand_groups]
    curation_settings = get_catalog_curation_settings(db_path)
    items = filter_items_by_curation(items, curation_settings)
    return [to_jsonable(item) for item in items]


@router.get("/drinks")
def list_drinks(catalog: PartyCatalog = Depends(get_catalog), db_path=Depends(get_db_path)) -> list[dict]:
    return _selectable(catalog, _DRINK_DEMAND_GROUPS, db_path)


@router.get("/food")
def list_food(catalog: PartyCatalog = Depends(get_catalog), db_path=Depends(get_db_path)) -> list[dict]:
    return _selectable(catalog, _FOOD_DEMAND_GROUPS, db_path)


@router.get("/occasions")
def list_occasions(occasions=Depends(get_occasions)) -> list[dict]:
    return [to_jsonable(profile) for profile in occasions.values()]
