"""Account-Löschung (Social-Graph-Phase-10, AUFGABE-Spec §104).

Hard-Delete des KOMPLETTEN Fußabdrucks eines Users in EINER Transaktion -
kein Tombstone, keine Anonymisierung (dieses Demo/Dev-Projekt hat keine
echte Retention-Policy; die FK-Constraints in den DDLs sind ohnehin inert,
da ``PRAGMA foreign_keys`` nie eingeschaltet wird).

Löscht auch die vom User GEHOSTETEN Parties samt aller ~18
``party_id``-verketteten Tabellen und die ihm GEHÖRENDEN Organizer samt
Memberships/Follows - Co-Hosts, Gäste und andere Organizer-Mitglieder
verlieren den Zugriff ohne Benachrichtigung (bewusste, dokumentierte
Scope-Entscheidung).

Roh-SQL statt Aufrufe der Domain-Storage-Module: jene öffnen eigene
Connections und würden die eine Transaktion aufbrechen (gleiche Begründung
wie ``social/blocks.py::block_user``). Reihenfolge Kinder -> Eltern (bei
ausgeschalteten FKs egal, aber sauber und zukunftssicher)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Tabellen, deren Zeilen zu einer vom User GEHOSTETEN Party gehören
# (``WHERE party_id IN (SELECT id FROM parties WHERE host_user_id = ?)``).
_PARTY_SCOPED_TABLES = (
    "party_memberships",
    "invitations",
    "rsvp_history",
    "public_events",
    "discover_actions",
    "event_recommendation_exposures",
    "event_follows",
    "party_locations",
    "party_settings",
    "party_context",
    "party_context_override",
    "weather_snapshot",
    "catalog_curation_settings",
    "catalog_curated_items",
    "music_admin_settings",
    "music_track_overrides",
    "music_artist_overrides",
    "responses",
)

# Tabellen, deren Zeilen zu einem vom User GEHÖRENDEN Organizer gehören.
_ORGANIZER_SCOPED_TABLES = ("organizer_memberships", "organizer_follows")

# Rein persönliche / einseitige Zeilen, direkt an ``user_id`` gekettet.
_USER_SCOPED_STATEMENTS = (
    "DELETE FROM refresh_tokens WHERE user_id = ?",
    "DELETE FROM password_reset_tokens WHERE user_id = ?",
    "DELETE FROM email_verification_tokens WHERE user_id = ?",
    "DELETE FROM account_unlock_tokens WHERE user_id = ?",
    "DELETE FROM user_profiles WHERE user_id = ?",
    "DELETE FROM birth_date_corrections WHERE user_id = ?",
    "DELETE FROM user_discovery_preferences WHERE user_id = ?",
    "DELETE FROM user_music_preferences WHERE user_id = ?",
    "DELETE FROM user_artist_preferences WHERE user_id = ?",
    "DELETE FROM explicit_discovery_preferences WHERE user_id = ?",
    "DELETE FROM learned_affinity_signals WHERE user_id = ?",
    "DELETE FROM spotify_oauth_states WHERE user_id = ?",
    "DELETE FROM spotify_connections WHERE user_id = ?",
    "DELETE FROM notifications WHERE user_id = ?",
    "DELETE FROM notification_settings WHERE user_id = ?",
    # Die eigene Seite von Dingen, die zu FREMDEN Parties/Organizern gehören
    # (die party-/organizer-scoped Sweeps oben treffen nur meine eigenen).
    "DELETE FROM discover_actions WHERE user_id = ?",
    "DELETE FROM event_recommendation_exposures WHERE user_id = ?",
    "DELETE FROM party_memberships WHERE user_id = ?",
    "DELETE FROM organizer_memberships WHERE user_id = ?",
    "DELETE FROM event_follows WHERE user_id = ?",
    "DELETE FROM organizer_follows WHERE user_id = ?",
)

# Zwei-User-Beziehungszeilen: löschen, egal auf welcher Seite der User steht.
_RELATIONAL_STATEMENTS = (
    "DELETE FROM friendships WHERE user_a_id = ? OR user_b_id = ?",
    "DELETE FROM friend_requests WHERE sender_id = ? OR receiver_id = ?",
    "DELETE FROM user_blocks WHERE blocker_id = ? OR blocked_id = ?",
    "DELETE FROM blocked_organizers WHERE user_id = ? OR organizer_user_id = ?",
    "DELETE FROM invitations WHERE host_user_id = ? OR invited_user_id = ?",
    "DELETE FROM rsvp_history WHERE user_id = ? OR changed_by_user_id = ?",
)


def delete_account(db_path: str | Path, user_id: str) -> None:
    """Irreversibler Hard-Delete des gesamten Datenbestands zu ``user_id``.
    Idempotent - ein zweiter Aufruf für einen bereits gelöschten User ist
    ein No-Op."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return
        email = row[0]

        # 1. Party-Context-ML (kein FK, an host_user_id gekettet).
        conn.execute(
            "DELETE FROM selection_events WHERE party_run_id IN "
            "(SELECT id FROM party_runs WHERE host_user_id = ?)",
            (user_id,),
        )
        conn.execute("DELETE FROM party_runs WHERE host_user_id = ?", (user_id,))

        # 2. Alles, was an einer vom User gehosteten Party hängt.
        for table in _PARTY_SCOPED_TABLES:
            conn.execute(
                f"DELETE FROM {table} WHERE party_id IN (SELECT id FROM parties WHERE host_user_id = ?)",
                (user_id,),
            )

        # 3. Alles, was an einem vom User gehörenden Organizer hängt.
        for table in _ORGANIZER_SCOPED_TABLES:
            conn.execute(
                f"DELETE FROM {table} WHERE organizer_id IN (SELECT id FROM organizers WHERE owner_user_id = ?)",
                (user_id,),
            )

        # 4. Die Eltern-Zeilen selbst.
        conn.execute("DELETE FROM parties WHERE host_user_id = ?", (user_id,))
        conn.execute("DELETE FROM organizers WHERE owner_user_id = ?", (user_id,))

        # 5. Rein persönliche / einseitige Zeilen.
        for stmt in _USER_SCOPED_STATEMENTS:
            conn.execute(stmt, (user_id,))

        # 6. Zwei-User-Beziehungszeilen.
        for stmt in _RELATIONAL_STATEMENTS:
            conn.execute(stmt, (user_id, user_id))

        # 7. Lockout-Zeile (per E-Mail-String gekettet, kein user_id).
        conn.execute("DELETE FROM login_attempts WHERE email = ?", (email,))

        # 8. Der User selbst.
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


