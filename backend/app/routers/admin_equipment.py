"""Party-gescopte Equipment-Endpunkte: Demand-Compute (Phase 1, PartyContext-
Integration in Phase 2, Beverage+Food-Plan-Integration in Phase 3) +
Venue-Provisions-CRUD (Phase 2, Spec §98/§146 "Venue provides 40 chairs").

Demand-Compute mirrort ``backend/app/routers/admin_shopping_list.py`` exakt
(``require_party_role``, ``to_jsonable(result)``-Antwort, kein eigenes
Response-Schema). ``guest_count`` kommt aus den echten ACCEPTED/TENTATIVE-
Memberships der Party; ``host_inventory`` aus dem Inventar des ECHTEN Hosts
(``party.host_user_id``), nicht des Aufrufers - ein Co-Host, der das hier
berechnet, sieht weiterhin das tatsächliche Host-Inventar.

Phase 3 (Spec §49/§51/§150): ruft zusätzlich ``party_engine.engine
.compute_party_demand`` (dieselbe "Demand Engine" wie
``admin_shopping_list.py``) mit derselben ``len(rows)``-``guest_count``-Basis
auf, damit Equipment und Shopping List für dieselbe Party immer identische
Getränke-/Eis-Zahlen zugrunde legen - bewusst NICHT dieselbe RSVP-basierte
``guest_count`` wie oben (siehe ``equipment_engine.food_beverage_integration``).

Venue-Provisions-CRUD mirrort ``backend/app/routers/equipment_inventory.py``'s
404-statt-403-Konvention bei fremdem/falsch-gescoptem Datensatz, aber
party- statt user-gescopt (daher ein zweiter ``APIRouter`` mit eigenem
Prefix in dieser Datei, statt einer neuen Datei - beide Router bedienen
denselben "Equipment für diese Party"-Ressourcenbereich)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import accounts.party_storage as party_storage
import equipment_engine.storage as equipment_storage
import event_theme
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from accounts.domain import PartyMembership, PartyRole, RsvpStatus
from backend.app.core.auth import require_party_role
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path, get_equipment_catalog
from backend.app.schemas.equipment import (
    EquipmentDemandComputeRequest,
    EquipmentProvisionCreate,
    EquipmentProvisionPublic,
    EquipmentProvisionUpdateRequest,
)
from equipment_engine.context import compute_seating_and_table_capacity_needs
from equipment_engine.domain import EquipmentCatalog, PartyEquipmentProvision
from equipment_engine.engine import calculate_equipment_demand
from equipment_engine.food_beverage_integration import (
    compute_beverage_capacity_needs,
    compute_food_triggered_item_ids,
)
from party_engine.domain import PartyCatalog, PartyConfig
from party_engine.engine import compute_party_demand
from party_engine.legacy_adapter import guest_response_from_row

router = APIRouter(prefix="/api/v1/parties/{party_id}/admin/equipment-demand", tags=["admin"])
provisions_router = APIRouter(
    prefix="/api/v1/parties/{party_id}/admin/equipment-venue-inventory", tags=["admin"]
)

_require_admin = require_party_role({PartyRole.HOST, PartyRole.CO_HOST})

_ACTIVE_RSVP_STATUSES = (RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE)


@router.post("")
def compute_equipment_demand(
    party_id: str,
    payload: EquipmentDemandComputeRequest,
    db_path: Path = Depends(get_db_path),
    catalog: EquipmentCatalog = Depends(get_equipment_catalog),
    party_catalog: PartyCatalog = Depends(get_catalog),
    membership: PartyMembership = Depends(_require_admin),
) -> dict:
    party = party_storage.get_party(db_path, party_id)
    if party is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party nicht gefunden.")

    members = party_storage.list_memberships_for_party(db_path, party_id)
    guest_count = len([m for m in members if m.rsvp_status in _ACTIVE_RSVP_STATUSES])
    host_inventory = equipment_storage.list_inventory_for_user(db_path, party.host_user_id)
    venue_provisions = equipment_storage.list_provisions_for_party(db_path, party_id)

    settings = event_theme.get_party_settings(db_path, party_id)
    raw_context = context_orchestration.get_party_context(db_path, party_id, settings)
    derived_context = context_orchestration.get_derived_party_context(db_path, party_id, settings, guest_count)

    context_capacity_needs = compute_seating_and_table_capacity_needs(guest_count, raw_context.seating_ratio)

    # Phase 3 (Spec §49/§51/§150): echte Food+Beverage-Demand-Zahlen statt
    # manueller Stub-Overrides. Eigener ``get_derived_party_context``-Aufruf
    # mit ``len(rows)`` statt der RSVP-basierten ``guest_count`` oben, damit
    # dies exakt dieselben Zahlen liefert wie
    # ``admin_shopping_list.py::compute_shopping_list`` für dieselbe Party.
    rows = response_storage.load_responses(db_path, party_id)
    guest_responses = [guest_response_from_row(row, party_catalog) for row in rows]
    food_beverage_context = context_orchestration.get_derived_party_context(db_path, party_id, settings, len(rows))
    food_beverage_result = compute_party_demand(
        party_catalog, guest_responses, PartyConfig(), derived_context=food_beverage_context
    )
    beverage_capacity_needs = compute_beverage_capacity_needs(food_beverage_result, party_catalog)
    food_triggered_item_ids = compute_food_triggered_item_ids(food_beverage_result)

    capacity_need_overrides = {**context_capacity_needs, **beverage_capacity_needs, **payload.capacity_need_overrides}
    selected_item_ids = list(set(payload.selected_item_ids) | food_triggered_item_ids)

    result = calculate_equipment_demand(
        catalog,
        guest_count=guest_count,
        selected_item_ids=selected_item_ids,
        station_activity_interest=payload.station_activity_interest,
        capacity_need_overrides=capacity_need_overrides,
        host_inventory=host_inventory,
        duration_hours=raw_context.duration_hours,
        venue_provisions=venue_provisions,
        derived_context=derived_context,
    )
    return to_jsonable(result)


def _to_public(provision: PartyEquipmentProvision) -> EquipmentProvisionPublic:
    return EquipmentProvisionPublic(
        id=provision.id, party_id=provision.party_id, equipment_item_id=provision.equipment_item_id,
        quantity=provision.quantity, notes=provision.notes,
    )


def _get_party_provision_or_404(db_path: Path, party_id: str, provision_id: str) -> PartyEquipmentProvision:
    """404 statt 403 bei fremder/falsch-gescopter Provision - keine Existenz
    verraten (mirrort ``equipment_inventory.py::_get_owned_or_404``)."""
    existing = equipment_storage.get_provision(db_path, provision_id)
    if existing is None or existing.party_id != party_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provision not found.")
    return existing


@provisions_router.get("", response_model=list[EquipmentProvisionPublic])
def list_equipment_venue_inventory(
    party_id: str,
    db_path: Path = Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> list[EquipmentProvisionPublic]:
    return [_to_public(p) for p in equipment_storage.list_provisions_for_party(db_path, party_id)]


@provisions_router.post("", response_model=EquipmentProvisionPublic, status_code=status.HTTP_201_CREATED)
def create_equipment_venue_inventory(
    party_id: str,
    payload: EquipmentProvisionCreate,
    db_path: Path = Depends(get_db_path),
    catalog: EquipmentCatalog = Depends(get_equipment_catalog),
    membership: PartyMembership = Depends(_require_admin),
) -> EquipmentProvisionPublic:
    if payload.equipment_item_id not in catalog.items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown equipment_item_id.")
    try:
        provision = equipment_storage.create_provision(
            db_path, uuid.uuid4().hex, party_id, payload.equipment_item_id,
            quantity=payload.quantity, notes=payload.notes,
        )
    except equipment_storage.ProvisionAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provision row for this item already exists - use PATCH to update it.",
        )
    return _to_public(provision)


@provisions_router.patch("/{provision_id}", response_model=EquipmentProvisionPublic)
def update_equipment_venue_inventory(
    party_id: str,
    provision_id: str,
    payload: EquipmentProvisionUpdateRequest,
    db_path: Path = Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> EquipmentProvisionPublic:
    _get_party_provision_or_404(db_path, party_id, provision_id)
    updated = equipment_storage.update_provision(db_path, provision_id, quantity=payload.quantity, notes=payload.notes)
    return _to_public(updated)


@provisions_router.delete("/{provision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment_venue_inventory(
    party_id: str,
    provision_id: str,
    db_path: Path = Depends(get_db_path),
    membership: PartyMembership = Depends(_require_admin),
) -> None:
    _get_party_provision_or_404(db_path, party_id, provision_id)
    equipment_storage.delete_provision(db_path, provision_id)
