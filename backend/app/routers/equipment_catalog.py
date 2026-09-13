"""Equipment-Katalog-Browsing (Mobile-UI-Phase) - authenticated (anders als
`backend/app/routers/catalog.py`'s öffentlicher Food/Beverage-Gast-Katalog
gibt es für Equipment keinen anonymen ExternalGuest-Flow). Keine Demand-
Group-Filterung wie beim Food-Katalog - Equipment kennt keine
`demand_group`; der Client sucht/filtert selbst (mirrort
`CatalogPicker`'s client-seitiges Substring-Matching). Kategorie-Namen
werden server-seitig aufgelöst und mitgeliefert, damit der Client keinen
zweiten Lookup braucht (mirrort Food-Katalogs `display_name`-
Denormalisierung)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import get_equipment_catalog
from backend.app.schemas.equipment import EquipmentCatalogItemPublic
from equipment_engine.domain import EquipmentCatalog

router = APIRouter(prefix="/api/v1/equipment", tags=["equipment-catalog"])


@router.get("/catalog", response_model=list[EquipmentCatalogItemPublic])
def list_equipment_catalog(
    current_user: User = Depends(get_current_user),
    catalog: EquipmentCatalog = Depends(get_equipment_catalog),
) -> list[EquipmentCatalogItemPublic]:
    result: list[EquipmentCatalogItemPublic] = []
    for item in catalog.items.values():
        if not item.active:
            continue
        category = catalog.categories.get(item.category_id)
        subcategory = catalog.categories.get(item.subcategory_id) if item.subcategory_id else None
        result.append(
            EquipmentCatalogItemPublic(
                id=item.id,
                name=item.name,
                equipment_type=item.equipment_type,
                unit=item.unit,
                category_id=item.category_id,
                category_name=category.name if category is not None else item.category_id,
                subcategory_id=item.subcategory_id,
                subcategory_name=subcategory.name if subcategory is not None else None,
                tags=sorted(item.tags),
            )
        )
    return sorted(result, key=lambda i: i.name)
