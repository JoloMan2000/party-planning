"""Gäste-Katalog (Getränke/Essen/Anlässe) - anonym, kein Auth nötig.

``_DRINK_DEMAND_GROUPS``/``_FOOD_DEMAND_GROUPS`` mirroring die gleichnamigen
Konstanten in ``"Party Planning.py"`` (dort UI-Gruppierungs-Helfer ohne
Fachlogik, siehe Kommentar dort) - die feingranulare Tab-Gruppierung
(``_DRINK_GROUP_ORDER`` etc.) ist reine Streamlit-Widget-Anzeige und bleibt
bewusst dort; die Mobile-App gruppiert client-seitig selbst anhand von
``category``.

``lang``-Query-Param (Default ``de``) fügt ein zusätzliches
``display_name``-Feld hinzu (übersetzt via ``translations.catalog_item_name``,
mirroring ``render_catalog_picker()``'s ``_display_name()``) - ``name`` bleibt
unverändert der kanonische deutsche Name, damit bestehende Konsumenten
(Tests, evtl. andere Clients) nicht brechen."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path, get_occasions
from party_engine.catalog_curation import filter_items_by_curation, get_catalog_curation_settings
from party_engine.domain import PartyCatalog
from translations import catalog_item_name

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

_DRINK_DEMAND_GROUPS = {"alcoholic_beverage", "non_alcoholic_beverage", "energy", "beverage_general"}
_FOOD_DEMAND_GROUPS = {"main", "side", "snack", "dessert", "condiment", "salad"}


def _selectable(
    catalog: PartyCatalog, demand_groups: set[str], db_path, lang: str, apply_curation: bool = True
) -> list[dict]:
    items = list(catalog.direct_consumables.values()) + list(catalog.recipes.values())
    items = [i for i in items if i.demand_group in demand_groups]
    if apply_curation:
        curation_settings = get_catalog_curation_settings(db_path)
        items = filter_items_by_curation(items, curation_settings)
    result = []
    for item in items:
        data = to_jsonable(item)
        data["display_name"] = catalog_item_name(item.id, item.name, lang)
        result.append(data)
    return result


@router.get("/drinks")
def list_drinks(
    lang: str = "de", catalog: PartyCatalog = Depends(get_catalog), db_path=Depends(get_db_path)
) -> list[dict]:
    return _selectable(catalog, _DRINK_DEMAND_GROUPS, db_path, lang)


@router.get("/food")
def list_food(
    lang: str = "de", catalog: PartyCatalog = Depends(get_catalog), db_path=Depends(get_db_path)
) -> list[dict]:
    return _selectable(catalog, _FOOD_DEMAND_GROUPS, db_path, lang)


@router.get("/occasions")
def list_occasions(occasions=Depends(get_occasions)) -> list[dict]:
    return [to_jsonable(profile) for profile in occasions.values()]