if __name__ == "__main__":
    import tempfile
    import uuid
    from datetime import date

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

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_account_deletion.db"
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
            init(db_path)

        a = user_storage.create_user(db_path, uuid.uuid4().hex, "a@example.com", "hash", "A")
        b = user_storage.create_user(db_path, uuid.uuid4().hex, "b@example.com", "hash", "B")

        # --- A's Fußabdruck ---
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
        discovery_storage.upsert_discovery_preferences(
            db_path, a.id, discovery_storage.UserDiscoveryPreferences(user_id=a.id, discovery_city="Berlin")
        )
        notification_storage.create_notification(db_path, uuid.uuid4().hex, a.id, a_party.id, "invitation", "hi")
        notification_settings_storage.upsert_notification_settings(
            db_path, a.id, friend_requests=False, party_invitations=True, organizer_updates=True,
            followed_event_updates=True, nearby_discover=True,
        )
        discover_learning.record_signal_from_action  # noqa: B018 - nur Referenz, dass das Modul importiert ist

        # A <-> B Beziehungen.
        friendships.create_friendship(db_path, uuid.uuid4().hex, a.id, b.id)
        blocks.block_user  # noqa: B018

        # Raw INSERTs für Tabellen ohne bequeme Helper.
        with sqlite3.connect(db_path) as seed:
            seed.execute(
                "INSERT INTO refresh_tokens (id, user_id, token_hash, issued_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, a.id, "h", "2026-01-01", "2027-01-01"),
            )
            seed.execute(
                "INSERT INTO learned_affinity_signals "
                "(id, user_id, attribute_category, attribute_value, value, observation_count, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, a.id, "event_type", "club_event", 0.7, 3.0, "2026-01-01"),
            )
            seed.execute(
                "INSERT INTO party_runs (host_user_id, started_at) VALUES (?, ?)", (a.id, "2026-01-01")
            )
            run_id = seed.execute("SELECT id FROM party_runs WHERE host_user_id = ?", (a.id,)).fetchone()[0]
            seed.execute(
                "INSERT INTO selection_events (party_run_id, item_id, item_type) VALUES (?, ?, ?)",
                (run_id, "x", "drink"),
            )
            seed.execute(
                "INSERT INTO party_locations (id, party_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex, a_party.id, "2026-01-01", "2026-01-01"),
            )
            seed.execute(
                "INSERT INTO login_attempts (email, updated_at) VALUES (?, ?)", ("a@example.com", "2026-01-01")
            )

        # --- B's eigener Fußabdruck (muss unangetastet bleiben) ---
        b_party = party_storage.create_party(db_path, uuid.uuid4().hex, b.id, "B Fest")
        b_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, b.id, "B Events")
        profile_storage.upsert_user_profile(db_path, b.id, birth_date=date(1991, 2, 2), username="bravo")

        # === Löschen ===
        delete_account(db_path, a.id)

        with sqlite3.connect(db_path) as check:
            assert check.execute("SELECT COUNT(*) FROM users WHERE id = ?", (a.id,)).fetchone()[0] == 0
            for table, col in (
                ("refresh_tokens", "user_id"), ("user_profiles", "user_id"), ("notifications", "user_id"),
                ("notification_settings", "user_id"), ("user_discovery_preferences", "user_id"),
                ("learned_affinity_signals", "user_id"), ("party_runs", "host_user_id"),
                ("organizer_memberships", "user_id"), ("organizer_follows", "user_id"),
                ("event_follows", "user_id"), ("discover_actions", "user_id"),
            ):
                n = check.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (a.id,)).fetchone()[0]
                assert n == 0, f"{table}.{col} noch {n} Zeilen fuer A"
            assert check.execute("SELECT COUNT(*) FROM parties WHERE host_user_id = ?", (a.id,)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM organizers WHERE owner_user_id = ?", (a.id,)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM party_memberships WHERE party_id = ?", (a_party.id,)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM public_events WHERE party_id = ?", (a_party.id,)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM party_locations WHERE party_id = ?", (a_party.id,)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM invitations WHERE invited_user_id = ?", (b.id,)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM friendships WHERE user_a_id = ? OR user_b_id = ?", (a.id, a.id)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM login_attempts WHERE email = ?", ("a@example.com",)).fetchone()[0] == 0
            assert check.execute("SELECT COUNT(*) FROM selection_events").fetchone()[0] == 0

            # B unangetastet.
            assert check.execute("SELECT COUNT(*) FROM users WHERE id = ?", (b.id,)).fetchone()[0] == 1
            assert check.execute("SELECT COUNT(*) FROM parties WHERE id = ?", (b_party.id,)).fetchone()[0] == 1
            assert check.execute("SELECT COUNT(*) FROM organizers WHERE id = ?", (b_org.id,)).fetchone()[0] == 1
            assert check.execute("SELECT COUNT(*) FROM user_profiles WHERE user_id = ?", (b.id,)).fetchone()[0] == 1

        # Idempotent.
        delete_account(db_path, a.id)

        print("accounts/account_deletion.py sanity check OK.")
