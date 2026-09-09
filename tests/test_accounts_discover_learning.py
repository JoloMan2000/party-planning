"""Pytest-Unit-Tests für ``accounts/discover_learning.py`` (Discover-Engine-
Phase-1, Exposure-Tracking-Ausbaustufe). Ergänzt den ausführbaren
``__main__``-Selbsttest im Modul selbst um eine pytest-Variante (isolierte
``tmp_path``-DB)."""

from __future__ import annotations

import uuid

import pytest

import accounts.discover_learning as discover_learning
import accounts.party_storage as party_storage
import accounts.user_storage as user_storage
from accounts.domain import DiscoverAction, DiscoverNotInterestedReason, PublicEvent


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "discover_learning_test.db"
    user_storage.init_user_storage(path)
    party_storage.init_party_storage(path)
    discover_learning.init_discover_learning_storage(path)
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
    discover_learning.init_discover_learning_storage(db_path)
    discover_learning.init_discover_learning_storage(db_path)


def test_ohne_exposures_leere_liste(db_path, guest):
    assert discover_learning.list_exposures_for_user(db_path, guest.id) == []


def test_record_exposures_schreibt_eine_zeile_pro_kandidat(db_path, guest, party):
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 0)])
    exposures = discover_learning.list_exposures_for_user(db_path, guest.id)
    assert len(exposures) == 1
    assert exposures[0].user_id == guest.id
    assert exposures[0].party_id == party.id
    assert exposures[0].rank == 0
    assert exposures[0].model_version == discover_learning.CURRENT_MODEL_VERSION


def test_record_exposures_batch_mehrere_kandidaten(db_path, guest, host, party):
    party2 = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Beach Party")
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 0), (party2.id, 1)])
    exposures = discover_learning.list_exposures_for_user(db_path, guest.id)
    assert len(exposures) == 2
    assert {e.party_id for e in exposures} == {party.id, party2.id}


def test_record_exposures_leere_liste_ist_no_op(db_path, guest):
    discover_learning.record_exposures(db_path, guest.id, [])
    assert discover_learning.list_exposures_for_user(db_path, guest.id) == []


def test_record_exposures_kein_dedup_dieselbe_party_zweimal_gezeigt(db_path, guest, party):
    """Jeder Deck-Abruf ist ein eigenes Exposure-Ereignis, auch für
    dieselbe Party (kein "schon gezeigt"-Dedup) - siehe Modul-Docstring."""
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 0)])
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 2)])
    exposures = discover_learning.list_exposures_for_user(db_path, guest.id)
    assert len(exposures) == 2
    assert sorted(e.rank for e in exposures) == [0, 2]


def test_record_exposures_custom_model_version(db_path, guest, party):
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 0)], model_version="test-model-v0")
    exposures = discover_learning.list_exposures_for_user(db_path, guest.id)
    assert exposures[0].model_version == "test-model-v0"


def test_list_exposures_filtert_nach_party(db_path, guest, host, party):
    party2 = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Beach Party")
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 0), (party2.id, 1)])
    exposures = discover_learning.list_exposures_for_user(db_path, guest.id, party_id=party.id)
    assert len(exposures) == 1
    assert exposures[0].party_id == party.id


def test_list_exposures_isoliert_pro_user(db_path, guest, host, party):
    other_guest = user_storage.create_user(db_path, uuid.uuid4().hex, "other@example.com", "hash", "Other")
    discover_learning.record_exposures(db_path, guest.id, [(party.id, 0)])
    assert discover_learning.list_exposures_for_user(db_path, other_guest.id) == []


def test_ohne_block_leere_menge(db_path, guest):
    assert discover_learning.get_blocked_organizer_ids(db_path, guest.id) == set()


def test_block_organizer_fuegt_id_hinzu(db_path, guest, host):
    blocked = discover_learning.block_organizer(db_path, guest.id, host.id)
    assert blocked.user_id == guest.id
    assert blocked.organizer_user_id == host.id
    assert discover_learning.get_blocked_organizer_ids(db_path, guest.id) == {host.id}


