"""Pydantic-Schemas für die Equipment Engine (Phase 1). Mirrort die
Konvention von ``backend/app/schemas/organizers.py`` (reine
``BaseModel``-DTOs)."""

from __future__ import annotations

from pydantic import BaseModel


class EquipmentInventoryItemCreate(BaseModel):
    equipment_item_id: str
    quantity: float = 1.0
    condition: str = ""
    available: bool = True
    notes: str = ""


class EquipmentInventoryItemUpdateRequest(BaseModel):
    """``None`` bedeutet je Feld "unverändert lassen" (mirrort
    ``ProfileUpdateRequest``/``SocialPrivacyUpdateRequest``)."""

    quantity: float | None = None
    condition: str | None = None
    available: bool | None = None
    notes: str | None = None


class EquipmentInventoryItemPublic(BaseModel):
    id: str
    owner_user_id: str
    equipment_item_id: str
    quantity: float
    condition: str
    available: bool
    notes: str


class EquipmentCatalogItemPublic(BaseModel):
    """Ein Katalog-Item für die Mobile-Katalog-Browsing-/Such-UI (mirrort
    `CatalogPicker`'s Erwartungen: Name, Kategorie server-seitig aufgelöst,
    kein zweiter Lookup-Call nötig)."""

    id: str
    name: str
    equipment_type: str
    unit: str
    category_id: str
    category_name: str
    subcategory_id: str | None = None
    subcategory_name: str | None = None
    tags: list[str] = []


class EquipmentDemandComputeRequest(BaseModel):
    """``station_activity_interest``/``capacity_need_overrides`` sind
    OPTIONALE Host-Overrides, die serverseitig berechnete Defaults
    überschreiben (Payload gewinnt bei Konflikt) - keine reinen Stub-
    Platzhalter mehr: ``capacity_need_overrides`` seit Phase 2/3 (Seating/
    Tische + echter Beverage-/Food-Plan), ``station_activity_interest`` seit
    Phase 4 (echtes Gäste-Voting über die ``activities``-Domain, siehe
    ``equipment_engine.activity_integration``). ``guest_count``/
    ``duration_hours``/``derived_context``/``venue_provisions`` werden
    weiterhin ausschließlich serverseitig aufgelöst, nicht vom Client
    übergeben."""

    selected_item_ids: list[str] = []
    station_activity_interest: dict[str, int] = {}
    capacity_need_overrides: dict[str, float] = {}


class EquipmentProvisionCreate(BaseModel):
    equipment_item_id: str
    quantity: float
    notes: str = ""


class EquipmentProvisionUpdateRequest(BaseModel):
    """``None`` bedeutet je Feld "unverändert lassen" (mirrort
    ``EquipmentInventoryItemUpdateRequest``)."""

    quantity: float | None = None
    notes: str | None = None


class EquipmentProvisionPublic(BaseModel):
    id: str
    party_id: str
    equipment_item_id: str
    quantity: float
    notes: str
