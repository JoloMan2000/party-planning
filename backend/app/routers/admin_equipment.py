"""Minimaler party-gescopter Equipment-Demand-Endpunkt (Phase 1) - mirrort
``backend/app/routers/admin_shopping_list.py`` exakt (``require_party_role``,
``to_jsonable(result)``-Antwort, kein eigenes Response-Schema).

``guest_count`` kommt aus den echten ACCEPTED/TENTATIVE-Memberships der
Party; ``host_inventory`` aus dem Inventar des ECHTEN Hosts
(``party.host_user_id``), nicht des Aufrufers - ein Co-Host, der das hier
berechnet, sieht weiterhin das tatsächliche Host-Inventar."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.party_storage as party_storage
import equipment_engine.storage as equipment_storage
from accounts.domain import PartyMembership, PartyRole, RsvpStatus
from backend.app.core.auth import require_party_role
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_db_path, get_equipment_catalog
from backend.app.schemas.equipment import EquipmentDemandComputeRequest
from equipment_engine.domain import EquipmentCatalog
from equipment_engine.engine import calculate_equipment_demand

router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/equipment-demand", tags=["admin"])

_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})

_ACTIVE_RSVP_STATUSES = (RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE)


@router.post("")
def compute_equipment_demand(
    party_id: str,
    payload: EquipmentDemandComputeRequest,
    db_path: Path = Depends(get_db_path),
    catalog: EquipmentCatalog = Depends(get_equipment_catalog),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")

    members = party_storage.list_memberships_for_party(db_path, party_id)
    guest_count = len([m for m in members if m.rsvp_status in _ACTIVE_RSVP_STATUSES])
    host_inventory = equipment_storage.list_inventory_for_user(db_path, party.host_user_id)

    result = calculate_equipment_demand(
        catalog,
        guest_count=guest_count,
        selected_item_ids=payload.selected_item_ids,
        station_activity_interest=payload.station_activity_interest,
        capacity_need_overrides=payload.capacity_need_overrides,
        host_inventory=host_inventory,
    )
    return to_jsonable(result)
