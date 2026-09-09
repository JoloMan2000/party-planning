"""SQLite-Persistenz für ``FriendRequest`` (Social-Graph-Phase-1), inkl.
Cross-Request-Merge (AUFGABE-Spec §20: "Cross Requests intelligent
zusammenführen").

Mirrort strukturell ``accounts/invitation_storage.py``: dedizierte
Exception-Klassen pro Fehlerfall, ein guarded ``UPDATE ... WHERE status =
'pending'`` für Transitions (statt der vollen Idempotency-Key-/
OCC-Maschinerie von ``apply_rsvp_transition`` - siehe
``social/domain.py``-Doku zu ``FriendRequest.version`` und
``social/friend_request_state_machine.py``-Moduldoku für die bewusste
Vereinfachung).

Abhängigkeits-Richtung: DIESES Modul importiert ``social.blocks``
(``is_blocked``) und ``social.friendships`` (``are_friends``,
``create_friendship``) für reine Lese-/Anlage-Checks - NICHT umgekehrt, um
einen Import-Zyklus mit ``social/blocks.py`` (das per Roh-SQL, nicht per
Funktionsaufruf, in die ``friend_requests``-Tabelle schreibt) zu vermeiden."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import social.blocks as blocks
import social.friendships as friendships
from social.domain import FriendRequest, FriendRequestStatus, Friendship


class SelfFriendRequestError(Exception):
    pass


class UserBlockedError(Exception):
    pass


class AlreadyFriendsError(Exception):
    pass


class FriendRequestAlreadyExistsError(Exception):
    pass


class FriendRequestNotFoundError(Exception):
    pass


class InvalidFriendRequestActorError(Exception):
    pass


class InvalidFriendRequestTransitionError(Exception):
    pass


@dataclass
class FriendRequestCreateResult:
    request: FriendRequest
    merged: bool
    friendship: Friendship | None = None


@dataclass
class FriendRequestAcceptResult:
    request: FriendRequest
    friendship: Friendship


def init_friend_request_storage(db_path: str | Path) -> None:
    """Legt ``friend_requests`` an, falls nicht vorhanden. Idempotent,
    sicher bei jedem App-Start aufrufbar.

    Der partielle Unique-Index (statt eines Tabellen-``UNIQUE(sender_id,
    receiver_id)``) erlaubt erneutes Anfragen NACHDEM eine frühere Anfrage
    declined/cancelled/expired wurde (diese Zeilen bleiben mit
    nicht-pending Status bestehen), verhindert aber weiterhin zwei
    gleichzeitige pending Anfragen in dieselbe Richtung."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friend_requests (
                id TEXT PRIMARY KEY,
                sender_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                responded_at TEXT,
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (receiver_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_friend_requests_active_pair "
            "ON friend_requests(sender_id, receiver_id) WHERE status = 'pending'"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friend_requests_receiver ON friend_requests(receiver_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friend_requests_sender ON friend_requests(sender_id)")


def _row_to_request(row: sqlite3.Row) -> FriendRequest:
    return FriendRequest(
        id=row["id"],
        sender_id=row["sender_id"],
        receiver_id=row["receiver_id"],
        status=FriendRequestStatus(row["status"]),
        version=row["version"],
        created_at=datetime.fromisoformat(row["created_at"]),
        responded_at=datetime.fromisoformat(row["responded_at"]) if row["responded_at"] else None,
    )


def get_friend_request(db_path: str | Path, request_id: str) -> FriendRequest | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM friend_requests WHERE id = ?", (request_id,)).fetchone()
    return _row_to_request(row) if row is not None else None


def get_pending_request(db_path: str | Path, sender_id: str, receiver_id: str) -> FriendRequest | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM friend_requests WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'",
            (sender_id, receiver_id),
        ).fetchone()
    return _row_to_request(row) if row is not None else None


def _accept_request_row(conn: sqlite3.Connection, request_row: sqlite3.Row, friendship_id: str) -> FriendRequestAcceptResult:
    """Interner Helper, geteilt zwischen ``accept_friend_request`` und dem
    Cross-Merge-Zweig in ``create_friend_request`` - beide führen exakt
    dieselbe guarded UPDATE + Friendship-Anlage aus, nur der Aufrufkontext
    (expliziter Accept vs. automatischer Merge) unterscheidet sich.

    Schreibt die ``friendships``-Zeile per Roh-SQL in DERSELBEN Connection/
    Transaktion wie das ``friend_requests``-UPDATE (statt
    ``social.friendships.create_friendship`` aufzurufen, das eine eigene
    Connection öffnen würde) - gleiche Atomicity-Begründung wie
    ``social/blocks.py::block_user``."""
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "UPDATE friend_requests SET status = ?, version = version + 1, responded_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (FriendRequestStatus.ACCEPTED.value, now, request_row["id"]),
    )
    if cursor.rowcount == 0:
        raise InvalidFriendRequestTransitionError(f"{request_row['id']} ist nicht mehr pending.")
    updated_row = conn.execute("SELECT * FROM friend_requests WHERE id = ?", (request_row["id"],)).fetchone()
    request = _row_to_request(updated_row)

    user_a_id, user_b_id = tuple(sorted((request.sender_id, request.receiver_id)))
    existing_friendship_row = conn.execute(
        "SELECT * FROM friendships WHERE user_a_id = ? AND user_b_id = ?", (user_a_id, user_b_id)
    ).fetchone()
    if existing_friendship_row is None:
        conn.execute(
            """
            INSERT INTO friendships (id, user_a_id, user_b_id, source_friend_request_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (friendship_id, user_a_id, user_b_id, request.id, now),
        )
        friendship_row = conn.execute("SELECT * FROM friendships WHERE id = ?", (friendship_id,)).fetchone()
    else:
        friendship_row = existing_friendship_row
    friendship = friendships._row_to_friendship(friendship_row)
    return FriendRequestAcceptResult(request=request, friendship=friendship)


def create_friend_request(db_path: str | Path, request_id: str, sender_id: str, receiver_id: str) -> FriendRequestCreateResult:
    """Legt eine neue Anfrage an - oder, falls der Empfänger bereits eine
    PENDING Gegenanfrage an den Sender gestellt hat, führt sie automatisch
    zusammen (Cross-Merge, Spec §20) statt einen Duplicate-Error zu werfen:
    die Gegenanfrage wird sofort akzeptiert (via ``_accept_request_row``),
    eine ``Friendship`` entsteht, ``merged=True`` wird zurückgegeben."""
    if sender_id == receiver_id:
        raise SelfFriendRequestError(sender_id)
    if blocks.is_blocked(db_path, sender_id, receiver_id):
        raise UserBlockedError(f"{sender_id} <-> {receiver_id}")
    if friendships.are_friends(db_path, sender_id, receiver_id):
        raise AlreadyFriendsError(f"{sender_id} <-> {receiver_id}")

    reverse = get_pending_request(db_path, receiver_id, sender_id)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if reverse is not None:
            reverse_row = conn.execute("SELECT * FROM friend_requests WHERE id = ?", (reverse.id,)).fetchone()
            result = _accept_request_row(conn, reverse_row, request_id)
            return FriendRequestCreateResult(request=result.request, merged=True, friendship=result.friendship)

        now = datetime.now().isoformat()
        try:
            conn.execute(
                """
                INSERT INTO friend_requests (id, sender_id, receiver_id, status, version, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (request_id, sender_id, receiver_id, FriendRequestStatus.PENDING.value, now),
            )
        except sqlite3.IntegrityError as exc:
            raise FriendRequestAlreadyExistsError(f"{sender_id} -> {receiver_id}") from exc
        row = conn.execute("SELECT * FROM friend_requests WHERE id = ?", (request_id,)).fetchone()
    return FriendRequestCreateResult(request=_row_to_request(row), merged=False)


def _require_request(db_path: str | Path, request_id: str) -> FriendRequest:
    request = get_friend_request(db_path, request_id)
    if request is None:
        raise FriendRequestNotFoundError(request_id)
    return request


def accept_friend_request(db_path: str | Path, request_id: str, actor_user_id: str) -> FriendRequestAcceptResult:
    request = _require_request(db_path, request_id)
    if actor_user_id != request.receiver_id:
        raise InvalidFriendRequestActorError(f"{actor_user_id} ist nicht Empfänger von {request_id}.")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM friend_requests WHERE id = ?", (request_id,)).fetchone()
        return _accept_request_row(conn, row, request_id)


def decline_friend_request(db_path: str | Path, request_id: str, actor_user_id: str) -> FriendRequest:
    request = _require_request(db_path, request_id)
    if actor_user_id != request.receiver_id:
        raise InvalidFriendRequestActorError(f"{actor_user_id} ist nicht Empfänger von {request_id}.")
    return _transition(db_path, request_id, FriendRequestStatus.DECLINED)


def cancel_friend_request(db_path: str | Path, request_id: str, actor_user_id: str) -> FriendRequest:
    request = _require_request(db_path, request_id)
    if actor_user_id != request.sender_id:
        raise InvalidFriendRequestActorError(f"{actor_user_id} ist nicht Sender von {request_id}.")
    return _transition(db_path, request_id, FriendRequestStatus.CANCELLED)


def expire_friend_request(db_path: str | Path, request_id: str) -> FriendRequest:
    """System-/Hintergrund-Transition. Definiert, aber unverdrahtet - kein
    Scheduled Job ruft sie in Phase 1 auf (siehe
    ``social/friend_request_state_machine.py::can_expire``)."""
    return _transition(db_path, request_id, FriendRequestStatus.EXPIRED)


def _transition(db_path: str | Path, request_id: str, new_status: FriendRequestStatus) -> FriendRequest:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE friend_requests SET status = ?, version = version + 1, responded_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (new_status.value, now, request_id),
        )
        if cursor.rowcount == 0:
            raise InvalidFriendRequestTransitionError(f"{request_id} ist nicht mehr pending.")
    result = get_friend_request(db_path, request_id)
    assert result is not None
    return result


