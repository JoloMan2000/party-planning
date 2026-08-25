from __future__ import annotations

from fastapi import APIRouter, Depends

import event_theme
import party_engine.context_orchestration as context_orchestration
from backend.app.core.deps import get_catalog, get_db_path
from backend.app.core.security import get_current_admin
from backend.app.schemas.admin import PartySettingsUpdate
from party_engine.domain import PartyCatalog

router = APIRouter(prefix="/api/v1/admin/party-settings", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("")
def get_party_settings(db_path=Depends(get_db_path)) -> dict:
    return event_theme.get_party_settings(db_path)


@router.post("")
def save_party_settings(
    payload: PartySettingsUpdate,
    db_path=Depends(get_db_path),
    catalog: PartyCatalog = Depends(get_catalog),
) -> dict:
    """Speichert die Party-Settings; löst VORHER den Lifecycle-Trigger aus,
    falls ein neues Datum gesetzt wird (mirroring des Save-Button-Handlers in
    ``render_party_settings_section``)."""
    existing = event_theme.get_party_settings(db_path)
    reset_happened = False
    if payload.party_date and payload.party_date != existing["party_date"]:
        reset_happened = context_orchestration.maybe_freeze_and_reset_party(db_path, existing, catalog)
    event_theme.save_party_settings(
        db_path,
        payload.event_type,
        payload.party_name,
        party_date=payload.party_date,
        party_start_time=payload.party_start_time,
        party_duration_hours=payload.party_duration_hours,
        party_location=payload.party_location,
    )
    return {"status": "ok", "reset_happened": reset_happened}
