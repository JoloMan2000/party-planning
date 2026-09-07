from __future__ import annotations

from fastapi import APIRouter, Depends

import event_theme
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from accounts.domain import PartyMembership, PartyRole
from backend.app.core.auth import require_party_role
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_db_path
from backend.app.schemas.admin import PartyContextOverrideCreate, PartyContextUpdate
from party_context import storage as party_context_storage
from party_context.countries import ISO_COUNTRIES
from party_context.domain import PartyContextOverride
from party_context.locations import LOCATION_LABELS, LOCATION_TYPES

router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/party-context", tags=["admin"])

_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})


@router.get("/metadata")
def get_party_context_metadata(party_id: str, membership: PartyMembership = Depends(_require_admin)) -> dict:
    """Stammdaten fürs Party-Kontext-Formular (Location-Typen, Länderliste -
    mirroring der in ``render_party_context_section`` importierten
    ``LOCATION_TYPES``/``LOCATION_LABELS``/``ISO_COUNTRIES``-Konstanten)."""
    return {
        "location_types": [
            {"id": key, "label_de": LOCATION_LABELS[key][0], "label_en": LOCATION_LABELS[key][1]}
            for key in LOCATION_TYPES
        ],
        "countries": [
            {"code": code, "name": name}
            for code, name in sorted(ISO_COUNTRIES.items(), key=lambda item: item[1])
        ],
    }


@router.get("")
def get_party_context(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    return to_jsonable(party_context_storage.get_party_context(db_path, party_id))


@router.post("")
def save_party_context(
    party_id: str,
    payload: PartyContextUpdate,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    ctx = party_context_storage.get_party_context(db_path, party_id)
    for field_name, value in payload.model_dump().items():
        setattr(ctx, field_name, value)
    party_context_storage.save_party_context(db_path, party_id, ctx)
    return {"status": "ok"}


@router.get("/derived")
def get_derived_party_context(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> dict:
    settings = event_theme.get_party_settings(db_path, party_id)
    responses = response_storage.load_responses(db_path, party_id)
    derived = context_orchestration.get_derived_party_context(db_path, party_id, settings, len(responses))
    return to_jsonable(derived)


@router.get("/overrides")
def list_overrides(
    party_id: str, db_path=Depends(get_db_path), membership: PartyMembership = Depends(_require_admin)
) -> list[dict]:
    return [to_jsonable(o) for o in party_context_storage.get_party_context_overrides(db_path, party_id)]


@router.post("/overrides", status_code=201)
def add_override(
    party_id: str,
    payload: PartyContextOverrideCreate,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    party_context_storage.save_party_context_override(
        db_path, party_id, PartyContextOverride(key=payload.key, value=payload.value, reason=payload.reason or None)
    )
    return {"status": "ok"}


@router.delete("/overrides/{key}")
def delete_override(
    party_id: str,
    key: str,
    db_path=Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    party_context_storage.delete_party_context_override(db_path, party_id, key)
    return {"status": "ok"}
