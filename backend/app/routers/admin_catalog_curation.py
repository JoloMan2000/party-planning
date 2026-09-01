from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path
from backend.app.core.security import get_current_admin
from backend.app.routers.catalog import _DRINK_DEMAND_GROUPS, _FOOD_DEMAND_GROUPS, _selectable
from backend.app.schemas.admin import CatalogCurationUpdate
from party_engine.catalog_curation import get_catalog_curation_settings, save_catalog_curation_settings
from party_engine.domain import CatalogCurationSettings, PartyCatalog

router = APIRouter(prefix="/api/v1/admin/catalog-curation", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("")
def get_curation(db_path=Depends(get_db_path)) -> dict:
    return to_jsonable(get_catalog_curation_settings(db_path))


@router.post("")
def save_curation(payload: CatalogCurationUpdate, db_path=Depends(get_db_path)) -> dict:
    settings = CatalogCurationSettings(enabled=payload.enabled, curated_item_ids=set(payload.curated_item_ids))
    save_catalog_curation_settings(db_path, settings)
    return {"status": "ok"}


@router.get("/items")
def get_curatable_items(
    lang: str = "de", catalog: PartyCatalog = Depends(get_catalog), db_path=Depends(get_db_path)
) -> dict:
    """Der VOLLSTÄNDIGE, ungefilterte Getränke-/Speisenkatalog (mirroring
    `_drink_items(catalog, apply_curation=False)`/`_food_items(..., apply_curation=False)`
    in `render_catalog_curation_section`) - der Admin muss immer aus dem
    ganzen Sortiment auswählen können, unabhängig davon, ob die Kuration
    aktuell selbst schon aktiv ist (sonst könnte man eine aktive Einschränkung
    nie mehr erweitern)."""
    return {
        "drinks": _selectable(catalog, _DRINK_DEMAND_GROUPS, db_path, lang, apply_curation=False),
        "food": _selectable(catalog, _FOOD_DEMAND_GROUPS, db_path, lang, apply_curation=False),
    }