def list_incoming_requests(
    db_path: str | Path, user_id: str, status: FriendRequestStatus | None = FriendRequestStatus.PENDING
) -> list[FriendRequest]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM friend_requests WHERE receiver_id = ? AND status = ? ORDER BY created_at DESC",
                (user_id, status.value),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM friend_requests WHERE receiver_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
    return [_row_to_request(r) for r in rows]


def list_outgoing_requests(
    db_path: str | Path, user_id: str, status: FriendRequestStatus | None = FriendRequestStatus.PENDING
) -> list[FriendRequest]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM friend_requests WHERE sender_id = ? AND status = ? ORDER BY created_at DESC",
                (user_id, status.value),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM friend_requests WHERE sender_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
    return [_row_to_request(r) for r in rows]


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage
    import social.blocks as blocks_module
    import social.friendships as friendships_module

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_friend_requests.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        friendships_module.init_friendship_storage(db_path)
        blocks_module.init_block_storage(db_path)
        init_friend_request_storage(db_path)
        init_friend_request_storage(db_path)  # idempotent

        anna = user_storage.create_user(db_path, uuid.uuid4().hex, "anna@example.com", "hash", "Anna")
        max_ = user_storage.create_user(db_path, uuid.uuid4().hex, "max@example.com", "hash", "Max")
        ben = user_storage.create_user(db_path, uuid.uuid4().hex, "ben@example.com", "hash", "Ben")

        # Self-request verboten.
        try:
            create_friend_request(db_path, uuid.uuid4().hex, anna.id, anna.id)
            assert False, "sollte SelfFriendRequestError werfen"
        except SelfFriendRequestError:
            pass

        # Normale Anfrage.
        result = create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
        assert result.merged is False
        assert result.request.status == FriendRequestStatus.PENDING

        # Duplicate pending -> Error.
        try:
            create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
            assert False, "sollte FriendRequestAlreadyExistsError werfen"
        except FriendRequestAlreadyExistsError:
            pass

        # Falscher Akteur darf nicht annehmen.
        try:
            accept_friend_request(db_path, result.request.id, ben.id)
            assert False, "sollte InvalidFriendRequestActorError werfen"
        except InvalidFriendRequestActorError:
            pass

        accept_result = accept_friend_request(db_path, result.request.id, max_.id)
        assert accept_result.request.status == FriendRequestStatus.ACCEPTED
        assert friendships_module.are_friends(db_path, anna.id, max_.id) is True

        # Bereits Freunde -> neue Anfrage verboten.
        try:
            create_friend_request(db_path, uuid.uuid4().hex, anna.id, max_.id)
            assert False, "sollte AlreadyFriendsError werfen"
        except AlreadyFriendsError:
            pass

        # Erneute Transition auf bereits-akzeptierte Anfrage -> Fehler.
        try:
            accept_friend_request(db_path, result.request.id, max_.id)
            assert False, "sollte InvalidFriendRequestTransitionError werfen"
        except InvalidFriendRequestTransitionError:
            pass

        # Decline.
        decline_pair = create_friend_request(db_path, uuid.uuid4().hex, anna.id, ben.id)
        declined = decline_friend_request(db_path, decline_pair.request.id, ben.id)
        assert declined.status == FriendRequestStatus.DECLINED
        # Nach Decline darf erneut angefragt werden (partial index erlaubt das).
        re_request = create_friend_request(db_path, uuid.uuid4().hex, anna.id, ben.id)
        assert re_request.request.status == FriendRequestStatus.PENDING

        # Cancel.
        cancel_target = create_friend_request(db_path, uuid.uuid4().hex, ben.id, max_.id)
        cancelled = cancel_friend_request(db_path, cancel_target.request.id, ben.id)
        assert cancelled.status == FriendRequestStatus.CANCELLED

        # Blocked -> neue Anfrage verboten.
        blocks_module.block_user(db_path, uuid.uuid4().hex, ben.id, max_.id)
        try:
            create_friend_request(db_path, uuid.uuid4().hex, ben.id, max_.id)
            assert False, "sollte UserBlockedError werfen"
        except UserBlockedError:
            pass

        # Cross-Merge: anna->ben ist aus re_request bereits wieder pending -
        # ben->anna sollte das automatisch zusammenführen statt zu duplizieren.
        c_to_a = create_friend_request(db_path, uuid.uuid4().hex, ben.id, anna.id)
        assert c_to_a.merged is True
        assert c_to_a.friendship is not None
        assert friendships_module.are_friends(db_path, anna.id, ben.id) is True
        original = get_friend_request(db_path, re_request.request.id)
        assert original.status == FriendRequestStatus.ACCEPTED

        assert len(list_incoming_requests(db_path, max_.id)) == 0  # alles bereits final
        assert len(list_outgoing_requests(db_path, anna.id, status=None)) >= 2

        print("social/friend_requests.py sanity check OK.")
