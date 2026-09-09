"""Pytest-Unit-Tests für ``organizers.storage`` (Social-Graph-Phase-4).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.user_storage as user_storage
import organizers.storage as organizers_storage
from organizers.domain import OrganizerRole, OrganizerVerificationStatus


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "organizers_test.db"
    user_storage.init_user_storage(path)
    organizers_storage.init_organizer_storage(path)
    return path


@pytest.fixture()
def owner(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "owner@example.com", "hash", "Owner")


@pytest.fixture()
def member(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "member@example.com", "hash", "Member")


def test_init_ist_idempotent(db_path):
    organizers_storage.init_organizer_storage(db_path)
    organizers_storage.init_organizer_storage(db_path)


def test_create_organizer_legt_owner_membership_automatisch_an(db_path, owner):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    membership = organizers_storage.get_membership(db_path, organizer.id, owner.id)
    assert membership is not None
    assert membership.role == OrganizerRole.OWNER
    assert organizer.verification_status == OrganizerVerificationStatus.UNVERIFIED


def test_get_organizer_unbekannt_ist_none(db_path):
    assert organizers_storage.get_organizer(db_path, "unknown") is None


def test_get_membership_unbekannt_ist_none(db_path, owner):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    assert organizers_storage.get_membership(db_path, organizer.id, "unknown") is None


def test_list_organizers_for_user_enthaelt_eigene_organizer(db_path, owner, member):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    result = organizers_storage.list_organizers_for_user(db_path, owner.id)
    assert len(result) == 1
    assert result[0][0].id == organizer.id
    assert result[0][1].role == OrganizerRole.OWNER
    assert organizers_storage.list_organizers_for_user(db_path, member.id) == []


def test_upsert_membership_fuegt_neues_mitglied_hinzu(db_path, owner, member):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.EDITOR)
    membership = organizers_storage.get_membership(db_path, organizer.id, member.id)
    assert membership.role == OrganizerRole.EDITOR


def test_upsert_membership_ist_idempotent_bei_gleicher_rolle(db_path, owner, member):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.VIEWER)
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.VIEWER)
    assert len(organizers_storage.list_members(db_path, organizer.id)) == 2  # owner + member, kein Duplikat


def test_upsert_membership_aendert_rolle(db_path, owner, member):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.VIEWER)
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.ADMIN)
    assert organizers_storage.get_membership(db_path, organizer.id, member.id).role == OrganizerRole.ADMIN


def test_list_members_enthaelt_alle_rollen(db_path, owner, member):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.EVENT_MANAGER)
    roles = {m.role for m in organizers_storage.list_members(db_path, organizer.id)}
    assert roles == {OrganizerRole.OWNER, OrganizerRole.EVENT_MANAGER}


def test_is_user_verified_organizer_member_false_vor_verifizierung(db_path, owner):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    assert organizers_storage.is_user_verified_organizer_member(db_path, owner.id) is False


def test_is_user_verified_organizer_member_true_nach_verifizierung_fuer_jede_rolle(db_path, owner, member):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    organizers_storage.upsert_membership(db_path, organizer.id, member.id, OrganizerRole.VIEWER)
    organizers_storage.set_verification_status(db_path, organizer.id, OrganizerVerificationStatus.VERIFIED)
    assert organizers_storage.is_user_verified_organizer_member(db_path, owner.id) is True
    assert organizers_storage.is_user_verified_organizer_member(db_path, member.id) is True


@pytest.mark.parametrize(
    "status",
    [OrganizerVerificationStatus.PENDING, OrganizerVerificationStatus.SUSPENDED, OrganizerVerificationStatus.REJECTED],
)
def test_is_user_verified_organizer_member_bleibt_false_fuer_nicht_verdrahtete_status(db_path, owner, status):
    organizer = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    organizers_storage.set_verification_status(db_path, organizer.id, status)
    assert organizers_storage.is_user_verified_organizer_member(db_path, owner.id) is False


def test_is_user_verified_organizer_member_ohne_organizer_ist_false(db_path, owner):
    assert organizers_storage.is_user_verified_organizer_member(db_path, owner.id) is False


def test_list_organizers_admin_listing(db_path, owner, member):
    org1 = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events")
    org2 = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, member.id, "Other Events")
    ids = {o.id for o in organizers_storage.list_organizers(db_path)}
    assert {org1.id, org2.id} <= ids
