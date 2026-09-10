"""SQLite-Persistenz für ``UserBlock`` (Social-Graph-Phase-1).

Gerichtet, strukturelle Kopie von ``blocked_organizers`` in
``accounts/discover_learning.py``. Siehe ``social/domain.py`` für die
Abgrenzung gegen ``accounts.domain.BlockedOrganizer``.

Abhängigkeits-Richtung: dieses Modul importiert NICHTS aus
``social.friend_requests`` (das umgekehrt ``social.blocks`` importiert, für
den ``is_blocked``-Check in ``create_friend_request``) - ``block_user``
schreibt stattdessen per Roh-SQL direkt in die ``friend_requests``-/
``friendships``-Tabellen (siehe dortige Begründung: eigene Connections
würden die Transaktion aufbrechen)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from social.domain import UserBlock


def init_block_storage(db_path: str | Path) -> None:
    """Legt ``user_blocks`` an, falls nicht vorhanden. Idempotent, sicher
    bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_blocks (
                id TEXT PRIMARY KEY,
                blocker_id TEXT NOT NULL,
                blocked_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(blocker_id, blocked_id),
                FOREIGN KEY (blocker_id) REFERENCES users(id),
                FOREIGN KEY (blocked_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker ON user_blocks(blocker_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON user_blocks(blocked_id)")


def _row_to_block(row: sqlite3.Row) -> UserBlock:
    return UserBlock(
        id=row["id"],
        blocker_id=row["blocker_id"],
        blocked_id=row["blocked_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def block_user(db_path: str | Path, block_id: str, blocker_id: str, blocked_id: str) -> UserBlock:
    """Harter Block (Spec §31-33) - in EINER Transaktion: (1) storniert jede
    pending ``FriendRequest`` zwischen den beiden Usern (beide Richtungen),
    (2) löscht eine bestehende ``Friendship`` (kanonisches Paar), (3)
    entfernt Follow-Beziehungen zwischen den beiden Usern in BEIDE
    Richtungen (Social-Graph-Phase-9, Spec §80/§128), (4) legt idempotent
    den ``user_blocks``-Eintrag an (SELECT-then-return-existing, mirrort
    ``discover_learning.block_organizer``). Schreibt (1)-(3) per Roh-SQL
    statt über ``social.friend_requests``/``social.friendships``/
    ``social.follows`` aufzurufen - jene öffnen eigene Connections, was
    diese Transaktion aufbrechen würde (gleiche Begründung wie
    ``accounts/invitation_storage.py::create_invitation`` beim Schreiben in
    ``party_memberships``). "Organizer"/"Event" hängen mangels
    ``Party.organizer_id`` (siehe Phase 8) über ``organizers.owner_user_id``
    bzw. ``parties.host_user_id`` an einem User."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        conn.execute(
            "UPDATE friend_requests SET status = 'cancelled', version = version + 1, responded_at = ? "
            "WHERE status = 'pending' AND "
            "((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))",
            (now, blocker_id, blocked_id, blocked_id, blocker_id),
        )

        user_a_id, user_b_id = tuple(sorted((blocker_id, blocked_id)))
        conn.execute("DELETE FROM friendships WHERE user_a_id = ? AND user_b_id = ?", (user_a_id, user_b_id))

        for follower, target_owner in ((blocker_id, blocked_id), (blocked_id, blocker_id)):
            conn.execute(
                "DELETE FROM organizer_follows WHERE user_id = ? AND organizer_id IN "
                "(SELECT id FROM organizers WHERE owner_user_id = ?)",
                (follower, target_owner),
            )
            conn.execute(
                "DELETE FROM event_follows WHERE user_id = ? AND party_id IN "
                "(SELECT id FROM parties WHERE host_user_id = ?)",
                (follower, target_owner),
            )

        existing = conn.execute(
            "SELECT * FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?", (blocker_id, blocked_id)
        ).fetchone()
        if existing is not None:
            return _row_to_block(existing)

        conn.execute(
            "INSERT INTO user_blocks (id, blocker_id, blocked_id, created_at) VALUES (?, ?, ?, ?)",
            (block_id, blocker_id, blocked_id, now),
        )
        row = conn.execute("SELECT * FROM user_blocks WHERE id = ?", (block_id,)).fetchone()
    return _row_to_block(row)


def unblock_user(db_path: str | Path, blocker_id: str, blocked_id: str) -> None:
    """No-Op, falls kein Block existiert (mirrort
    ``discover_learning.unblock_organizer``). Stellt bewusst KEINE zuvor
    gecancelte ``FriendRequest``/``Friendship`` wieder her - Unblock hebt
    nur den Interaktions-Constraint auf, User müssen danach explizit neu
    anfragen."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?", (blocker_id, blocked_id))


def is_blocked(db_path: str | Path, user_id_a: str, user_id_b: str) -> bool:
    """Bidirektional: True, wenn A B blockiert hat ODER B A blockiert hat -
    ein Block wirkt als Interaktionssperre in beide Richtungen, auch wenn
    die Blockier-Entscheidung selbst gerichtet gespeichert ist."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM user_blocks WHERE (blocker_id = ? AND blocked_id = ?) "
            "OR (blocker_id = ? AND blocked_id = ?)",
            (user_id_a, user_id_b, user_id_b, user_id_a),
        ).fetchone()
    return row is not None


def list_blocked_user_ids(db_path: str | Path, user_id: str) -> set[str]:
    """Mirrort ``discover_learning.get_blocked_organizer_ids`` - bare
    ``set[str]``, wenn nur die IDs gebraucht werden."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT blocked_id FROM user_blocks WHERE blocker_id = ?", (user_id,)).fetchall()
    return {row[0] for row in rows}


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage
    import organizers.storage as organizers_storage
    import social.follows as follows
    import social.friend_requests as friend_requests
    import social.friendships as friendships
    from organizers.domain import OrganizerVerificationStatus

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_blocks.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        organizers_storage.init_organizer_storage(db_path)
        follows.init_follow_storage(db_path)
        init_block_storage(db_path)
        init_block_storage(db_path)  # idempotent
        friendships.init_friendship_storage(db_path)
        friend_requests.init_friend_request_storage(db_path)

        anna = user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")
        max_ = user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")

        assert is_blocked(db_path, anna.id, max_.id) is False
        assert list_blocked_user_ids(db_path, anna.id) == set()

        block = block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
        assert block.blocker_id == anna.id
        assert block.blocked_id == max_.id
        # Bidirektional: von beiden Seiten aus als blockiert erkennbar.
        assert is_blocked(db_path, anna.id, max_.id) is True
        assert is_blocked(db_path, max_.id, anna.id) is True
        assert list_blocked_user_ids(db_path, anna.id) == {max_.id}
        # Gerichtet gespeichert: max hat anna nicht blockiert.
        assert list_blocked_user_ids(db_path, max_.id) == set()

        # Idempotent.
        block_again = block_user(db_path, uuid.uuid4().hex, anna.id, max_.id)
        assert block_again.id == block.id

        unblock_user(db_path, anna.id, max_.id)
        assert is_blocked(db_path, anna.id, max_.id) is False

        # Unblock ohne bestehenden Block -> No-Op.
        unblock_user(db_path, anna.id, max_.id)

        # Block storniert eine pending FriendRequest und beendet eine Friendship.
        ben = user_storage.create_user(db_path, uuid.uuid4().hex, "ben@example.com", "hash", "Ben")
        friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, ben.id)
        block_user(db_path, uuid.uuid4().hex, anna.id, ben.id)
        pending = friend_requests.get_pending_request(db_path, anna.id, ben.id)
        assert pending is None  # storniert

        carla = user_storage.create_user(db_path, uuid.uuid4().hex, "carla@example.com", "hash", "Carla")
        req = friend_requests.create_friend_request(db_path, uuid.uuid4().hex, anna.id, carla.id)
        friend_requests.accept_friend_request(db_path, req.request.id, carla.id)
        assert friendships.are_friends(db_path, anna.id, carla.id) is True
        block_user(db_path, uuid.uuid4().hex, anna.id, carla.id)
        assert friendships.are_friends(db_path, anna.id, carla.id) is False

        # Social-Graph-Phase-9: Block entfernt Follow-Beziehungen in beide Richtungen.
        dora = user_storage.create_user(db_path, uuid.uuid4().hex, "dora@example.com", "hash", "Dora")
        eric = user_storage.create_user(db_path, uuid.uuid4().hex, "eric@example.com", "hash", "Eric")
        eric_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, eric.id, "Eric Events")
        organizers_storage.set_verification_status(db_path, eric_org.id, OrganizerVerificationStatus.VERIFIED)
        eric_party = party_storage.create_party(db_path, uuid.uuid4().hex, eric.id, "Eric Fest")
        dora_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, dora.id, "Dora Events")
        organizers_storage.set_verification_status(db_path, dora_org.id, OrganizerVerificationStatus.VERIFIED)
        ben_org = organizers_storage.create_organizer(db_path, uuid.uuid4().hex, ben.id, "Ben Events")

        follows.follow_organizer(db_path, uuid.uuid4().hex, dora.id, eric_org.id)   # dora -> eric-org
        follows.follow_event(db_path, uuid.uuid4().hex, dora.id, eric_party.id)     # dora -> eric-event
        follows.follow_organizer(db_path, uuid.uuid4().hex, eric.id, dora_org.id)   # eric -> dora-org (Gegenrichtung)
        follows.follow_organizer(db_path, uuid.uuid4().hex, dora.id, ben_org.id)    # dora -> ben-org (unbeteiligt)

        block_user(db_path, uuid.uuid4().hex, dora.id, eric.id)
        assert follows.is_following_organizer(db_path, dora.id, eric_org.id) is False
        assert follows.is_following_event(db_path, dora.id, eric_party.id) is False
        assert follows.is_following_organizer(db_path, eric.id, dora_org.id) is False  # Gegenrichtung auch weg
        assert follows.is_following_organizer(db_path, dora.id, ben_org.id) is True    # unbeteiligt bleibt

        print("social/blocks.py sanity check OK.")
