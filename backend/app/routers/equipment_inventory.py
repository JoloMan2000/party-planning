"""Self-Only CRUD für das Host-Equipment-Inventar (Spec §7, Phase 1).
Mirrort das ``/me/social-privacy``-Muster in ``backend/app/routers/social.py``
(bare ``Depends(get_current_user)``, kein ``party_id`` - das Inventar gehört
einem User, nicht einer Party)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

import equipment_engine.storage as equipment_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_db_path, get_equipment_catalog
from backend.app.schemas.equipment import (
    EquipmentInventoryItemCreate,
    EquipmentInventoryItemPublic,
    EquipmentInventoryItemUpdateRequest,
)
from equipment_engine.domain import EquipmentCatalog, PartyEquipmentInventoryItem

router = APIRouter(prefix="/api/v1/me/equipment-inventory", tags=["equipment-inventory"])


def _to_public(item: PartyEquipmentInventoryItem) -> EquipmentInventoryItemPublic:
    return EquipmentInventoryItemPublic(
        id=item.id, owner_user_id=item.owner_user_id, equipment_item_id=item.equipment_item_id,
        quantity=item.quantity, condition=item.condition, available=item.available, notes=item.notes,
    )


def _get_owned_or_404(db_path: Path, inventory_item_id: str, current_user: User) -> PartyEquipmentInventoryItem:
    """404 statt 403 bei fremdem Item - keine Existenz verraten (mirrort
    ``backend/app/routers/social.py::get_user_friends``-Prinzip)."""
    existing = equipment_storage.get_inventory_item(db_path, inventory_item_id)
    if existing is None or existing.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found.")
    return existing


@router.get("", response_model=list[EquipmentInventoryItemPublic])
def list_my_equipment_inventory(
    current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> list[EquipmentInventoryItemPublic]:
    return [_to_public(i) for i in equipment_storage.list_inventory_for_user(db_path, current_user.id)]


@router.post("", response_model=EquipmentInventoryItemPublic, status_code=status.HTTP_201_CREATED)
def create_equipment_inventory_item(
    payload: EquipmentInventoryItemCreate,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    catalog: EquipmentCatalog = Depends(get_equipment_catalog),
) -> EquipmentInventoryItemPublic:
    if payload.equipment_item_id not in catalog.items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown equipment_item_id.")
    try:
        item = equipment_storage.create_inventory_item(
            db_path, uuid.uuid4().hex, current_user.id, payload.equipment_item_id,
            quantity=payload.quantity, condition=payload.condition, available=payload.available, notes=payload.notes,
        )
    except equipment_storage.InventoryItemAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory row for this item already exists - use PATCH to update it.",
        )
    return _to_public(item)


@router.patch("/{inventory_item_id}", response_model=EquipmentInventoryItemPublic)
def update_equipment_inventory_item(
    inventory_item_id: str,
    payload: EquipmentInventoryItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> EquipmentInventoryItemPublic:
    _get_owned_or_404(db_path, inventory_item_id, current_user)
    updated = equipment_storage.update_inventory_item(
        db_path, inventory_item_id,
        quantity=payload.quantity, condition=payload.condition, available=payload.available, notes=payload.notes,
    )
    return _to_public(updated)


@router.delete("/{inventory_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment_inventory_item(
    inventory_item_id: str, current_user: User = Depends(get_current_user), db_path: Path = Depends(get_db_path)
) -> None:
    _get_owned_or_404(db_path, inventory_item_id, current_user)
    equipment_storage.delete_inventory_item(db_path, inventory_item_id)
