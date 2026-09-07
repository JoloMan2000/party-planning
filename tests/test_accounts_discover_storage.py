"""Pytest-Unit-Tests für ``accounts/discover_storage.py`` (Discover-Events-MVP).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.discover_storage as discover_storage
import accounts.discovery_storage as discovery_storage
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import DiscoverAction, PartyRole, RsvpStatus


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "discover_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    discover_storage.init_discover_storage(path)
    discovery_storage.init_discovery_storage(path)
    return path


@pytest.fixture()
def host(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "host@example.com", "hash", "Host")


@pytest.fixture()
def guest(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "guest@example.com", "hash", "Guest")


@pytest.fixture()
def party(db_path, host):
    return party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Rooftop Rave", location="Berlin")


def test_init_ist_idempotent(db_path):
    discover_storage.init_discover_storage(db_path)
    discover_storage.init_discover_storage(db_path)


def test_get_publication_unbekannt_gibt_none(db_path, party):
    assert discover_storage.get_publication(db_path, party.id) is None


def test_publish_und_unpublish(db_path, party):
    publication = discover_storage.publish_party(db_path, party.id, event_type="club_event", interest_tags=["techno"])
    assert publication.event_type == "club_event"
    assert publication.interest_tags == ["techno"]
    assert discover_storage.get_publication(db_path, party.id) is not None

    discover_storage.unpublish_party(db_path, party.id)
    assert discover_storage.get_publication(db_path, party.id) is None


def test_republish_aktualisiert_statt_zu_duplizieren(db_path, party):
    discover_storage.publish_party(db_path, party.id, event_type="club_event", interest_tags=["techno"])
    discover_storage.publish_party(db_path, party.id, event_type="rave", interest_tags=["outdoor"])
    updated = discover_storage.get_publication(db_path, party.id)
    assert updated.event_type == "rave"
    assert updated.interest_tags == ["outdoor"]


def test_list_candidate_publications_schliesst_eigene_party_aus(db_path, host, party):
    discover_storage.publish_party(db_path, party.id)
    assert discover_storage.list_candidate_publications(db_path, host.id) == []


def test_list_candidate_publications_schliesst_bereits_mitglied_aus(db_path, guest, party):
    discover_storage.publish_party(db_path, party.id)
    assert len(discover_storage.list_candidate_publications(db_path, guest.id)) == 1

    party_storage.upsert_membership(db_path, party.id, guest.id, PartyRole.GUEST, RsvpStatus.ACCEPTED)
    assert discover_storage.list_candidate_publications(db_path, guest.id) == []


def test_list_candidate_publications_schliesst_bereits_geswiped_aus(db_path, guest, party):
    discover_storage.publish_party(db_path, party.id)
    discover_storage.upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party.id, DiscoverAction.NOT_INTERESTED)
    assert discover_storage.list_candidate_publications(db_path, guest.id) == []


def test_upsert_discover_action_ist_ein_echtes_upsert(db_path, guest, party):
    discover_storage.publish_party(db_path, party.id)
    discover_storage.upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party.id, DiscoverAction.MAYBE)
    discover_storage.upsert_discover_action(db_path, uuid.uuid4().hex, guest.id, party.id, DiscoverAction.GOING)
    action = discover_storage.get_discover_action(db_path, guest.id, party.id)
    assert action.action == DiscoverAction.GOING


def test_get_discover_deck_liefert_score_pro_kandidat(db_path, guest, party):
    discover_storage.publish_party(db_path, party.id, event_type="club_event")
    deck = discover_storage.get_discover_deck(db_path, guest.id)
    assert len(deck) == 1
    ranked_party, publication, score = deck[0]
    assert ranked_party.id == party.id
    assert publication.event_type == "club_event"
    assert 0.0 < score <= 1.0
