"""Pytest-Unit-Tests für die ``accounts/*_storage.py``-Module (Account-
basierter Pivot, Phase 1). Ergänzt die ausführbaren ``__main__``-Selbsttests
in den Modulen selbst um eine pytest-Variante für die Testsuite (isolierte
``tmp_path``-DB statt ``tempfile.TemporaryDirectory``)."""

from __future__ import annotations

import uuid

import pytest

import accounts.invitation_storage as invitation_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import PartyRole, RsvpStatus


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "accounts_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    invitation_storage.init_invitation_storage(path)
    return path


def test_create_user_lehnt_doppelte_email_ab(db_path):
    user_storage.create_user(db_path, uuid.uuid4().hex, "dupe@example.com", "hash1", "First")
    with pytest.raises(user_storage.EmailAlreadyRegisteredError):
        user_storage.create_user(db_path, uuid.uuid4().hex, "dupe@example.com", "hash2", "Second")


def test_user_dataclass_hat_kein_password_hash_feld(db_path):
    user = user_storage.create_user(db_path, uuid.uuid4().hex, "nohash@example.com", "secret-hash", "NoHash")
    assert not hasattr(user, "password_hash")

    by_id = user_storage.get_user_by_id(db_path, user.id)
    assert not hasattr(by_id, "password_hash")

    by_email = user_storage.get_user_by_email(db_path, "nohash@example.com")
    assert not hasattr(by_email, "password_hash")


def test_create_party_legt_atomisch_host_membership_an(db_path):
    host = user_storage.create_user(db_path, uuid.uuid4().hex, "host@example.com", "hash", "Host")
    party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Party")

    membership = party_storage.get_membership(db_path, party.id, host.id)
    assert membership is not None
    assert membership.role == PartyRole.HOST
    assert membership.rsvp_status == RsvpStatus.ACCEPTED


def test_create_invitation_legt_atomisch_guest_membership_an(db_path):
    host = user_storage.create_user(db_path, uuid.uuid4().hex, "host2@example.com", "hash", "Host")
    guest = user_storage.create_user(db_path, uuid.uuid4().hex, "guest2@example.com", "hash", "Guest")
    party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Party")

    invitation_storage.create_invitation(db_path, uuid.uuid4().hex, party.id, host.id, guest.id)

    membership = party_storage.get_membership(db_path, party.id, guest.id)
    assert membership is not None
    assert membership.role == PartyRole.GUEST
    assert membership.rsvp_status == RsvpStatus.PENDING


def test_create_invitation_doppelt_wird_abgelehnt(db_path):
    host = user_storage.create_user(db_path, uuid.uuid4().hex, "host3@example.com", "hash", "Host")
    guest = user_storage.create_user(db_path, uuid.uuid4().hex, "guest3@example.com", "hash", "Guest")
    party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Party")

    invitation_storage.create_invitation(db_path, uuid.uuid4().hex, party.id, host.id, guest.id)
    with pytest.raises(invitation_storage.InvitationAlreadyExistsError):
        invitation_storage.create_invitation(db_path, uuid.uuid4().hex, party.id, host.id, guest.id)


def _party_with_invitation(db_path):
    host = user_storage.create_user(db_path, uuid.uuid4().hex, f"host-{uuid.uuid4().hex}@example.com", "hash", "Host")
    guest = user_storage.create_user(db_path, uuid.uuid4().hex, f"guest-{uuid.uuid4().hex}@example.com", "hash", "Guest")
    party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Party")
    invitation = invitation_storage.create_invitation(db_path, uuid.uuid4().hex, party.id, host.id, guest.id)
    return host, guest, party, invitation


def test_apply_rsvp_transition_happy_path(db_path):
    _host, guest, _party, invitation = _party_with_invitation(db_path)
    result = invitation_storage.apply_rsvp_transition(db_path, invitation.id, RsvpStatus.ACCEPTED, guest.id, expected_version=1)
    assert result.status == RsvpStatus.ACCEPTED
    assert result.version == 2


def test_apply_rsvp_transition_version_conflict_keine_mutation(db_path):
    _host, guest, _party, invitation = _party_with_invitation(db_path)
    invitation_storage.apply_rsvp_transition(db_path, invitation.id, RsvpStatus.ACCEPTED, guest.id, expected_version=1)

    with pytest.raises(invitation_storage.VersionConflictError) as excinfo:
        invitation_storage.apply_rsvp_transition(db_path, invitation.id, RsvpStatus.TENTATIVE, guest.id, expected_version=1)
    assert excinfo.value.current_version == 2
    assert excinfo.value.expected_version == 1

    unchanged = invitation_storage.get_invitation(db_path, invitation.id)
    assert unchanged.status == RsvpStatus.ACCEPTED
    assert unchanged.version == 2


def test_apply_rsvp_transition_invalid_transition(db_path):
    _host, guest, _party, invitation = _party_with_invitation(db_path)
    with pytest.raises(invitation_storage.InvalidTransitionError):
        invitation_storage.apply_rsvp_transition(db_path, invitation.id, RsvpStatus.REVOKED, guest.id, expected_version=1)


def test_apply_rsvp_transition_idempotenter_replay(db_path):
    _host, guest, _party, invitation = _party_with_invitation(db_path)
    crid = uuid.uuid4().hex

    r1 = invitation_storage.apply_rsvp_transition(
        db_path, invitation.id, RsvpStatus.ACCEPTED, guest.id, expected_version=1, client_request_id=crid
    )
    r2 = invitation_storage.apply_rsvp_transition(
        db_path, invitation.id, RsvpStatus.ACCEPTED, guest.id, expected_version=1, client_request_id=crid
    )
    assert r1.version == r2.version == 2


def test_apply_rsvp_transition_idempotency_key_reuse_mit_anderem_status(db_path):
    _host, guest, _party, invitation = _party_with_invitation(db_path)
    crid = uuid.uuid4().hex
    invitation_storage.apply_rsvp_transition(
        db_path, invitation.id, RsvpStatus.ACCEPTED, guest.id, expected_version=1, client_request_id=crid
    )
    with pytest.raises(invitation_storage.IdempotencyKeyReuseError):
        invitation_storage.apply_rsvp_transition(
            db_path, invitation.id, RsvpStatus.DECLINED, guest.id, expected_version=2, client_request_id=crid
        )
