from __future__ import annotations

from fastapi import APIRouter, Depends

import event_theme
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path
from backend.app.core.security import get_current_admin
from party_engine.domain import PartyCatalog, PartyConfig
from party_engine.engine import compute_party_demand
from party_engine.legacy_adapter import guest_response_from_row

router = APIRouter(prefix="/api/v1/admin/shopping-list", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.post("")
def compute_shopping_list(db_path=Depends(get_db_path), catalog: PartyCatalog = Depends(get_catalog)) -> dict:
    settings = event_theme.get_party_settings(db_path)
    rows = response_storage.load_responses(db_path)
    guest_responses = [guest_response_from_row(row, catalog) for row in rows]
    derived_context = context_orchestration.get_derived_party_context(db_path, settings, len(rows))
    result = compute_party_demand(catalog, guest_responses, PartyConfig(), derived_context=derived_context)
    return to_jsonable(result)
