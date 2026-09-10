"""Pytest-Unit-Tests für ``social.search`` (Social-Graph-Phase-1/3/6).
Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul selbst um eine
pytest-Variante (isolierte ``tmp_path``-DB)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

import accounts.discover_storage as discover_storage
import accounts.party_storage as party_storage
import accounts.profile_storage as profile_storage
import accounts.user_storage as user_storage
import organizers.storage as organizers_storage
import social.search as search
from organizers.domain import OrganizerVerificationStatus


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "search_test.db"
    user_storage.init_user_storage(path)
    profile_storage.init_profile_storage(path)
    party_storage.init_party_storage(path)
    organizers_storage.init_organizer_storage(path)
    discover_storage.init_discover_storage(path)
    return path


@pytest.fixture()
def me(db_path):
    return user_storage.create_user(db_path, uuid.uuid4().hex, "me@example.com", "hash", "Me")


def _make_user(db_path, email, display_name, username=None, **privacy):
    user = user_storage.create_user(db_path, uuid.uuid4().hex, email, "hash", display_name)
    profile_storage.upsert_user_profile(db_path, user.id, birth_date=date(1990, 1, 1), username=username, **privacy)
    return user


def _make_verified_organizer(db_path, owner_id, display_name):
    org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, owner_id, display_name)
    organizers_storage.set_verification_status(db_path, org.id, OrganizerVerificationStatus.VERIFIED)
    return org


# --- Social-Graph-Phase-1/3: User-Suche ---------------------------------


def test_search_findet_per_username(db_path, me):
    target = _make_user(db_path, "target@example.com", "Target Person", username="TargetHandle")
    results = search.search_users(db_path, "targethandle", exclude_user_id=me.id)
    assert any(r.user_id == target.id for r in results)


def test_search_findet_per_display_name(db_path, me):
    target = _make_user(db_path, "target2@example.com", "Very Unique Name")
    results = search.search_users(db_path, "Very Unique", exclude_user_id=me.id)
    assert any(r.user_id == target.id for r in results)


def test_search_discoverable_by_username_false_versteckt_nur_username_treffer(db_path, me):
    target = _make_user(
        db_path, "target3@example.com", "Hidden Handle Person", username="hiddenhandle123",
        discoverable_by_username=False,
    )
    assert not any(r.user_id == target.id for r in search.search_users(db_path, "hiddenhandle123", exclude_user_id=me.id))
    assert any(r.user_id == target.id for r in search.search_users(db_path, "Hidden Handle", exclude_user_id=me.id))


def test_search_discoverable_by_name_false_versteckt_nur_name_treffer(db_path, me):
    target = _make_user(
        db_path, "target4@example.com", "Secret Name Person", username="opennhandle456",
        discoverable_by_name=False,
    )
    assert not any(r.user_id == target.id for r in search.search_users(db_path, "Secret Name", exclude_user_id=me.id))
    assert any(r.user_id == target.id for r in search.search_users(db_path, "opennhandle456", exclude_user_id=me.id))


def test_search_beide_toggles_aus_macht_user_vollstaendig_unsichtbar(db_path, me):
    _make_user(
        db_path, "target5@example.com", "Totally Hidden Person", username="totallyhidden789",
        discoverable_by_username=False, discoverable_by_name=False,
    )
    assert search.search_users(db_path, "totallyhidden789", exclude_user_id=me.id) == []
    assert search.search_users(db_path, "Totally Hidden", exclude_user_id=me.id) == []


def test_search_user_ohne_profil_ist_per_default_discoverable(db_path, me):
    target = user_storage.create_user(db_path, uuid.uuid4().hex, "noprofile@example.com", "hash", "No Profile Person")
    results = search.search_users(db_path, "No Profile", exclude_user_id=me.id)
    assert any(r.user_id == target.id for r in results)


def test_search_treffer_in_beiden_zweigen_wird_nicht_dupliziert(db_path, me):
    target = _make_user(db_path, "target6@example.com", "Overlap Overlap", username="overlapoverlap")
    results = search.search_users(db_path, "overlap", exclude_user_id=me.id)
    assert len([r for r in results if r.user_id == target.id]) == 1


def test_search_limit_wirkt_auf_kombiniertes_ergebnis(db_path, me):
    for i in range(5):
        _make_user(db_path, f"limituser{i}@example.com", f"LimitMatch Person {i}", username=f"limitmatch{i}")
    results = search.search_users(db_path, "limitmatch", exclude_user_id=me.id, limit=3)
    assert len(results) == 3


# --- Social-Graph-Phase-6: Organizer-Suche -----------------------------


def test_search_organizers_findet_verifizierten_per_teilname_case_insensitiv(db_path, me):
    org = _make_verified_organizer(db_path, me.id, "Boiler Room")
    results = search.search_organizers(db_path, "boiler")
    assert [r.organizer_id for r in results] == [org.id]
    assert results[0].owner_user_id == me.id
    assert results[0].verification_status == "verified"


@pytest.mark.parametrize(
    "status",
    [
        OrganizerVerificationStatus.UNVERIFIED,
        OrganizerVerificationStatus.PENDING,
        OrganizerVerificationStatus.SUSPENDED,
        OrganizerVerificationStatus.REJECTED,
    ],
)
def test_search_organizers_ignoriert_nicht_verifizierte(db_path, me, status):
    org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, me.id, "Nightclub XYZ")
    organizers_storage.set_verification_status(db_path, org.id, status)
    assert search.search_organizers(db_path, "nightclub") == []


def test_search_organizers_escaped_wildcards(db_path, me):
    # SQL-Wildcards im Query werden escaped, nicht als "matche alles" interpretiert.
    _make_verified_organizer(db_path, me.id, "Boiler Room")
    assert search.search_organizers(db_path, "%") == []
    assert search.search_organizers(db_path, "_") == []


def test_search_organizers_kein_treffer_leere_liste(db_path, me):
    _make_verified_organizer(db_path, me.id, "Boiler Room")
    assert search.search_organizers(db_path, "nonexistent") == []


def test_search_organizers_sortiert_nach_display_name_und_limit(db_path, me):
    for name in ["Club Delta", "Club Alpha", "Club Charlie", "Club Bravo"]:
        _make_verified_organizer(db_path, me.id, name)
    results = search.search_organizers(db_path, "club", limit=2)
    assert [r.display_name for r in results] == ["Club Alpha", "Club Bravo"]


# --- Social-Graph-Phase-6: Event-Suche --------------------------------


def test_search_public_events_findet_veroeffentlichte_per_teilname(db_path, me):
    party = party_storage.create_party(db_path, uuid.uuid4().hex, me.id, "Summer Sound Festival")
    discover_storage.publish_party(db_path, party.id, event_type="festival")
    results = search.search_public_events(db_path, "summer sound")
    assert [r.party_id for r in results] == [party.id]
    assert results[0].host_user_id == me.id
    assert results[0].event_type == "festival"


def test_search_public_events_ignoriert_unveroeffentlichte(db_path, me):
    party_storage.create_party(db_path, uuid.uuid4().hex, me.id, "Private Kitchen Party")
    assert search.search_public_events(db_path, "kitchen") == []


def test_search_public_events_verschwindet_nach_unpublish(db_path, me):
    party = party_storage.create_party(db_path, uuid.uuid4().hex, me.id, "Rooftop Rave")
    discover_storage.publish_party(db_path, party.id)
    assert len(search.search_public_events(db_path, "rooftop")) == 1
    discover_storage.unpublish_party(db_path, party.id)
    assert search.search_public_events(db_path, "rooftop") == []


def test_search_public_events_neueste_zuerst_und_limit(db_path, me):
    ids = []
    for name in ["Alpha Night", "Beta Night", "Gamma Night"]:
        p = party_storage.create_party(db_path, uuid.uuid4().hex, me.id, name)
        discover_storage.publish_party(db_path, p.id)
        ids.append(p.id)
    results = search.search_public_events(db_path, "night", limit=2)
    # published_at DESC -> zuletzt veröffentlichte (Gamma, Beta) zuerst
    assert [r.party_id for r in results] == [ids[2], ids[1]]


def test_search_public_events_escaped_wildcards(db_path, me):
    # SQL-Wildcards im Query werden escaped, nicht als "matche alles" interpretiert.
    p = party_storage.create_party(db_path, uuid.uuid4().hex, me.id, "Rooftop Rave")
    discover_storage.publish_party(db_path, p.id)
    assert search.search_public_events(db_path, "%") == []
    assert search.search_public_events(db_path, "_") == []
