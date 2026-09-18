"""Storage-Tests für ``party_equipment_provisions`` (Phase 2, Spec §98/§146
"Venue provides 40 chairs") - mirrort ``tests/test_equipment_inventory_storage.py``'s
Struktur, aber party- statt owner_user_id-gescoped."""

from __future__ import annotations

import uuid

import pytest

import equipment_engine.storage as equipment_storage


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "equipment_provisions_test.db"
    equipment_storage.init_equipment_storage(path)
    return path


def test_create_list_get_update_delete_roundtrip(db_path):
    party_id = uuid.uuid4().hex
    provision_id = uuid.uuid4().hex

    created = equipment_storage.create_provision(db_path, provision_id, party_id, "folding_chair", quantity=40.0)
    assert created.party_id == party_id
    assert created.quantity == 40.0

    fetched = equipment_storage.get_provision(db_path, provision_id)
    assert fetched == created

    listed = equipment_storage.list_provisions_for_party(db_path, party_id)
    assert [p.id for p in listed] == [provision_id]

    updated = equipment_storage.update_provision(db_path, provision_id, quantity=50.0, notes="from the venue")
    assert updated.quantity == 50.0
    assert updated.notes == "from the venue"

    equipment_storage.delete_provision(db_path, provision_id)
    assert equipment_storage.get_provision(db_path, provision_id) is None
    equipment_storage.delete_provision(db_path, provision_id)  # idempotent


def test_duplicate_party_equipment_item_pair_raises(db_path):
    party_id = uuid.uuid4().hex
    equipment_storage.create_provision(db_path, uuid.uuid4().hex, party_id, "folding_chair", quantity=40.0)
    with pytest.raises(equipment_storage.ProvisionAlreadyExistsError):
        equipment_storage.create_provision(db_path, uuid.uuid4().hex, party_id, "folding_chair", quantity=1.0)


def test_same_equipment_item_allowed_for_different_parties(db_path):
    party_a, party_b = uuid.uuid4().hex, uuid.uuid4().hex
    equipment_storage.create_provision(db_path, uuid.uuid4().hex, party_a, "folding_chair", quantity=40.0)
    equipment_storage.create_provision(db_path, uuid.uuid4().hex, party_b, "folding_chair", quantity=10.0)
    assert len(equipment_storage.list_provisions_for_party(db_path, party_a)) == 1
    assert len(equipment_storage.list_provisions_for_party(db_path, party_b)) == 1
