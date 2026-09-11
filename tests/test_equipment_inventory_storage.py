"""Storage-Tests für ``equipment_engine.storage`` (Host-Equipment-Inventar) -
Pytest-Variante des ``__main__``-Selbsttests, isolierte ``tmp_path``-DB."""

from __future__ import annotations

import uuid

import pytest

import equipment_engine.storage as equipment_storage


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "equipment_storage_test.db"
    equipment_storage.init_equipment_storage(path)
    return path


def test_create_list_get_update_delete_roundtrip(db_path):
    owner = uuid.uuid4().hex
    item_id = uuid.uuid4().hex

    created = equipment_storage.create_inventory_item(db_path, item_id, owner, "beer_pong_table", quantity=2.0)
    assert created.owner_user_id == owner
    assert created.equipment_item_id == "beer_pong_table"
    assert created.quantity == 2.0
    assert created.available is True

    fetched = equipment_storage.get_inventory_item(db_path, item_id)
    assert fetched == created

    listed = equipment_storage.list_inventory_for_user(db_path, owner)
    assert [i.id for i in listed] == [item_id]

    updated = equipment_storage.update_inventory_item(db_path, item_id, quantity=3.0, condition="good")
    assert updated.quantity == 3.0
    assert updated.condition == "good"
    assert updated.available is True  # unverändert, da nicht übergeben

    equipment_storage.delete_inventory_item(db_path, item_id)
    assert equipment_storage.get_inventory_item(db_path, item_id) is None


def test_duplicate_owner_equipment_item_pair_raises(db_path):
    owner = uuid.uuid4().hex
    equipment_storage.create_inventory_item(db_path, uuid.uuid4().hex, owner, "wine_glass", quantity=12.0)
    with pytest.raises(equipment_storage.InventoryItemAlreadyExistsError):
        equipment_storage.create_inventory_item(db_path, uuid.uuid4().hex, owner, "wine_glass", quantity=1.0)


def test_same_equipment_item_allowed_for_different_owners(db_path):
    owner_a, owner_b = uuid.uuid4().hex, uuid.uuid4().hex
    equipment_storage.create_inventory_item(db_path, uuid.uuid4().hex, owner_a, "wine_glass", quantity=12.0)
    # Kein Fehler - UNIQUE ist (owner_user_id, equipment_item_id), nicht nur equipment_item_id.
    equipment_storage.create_inventory_item(db_path, uuid.uuid4().hex, owner_b, "wine_glass", quantity=6.0)
    assert len(equipment_storage.list_inventory_for_user(db_path, owner_a)) == 1
    assert len(equipment_storage.list_inventory_for_user(db_path, owner_b)) == 1


def test_delete_nonexistent_item_is_idempotent(db_path):
    equipment_storage.delete_inventory_item(db_path, "never-existed")  # kein Fehler


def test_update_nonexistent_item_returns_none(db_path):
    assert equipment_storage.update_inventory_item(db_path, "never-existed", quantity=5.0) is None
