from __future__ import annotations

from fastapi import APIRouter, Depends

import accounts.party_storage as party_storage
import event_theme
import party_engine.context_orchestration as context_orchestration
from accounts.domain import PartyMembership, PartyRole
from backend.app.core.auth import require_party_role
from backend.app.core.deps import get_catalog, get_db_path
from backend.app.schemas.admin import PartySettingsUpdate
from party_engine.domain import PartyCatalog

router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/party-settings", tags=["admin"])

_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})


@router.get("")
def get_party_settings(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    return event_theme.get_party_settings(db_path, party_id)


@router.get("/event-types")
def get_event_types(party_id: str, membership: PartyMembership = Depends(_require_admin)) -> list[dict]:
    """Liste aller wählbaren Event-Typen für das Party-Settings-Dropdown
    (mirroring ``event_type_keys``/``_format_event_type`` in
    ``render_party_settings_section``)."""
    return [
        {
            "id": key,
            "emoji": theme["emoji"],
            "label_de": theme["label_de"],
            "label_en": theme["label_en"],
            "default_title": theme["default_title"],
        }
        for key, theme in event_theme.EVENT_TYPES.items()
    ]


@router.post("")
def save_party_settings(
    party_id: str,
    payload: PartySettingsUpdate,
    db_path=Depends(get_db_path),
    catalog: PartyCatalog = Depends(get_catalog),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    """Speichert die Party-Settings; löst VORHER den Lifecycle-Trigger aus,
    falls ein neues Datum gesetzt wird (mirroring des Save-Button-Handlers in
    ``render_party_settings_section``)."""
    existing = event_theme.get_party_settings(db_path, party_id)
    reset_happened = False
    if payload.party_date and payload.party_date != existing["party_date"]:
        party = party_storage.get_party(db_path, party_id)
        reset_happened = context_orchestration.maybe_freeze_and_reset_party(
            db_path, party_id, party.host_user_id, existing, catalog
        )
    event_theme.save_party_settings(
        db_path,
        party_id,
        payload.event_type,
        payload.party_name,
        party_date=payload.party_date,
        party_start_time=payload.party_start_time,
        party_duration_hours=payload.party_duration_hours,
        party_location=payload.party_location,
    )
    return {"status": "ok", "reset_happened": reset_happened}
