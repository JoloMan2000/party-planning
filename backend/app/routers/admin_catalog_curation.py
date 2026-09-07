from __future__ import annotations

from fastapi import APIRouter, Depends

from accounts.domain import PartyMembership, PartyRole
from backend.app.core.auth import require_party_role
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path
from backend.app.routers.catalog import _DRINK_DEMAND_GROUPS, _FOOD_DEMAND_GROUPS, _selectable
from backend.app.schemas.admin import CatalogCurationUpdate
from party_engine.catalog_curation import get_catalog_curation_settings, save_catalog_curation_settings
from party_engine.domain import CatalogCurationSettings, PartyCatalog

router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/catalog-curation", tags=["admin"])

_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})


@router.get("")
def get_curation(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    return to_jsonable(get_catalog_curation_settings(db_path, party_id))


@router.post("")
def save_curation(
    party_id: str,
    payload: CatalogCurationUpdate,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    settings = CatalogCurationSettings(enabled=payload.enabled, curated_item_ids=set(payload.curated_item_ids))
    save_catalog_curation_settings(db_path, party_id, settings)
    return {"status": "ok"}


@router.get("/items")
def get_curatable_items(
    party_id: str,
    lang: str = "de",
    catalog: PartyCatalog = Depends(get_catalog),
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    """Der VOLLSTÄNDIGE, ungefilterte Getränke-/Speisenkatalog (mirroring
    `_drink_items(catalog, apply_curation=False)`/`_food_items(..., apply_curation=False)`
    in `render_catalog_curation_section`) - der Admin muss immer aus dem
    ganzen Sortiment auswählen können, unabhängig davon, ob die Kuration
    aktuell selbst schon aktiv ist (sonst könnte man eine aktive Einschränkung
    nie mehr erweitern)."""
    return {
        "drinks": _selectable(catalog, _DRINK_DEMAND_GROUPS, db_path, party_id, lang, apply_curation=False),
        "food": _selectable(catalog, _FOOD_DEMAND_GROUPS, db_path, party_id, lang, apply_curation=False),
    }
