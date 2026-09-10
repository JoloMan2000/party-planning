"""Pytest-Unit-Tests für ``accounts.account_deletion`` (Social-Graph-
Phase-10, Spec §104). Ergänzt den ``__main__``-Selbsttest um eine
pytest-Variante (isolierte ``tmp_path``-DB, alle Tabellen initialisiert)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date

import pytest

import accounts.account_deletion as account_deletion
import accounts.discover_learning as discover_learning
import accounts.discover_storage as discover_storage
import accounts.discovery_storage as discovery_storage
import accounts.invitation_storage as invitation_storage
import accounts.notification_settings_storage as notification_settings_storage
import accounts.notification_storage as notification_storage
import accounts.party_storage as party_storage
import accounts.profile_storage as profile_storage
import accounts.spotify_storage as spotify_storage
import accounts.user_storage as user_storage
import event_theme
import geo.storage as geo_storage
import music_engine.admin_settings as music_admin_settings
import organizers.storage as organizers_storage
import party_engine.response_storage as response_storage
import social.blocks as blocks
import social.follows as follows
import social.friend_requests as friend_requests
import social.friendships as friendships
from accounts.domain import DiscoverAction, PartyRole, RsvpStatus
from organizers.domain import OrganizerRole, OrganizerVerificationStatus
from party_context import learning_storage
from party_context import storage as party_context_storage
from party_engine.catalog_curation import init_catalog_curation


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "account_deletion_test.db"
    for init in (
        user_storage.init_user_storage,
        party_storage.init_party_storage,
        organizers_storage.init_organizer_storage,
        invitation_storage.init_invitation_storage,
        notification_storage.init_notifications,
        notification_settings_storage.init_notification_settings_storage,
        profile_storage.init_profile_storage,
        blocks.init_block_storage,
        friendships.init_friendship_storage,
        friend_requests.init_friend_request_storage,
        follows.init_follow_storage,
        discovery_storage.init_discovery_storage,
        discover_storage.init_discover_storage,
        discover_learning.init_discover_learning_storage,
        spotify_storage.init_spotify_storage,
        event_theme.init_party_settings,
        music_admin_settings.init_music_admin_settings,
        party_context_storage.init_party_context_storage,
        learning_storage.init_learning_storage,
        init_catalog_curation,
        response_storage.init_db,
        geo_storage.init_geo_storage,
    ):
        init(path)
    return path


def _count(db_path, sql, params):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchone()[0]


def test_delete_account_entfernt_alles_und_laesst_andere_user_unangetastet(db_path):
    a = user_storage.create_user(db_path, uuid.uuid4().hex, "a@example.com", "hash", "A")
    b = user_storage.create_user(db_path, uuid.uuid4().hex, "b@example.com", "hash", "B")
    c = user_storage.create_user(db_path, uuid.uuid4().hex, "c@example.com", "hash", "C")

    # A's Fußabdruck
    a_party = party_storage.create_party(db_path, uuid.uuid4().hex, a.id, "A Fest")
    party_storage.upsert_membership(db_path, a_party.id, b.id, PartyRole.GUEST, RsvpStatus.ACCEPTED)
    invitation_storage.create_invitation(db_path, uuid.uuid4().hex, a_party.id, a.id, b.id)
    discover_storage.publish_party(db_path, a_party.id, event_type="club_event")
    discover_storage.upsert_discover_action(db_path, uuid.uuid4().hex, b.id, a_party.id, DiscoverAction.GOING)
    a_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, a.id, "A Events")
    organizers_storage.set_verification_status(db_path, a_org.id, OrganizerVerificationStatus.VERIFIED)
    organizers_storage.upsert_membership(db_path, a_org.id, b.id, OrganizerRole.EDITOR)
    follows.follow_organizer(db_path, uuid.uuid4().hex, b.id, a_org.id)
    follows.follow_event(db_path, uuid.uuid4().hex, b.id, a_party.id)
    profile_storage.upsert_user_profile(db_path, a.id, birth_date=date(1990, 1, 1), username="alpha")
    notification_storage.create_notification(db_path, uuid.uuid4().hex, a.id, a_party.id, "invitation", "hi")
    notification_settings_storage.upsert_notification_settings(
        db_path, a.id, friend_requests=False, party_invitations=True, organizer_updates=True,
        followed_event_updates=True, nearby_discover=True,
    )
    friendships.create_friendship(db_path, uuid.uuid4().hex, a.id, b.id)
    friend_requests.create_friend_request(db_path, uuid.uuid4().hex, a.id, c.id)  # A -> C pending
    with sqlite3.connect(db_path) as seed:
        seed.execute(
            "INSERT INTO refresh_tokens (id, user_id, token_hash, issued_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, a.id, "h", "2026-01-01", "2027-01-01"),
        )
        seed.execute(
            "INSERT INTO party_runs (host_user_id, started_at) VALUES (?, ?)", (a.id, "2026-01-01")
        )
        run_id = seed.execute("SELECT id FROM party_runs WHERE host_user_id = ?", (a.id,)).fetchone()[0]
        seed.execute(
            "INSERT INTO selection_events (party_run_id, item_id, item_type) VALUES (?, ?, ?)", (run_id, "x", "drink")
        )
        seed.execute("INSERT INTO login_attempts (email, updated_at) VALUES (?, ?)", ("a@example.com", "2026-01-01"))

    # B's eigener Fußabdruck (muss bleiben)
    b_party = party_storage.create_party(db_path, uuid.uuid4().hex, b.id, "B Fest")
    b_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, b.id, "B Events")
    profile_storage.upsert_user_profile(db_path, b.id, birth_date=date(1991, 2, 2), username="bravo")

    account_deletion.delete_account(db_path, a.id)

    assert _count(db_path, "SELECT COUNT(*) FROM users WHERE id = ?", (a.id,)) == 0
    for table, col in (
        ("refresh_tokens", "user_id"), ("user_profiles", "user_id"), ("notifications", "user_id"),
        ("notification_settings", "user_id"), ("party_runs", "host_user_id"),
        ("organizer_memberships", "user_id"), ("organizer_follows", "user_id"),
        ("event_follows", "user_id"), ("discover_actions", "user_id"),
    ):
        assert _count(db_path, f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (a.id,)) == 0, table
    assert _count(db_path, "SELECT COUNT(*) FROM parties WHERE host_user_id = ?", (a.id,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM organizers WHERE owner_user_id = ?", (a.id,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM party_memberships WHERE party_id = ?", (a_party.id,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM public_events WHERE party_id = ?", (a_party.id,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM invitations WHERE invited_user_id = ?", (b.id,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM friendships WHERE user_a_id = ? OR user_b_id = ?", (a.id, a.id)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM friend_requests WHERE sender_id = ? OR receiver_id = ?", (a.id, a.id)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM login_attempts WHERE email = ?", ("a@example.com",)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM selection_events", ()) == 0

    # B unangetastet
    assert _count(db_path, "SELECT COUNT(*) FROM users WHERE id = ?", (b.id,)) == 1
    assert _count(db_path, "SELECT COUNT(*) FROM parties WHERE id = ?", (b_party.id,)) == 1
    assert _count(db_path, "SELECT COUNT(*) FROM organizers WHERE id = ?", (b_org.id,)) == 1
    assert _count(db_path, "SELECT COUNT(*) FROM user_profiles WHERE user_id = ?", (b.id,)) == 1


def test_delete_account_ist_idempotent(db_path):
    a = user_storage.create_user(db_path, uuid.uuid4().hex, "solo@example.com", "hash", "Solo")
    account_deletion.delete_account(db_path, a.id)
    account_deletion.delete_account(db_path, a.id)  # No-Op, kein Fehler
    account_deletion.delete_account(db_path, "never-existed")  # No-Op
    assert _count(db_path, "SELECT COUNT(*) FROM users", ()) == 0