def test_block_organizer_ist_idempotent(db_path, guest, host):
    first = discover_learning.block_organizer(db_path, guest.id, host.id)
    second = discover_learning.block_organizer(db_path, guest.id, host.id)
    assert first.id == second.id
    assert discover_learning.get_blocked_organizer_ids(db_path, guest.id) == {host.id}


def test_block_organizer_isoliert_pro_user(db_path, guest, host):
    other_guest = user_storage.create_user(db_path, uuid.uuid4().hex, "other@example.com", "hash", "Other")
    discover_learning.block_organizer(db_path, guest.id, host.id)
    assert discover_learning.get_blocked_organizer_ids(db_path, other_guest.id) == set()


def test_unblock_organizer_entfernt_block(db_path, guest, host):
    discover_learning.block_organizer(db_path, guest.id, host.id)
    discover_learning.unblock_organizer(db_path, guest.id, host.id)
    assert discover_learning.get_blocked_organizer_ids(db_path, guest.id) == set()


def test_unblock_organizer_ohne_bestehenden_block_ist_no_op(db_path, guest, host):
    discover_learning.unblock_organizer(db_path, guest.id, host.id)
    assert discover_learning.get_blocked_organizer_ids(db_path, guest.id) == set()


# --- Learned Affinity (Build-Schritt 4) ---------------------------------


def test_get_learned_affinity_cold_start_gibt_none(db_path, guest):
    assert discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "club_event") is None


def test_apply_signal_erstes_signal_setzt_value_direkt(db_path, guest):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    fit, count = discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "club_event")
    assert abs(fit - 1.0) < 0.001
    assert count == 1.0


def test_apply_signal_blendet_zweites_signal_gewichtet_ein(db_path, guest):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=0.0, weight=1.0)
    fit, count = discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "club_event")
    assert abs(fit - 0.5) < 0.001  # gleich gewichtet -> Mittelwert von 1.0 und 0.0
    assert count == 2.0


def test_apply_signal_isoliert_pro_attribut(db_path, guest):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    assert discover_learning.get_learned_affinity(db_path, guest.id, "interest_tag", "club_event") is None
    assert discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "house_party") is None


def test_apply_signal_isoliert_pro_user(db_path, guest, host):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    assert discover_learning.get_learned_affinity(db_path, host.id, "event_type", "club_event") is None


def test_get_learned_affinity_decay_naehert_sich_neutralwert(db_path, guest):
    import datetime as dt

    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=discover_learning.AFFINITY_HALF_LIFE_DAYS)
    decayed_fit, decayed_count = discover_learning.get_learned_affinity(
        db_path, guest.id, "event_type", "club_event", now=far_future
    )
    assert abs(decayed_fit - 0.75) < 0.01  # halbe Auslenkung von 1.0 nach einer Halbwertszeit
    assert decayed_count == 1.0  # observation_count decayed nicht


def test_record_signal_from_action_going_erzeugt_signal_pro_attribut(db_path, guest, party):
    publication = PublicEvent(id="pe-1", party_id=party.id, event_type="club_event", interest_tags=["techno", "outdoor"])
    signals = discover_learning.record_signal_from_action(db_path, guest.id, publication, DiscoverAction.GOING)
    assert len(signals) == 3  # event_type + 2 interest_tags
    fit, _ = discover_learning.get_learned_affinity(db_path, guest.id, "interest_tag", "outdoor")
    assert abs(fit - 1.0) < 0.001


def test_record_signal_from_action_ohne_interest_tags_nur_event_type_signal(db_path, guest, party):
    publication = PublicEvent(id="pe-1", party_id=party.id, event_type="club_event", interest_tags=[])
    signals = discover_learning.record_signal_from_action(db_path, guest.id, publication, DiscoverAction.GOING)
    assert len(signals) == 1


def test_record_signal_from_action_not_interested_wrong_vibe_ist_stark_negativ(db_path, guest, party):
    publication = PublicEvent(id="pe-1", party_id=party.id, event_type="cultural_event", interest_tags=[])
    discover_learning.record_signal_from_action(
        db_path, guest.id, publication, DiscoverAction.NOT_INTERESTED,
        reason=DiscoverNotInterestedReason.WRONG_VIBE.value,
    )
    fit, _ = discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "cultural_event")
    assert abs(fit - 0.1) < 0.001


def test_record_signal_from_action_not_interested_ohne_grund_ist_schwach_negativ(db_path, guest, party):
    publication = PublicEvent(id="pe-1", party_id=party.id, event_type="cultural_event", interest_tags=[])
    discover_learning.record_signal_from_action(db_path, guest.id, publication, DiscoverAction.NOT_INTERESTED)
    fit, count = discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "cultural_event")
    assert abs(fit - 0.3) < 0.001
    assert count == 0.5


@pytest.mark.parametrize(
    "reason",
    [
        DiscoverNotInterestedReason.TOO_FAR.value,
        DiscoverNotInterestedReason.BAD_TIMING.value,
        DiscoverNotInterestedReason.NOT_INTERESTED_IN_ORGANIZER.value,
        DiscoverNotInterestedReason.OTHER.value,
    ],
)
def test_record_signal_from_action_non_attribute_reasons_erzeugen_kein_signal(db_path, guest, party, reason):
    publication = PublicEvent(id="pe-1", party_id=party.id, event_type="cultural_event", interest_tags=["jazz"])
    signals = discover_learning.record_signal_from_action(
        db_path, guest.id, publication, DiscoverAction.NOT_INTERESTED, reason=reason
    )
    assert signals == []
    assert discover_learning.get_learned_affinity(db_path, guest.id, "event_type", "cultural_event") is None
    assert discover_learning.get_learned_affinity(db_path, guest.id, "interest_tag", "jazz") is None


def test_get_learned_affinities_for_user_bulk_fetch(db_path, guest):
    assert discover_learning.get_learned_affinities_for_user(db_path, guest.id) == {}
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    discover_learning.apply_signal(db_path, guest.id, "interest_tag", "techno", target_fit=0.8, weight=0.5)
    bulk = discover_learning.get_learned_affinities_for_user(db_path, guest.id)
    assert set(bulk.keys()) == {("event_type", "club_event"), ("interest_tag", "techno")}
    assert abs(bulk[("event_type", "club_event")][0] - 1.0) < 0.001
    assert bulk[("interest_tag", "techno")][1] == 0.5


def test_get_learned_affinities_for_user_isoliert_pro_user(db_path, guest, host):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    assert discover_learning.get_learned_affinities_for_user(db_path, host.id) == {}


# --- Reset Learning (Build-Schritt 8) -----------------------------------


def test_reset_learned_profile_loescht_learned_affinity(db_path, guest):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    discover_learning.reset_learned_profile(db_path, guest.id)
    assert discover_learning.get_learned_affinities_for_user(db_path, guest.id) == {}


def test_reset_learned_profile_laesst_blocked_organizers_unangetastet(db_path, guest, host):
    discover_learning.block_organizer(db_path, guest.id, host.id)
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    discover_learning.reset_learned_profile(db_path, guest.id)
    assert discover_learning.get_blocked_organizer_ids(db_path, guest.id) == {host.id}


def test_reset_learned_profile_isoliert_pro_user(db_path, guest, host):
    discover_learning.apply_signal(db_path, guest.id, "event_type", "club_event", target_fit=1.0, weight=1.0)
    discover_learning.apply_signal(db_path, host.id, "event_type", "cultural_event", target_fit=1.0, weight=1.0)
    discover_learning.reset_learned_profile(db_path, guest.id)
    assert discover_learning.get_learned_affinities_for_user(db_path, guest.id) == {}
    assert discover_learning.get_learned_affinities_for_user(db_path, host.id) != {}


def test_reset_learned_profile_ohne_bestehende_signale_ist_no_op(db_path, guest):
    discover_learning.reset_learned_profile(db_path, guest.id)
    assert discover_learning.get_learned_affinities_for_user(db_path, guest.id) == {}
