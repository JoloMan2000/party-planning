"""SQLite-Persistenz für Einladungen + RSVP-Historie (Account-basierter
Pivot, Phase 1). Mirrort das Muster aus ``accounts/party_storage.py``/
``accounts/user_storage.py``.

Kernstück ist ``apply_rsvp_transition`` - die einzige erlaubte Art, den
Status einer Invitation zu ändern (kein beliebiges String-Setzen), mit
Idempotenz (client_request_id), Optimistic Concurrency Control (version)
und Spiegelung des neuen Status auf ``party_memberships``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from accounts.domain import Invitation, PartyRole, RsvpHistoryEntry, RsvpStatus
from accounts.rsvp_state_machine import can_guest_transition, can_host_revoke


class InvitationAlreadyExistsError(Exception):
    pass


class PartyNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class InvitationNotFoundError(Exception):
    pass


class VersionConflictError(Exception):
    def __init__(self, current_version: int, expected_version: int):
        self.current_version = current_version
        self.expected_version = expected_version
        super().__init__(f"expected version {expected_version}, current version is {current_version}")


class InvalidTransitionError(Exception):
    pass


class IdempotencyKeyReuseError(Exception):
    pass


@dataclass
class RsvpResult:
    invitation_id: str
    party_id: str
    status: RsvpStatus
    responded_at: datetime | None
    version: int


def init_invitation_storage(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invitations (
                id TEXT PRIMARY KEY,
                party_id TEXT NOT NULL,
                host_user_id TEXT NOT NULL,
                invited_user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                invitation_message TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                viewed_at TEXT,
                responded_at TEXT,
                UNIQUE(party_id, invited_user_id),
                FOREIGN KEY (party_id) REFERENCES parties(id),
                FOREIGN KEY (host_user_id) REFERENCES users(id),
                FOREIGN KEY (invited_user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invitations_party ON invitations(party_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invitations_invited_user ON invitations(invited_user_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rsvp_history (
                id TEXT PRIMARY KEY,
                invitation_id TEXT NOT NULL,
                party_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_by_user_id TEXT NOT NULL,
                client_request_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (invitation_id) REFERENCES invitations(id)
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_rsvp_history_idempotency "
            "ON rsvp_history(invitation_id, client_request_id) WHERE client_request_id IS NOT NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rsvp_history_invitation ON rsvp_history(invitation_id)")


def _row_to_invitation(row: sqlite3.Row) -> Invitation:
    return Invitation(
        id=row["id"],
        party_id=row["party_id"],
        host_user_id=row["host_user_id"],
        invited_user_id=row["invited_user_id"],
        status=RsvpStatus(row["status"]),
        invitation_message=row["invitation_message"],
        version=row["version"],
        created_at=datetime.fromisoformat(row["created_at"]),
        viewed_at=datetime.fromisoformat(row["viewed_at"]) if row["viewed_at"] else None,
        responded_at=datetime.fromisoformat(row["responded_at"]) if row["responded_at"] else None,
    )


def create_invitation(
    db_path: str | Path,
    invitation_id: str,
    party_id: str,
    host_user_id: str,
    invited_user_id: str,
    invitation_message: str = "",
) -> Invitation:
    """Prüft Existenz von Party + eingeladenem User und legt (atomisch, gleiche
    Transaktion) die Invitation UND eine ``guest``/``pending``-Membership an."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        party_row = conn.execute("SELECT id FROM parties WHERE id = ?", (party_id,)).fetchone()
        if party_row is None:
            raise PartyNotFoundError(party_id)
        user_row = conn.execute("SELECT id FROM users WHERE id = ?", (invited_user_id,)).fetchone()
        if user_row is None:
            raise UserNotFoundError(invited_user_id)
        try:
            conn.execute(
                """
                INSERT INTO invitations
                    (id, party_id, host_user_id, invited_user_id, status, invitation_message, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (invitation_id, party_id, host_user_id, invited_user_id, RsvpStatus.PENDING.value, invitation_message, now),
            )
        except sqlite3.IntegrityError as exc:
            raise InvitationAlreadyExistsError(f"{party_id}:{invited_user_id}") from exc
        conn.execute(
            """
            INSERT INTO party_memberships (id, party_id, user_id, role, rsvp_status, joined_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(party_id, user_id) DO UPDATE SET
                rsvp_status = excluded.rsvp_status, updated_at = excluded.updated_at
            """,
            (f"{party_id}:{invited_user_id}", party_id, invited_user_id, PartyRole.GUEST.value, RsvpStatus.PENDING.value, now, now),
        )
    return Invitation(
        id=invitation_id,
        party_id=party_id,
        host_user_id=host_user_id,
        invited_user_id=invited_user_id,
        status=RsvpStatus.PENDING,
        invitation_message=invitation_message,
        version=1,
        created_at=datetime.fromisoformat(now),
    )


def get_invitation(db_path: str | Path, invitation_id: str) -> Invitation | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
    return _row_to_invitation(row) if row is not None else None


def list_invitations_for_user(db_path: str | Path, user_id: str, status: RsvpStatus | None = None) -> list[Invitation]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM invitations WHERE invited_user_id = ? AND status = ? ORDER BY created_at DESC",
                (user_id, status.value),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM invitations WHERE invited_user_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
    return [_row_to_invitation(r) for r in rows]


def list_invitations_for_party(db_path: str | Path, party_id: str) -> list[Invitation]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM invitations WHERE party_id = ? ORDER BY created_at DESC", (party_id,)
        ).fetchall()
    return [_row_to_invitation(r) for r in rows]


def mark_invitation_viewed(db_path: str | Path, invitation_id: str) -> Invitation | None:
    """Setzt ``viewed_at`` nur beim ersten Aufruf (idempotent), bumpt NICHT
    die Version - reines Anzeigen ist keine RSVP-Statusänderung."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT viewed_at FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
        if row is None:
            return None
        if row["viewed_at"] is None:
            conn.execute(
                "UPDATE invitations SET viewed_at = ? WHERE id = ?", (datetime.now().isoformat(), invitation_id)
            )
    return get_invitation(db_path, invitation_id)


def apply_rsvp_transition(
    db_path: str | Path,
    invitation_id: str,
    new_status: RsvpStatus,
    actor_user_id: str,
    expected_version: int,
    client_request_id: str | None = None,
) -> RsvpResult:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Idempotenz-Fastpath: gleiche client_request_id schon verarbeitet?
        if client_request_id is not None:
            history_row = conn.execute(
                "SELECT new_status FROM rsvp_history WHERE invitation_id = ? AND client_request_id = ?",
                (invitation_id, client_request_id),
            ).fetchone()
            if history_row is not None:
                inv_row = conn.execute("SELECT * FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
                if inv_row is None:
                    raise InvitationNotFoundError(invitation_id)
                if history_row["new_status"] != new_status.value:
                    raise IdempotencyKeyReuseError(client_request_id)
                return RsvpResult(
                    invitation_id=inv_row["id"],
                    party_id=inv_row["party_id"],
                    status=RsvpStatus(inv_row["status"]),
                    responded_at=datetime.fromisoformat(inv_row["responded_at"]) if inv_row["responded_at"] else None,
                    version=inv_row["version"],
                )

        # 2. Invitation laden
        inv_row = conn.execute("SELECT * FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
        if inv_row is None:
            raise InvitationNotFoundError(invitation_id)
        current_status = RsvpStatus(inv_row["status"])
        current_version = inv_row["version"]

        # 3. OCC-Check
        if current_version != expected_version:
            raise VersionConflictError(current_version, expected_version)

        # 4. State-Machine-Check
        if not can_guest_transition(current_status, new_status):
            raise InvalidTransitionError(f"{current_status.value} -> {new_status.value} not allowed")

        # 5. Atomisches UPDATE (version erneut in WHERE geprüft, Defense-in-Depth)
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "UPDATE invitations SET status = ?, version = version + 1, responded_at = ? WHERE id = ? AND version = ?",
            (new_status.value, now, invitation_id, expected_version),
        )
        if cursor.rowcount == 0:
            refreshed = conn.execute("SELECT version FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
            raise VersionConflictError(refreshed["version"] if refreshed else current_version, expected_version)

        # 6. rsvp_history-Eintrag (IntegrityError bei Idempotenz-Race schlucken)
        try:
            conn.execute(
                """
                INSERT INTO rsvp_history
                    (id, invitation_id, party_id, user_id, previous_status, new_status, changed_by_user_id, client_request_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{invitation_id}:{current_version}",
                    invitation_id,
                    inv_row["party_id"],
                    inv_row["invited_user_id"],
                    current_status.value,
                    new_status.value,
                    actor_user_id,
                    client_request_id,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            pass

        # 7. Spiegelung auf party_memberships
        conn.execute(
            "UPDATE party_memberships SET rsvp_status = ?, updated_at = ? WHERE party_id = ? AND user_id = ?",
            (new_status.value, now, inv_row["party_id"], inv_row["invited_user_id"]),
        )

    return RsvpResult(
        invitation_id=invitation_id,
        party_id=inv_row["party_id"],
        status=new_status,
        responded_at=datetime.fromisoformat(now),
        version=expected_version + 1,
    )


def revoke_invitation(db_path: str | Path, invitation_id: str, host_user_id: str) -> RsvpResult:
    """Host-Aktion: aus jedem nicht-terminalen Status -> REVOKED. Gleiche
    Version-/History-Buchhaltung wie ``apply_rsvp_transition``, aber ohne
    Idempotenzschlüssel (Host-Aktionen sind nicht client-retry-empfindlich
    in Phase 1)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        inv_row = conn.execute("SELECT * FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
        if inv_row is None:
            raise InvitationNotFoundError(invitation_id)
        current_status = RsvpStatus(inv_row["status"])
        current_version = inv_row["version"]

        if not can_host_revoke(current_status):
            raise InvalidTransitionError(f"{current_status.value} -> revoked not allowed")

        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE invitations SET status = ?, version = version + 1, responded_at = ? WHERE id = ? AND version = ?",
            (RsvpStatus.REVOKED.value, now, invitation_id, current_version),
        )
        try:
            conn.execute(
                """
                INSERT INTO rsvp_history
                    (id, invitation_id, party_id, user_id, previous_status, new_status, changed_by_user_id, client_request_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"{invitation_id}:{current_version}",
                    invitation_id,
                    inv_row["party_id"],
                    inv_row["invited_user_id"],
                    current_status.value,
                    RsvpStatus.REVOKED.value,
                    host_user_id,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            pass
        conn.execute(
            "UPDATE party_memberships SET rsvp_status = ?, updated_at = ? WHERE party_id = ? AND user_id = ?",
            (RsvpStatus.REVOKED.value, now, inv_row["party_id"], inv_row["invited_user_id"]),
        )

    return RsvpResult(
        invitation_id=invitation_id,
        party_id=inv_row["party_id"],
        status=RsvpStatus.REVOKED,
        responded_at=datetime.fromisoformat(now),
        version=current_version + 1,
    )


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.party_storage as party_storage
    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_invitation_storage.db"
        user_storage.init_user_storage(db_path)
        party_storage.init_party_storage(db_path)
        init_invitation_storage(db_path)
        init_invitation_storage(db_path)  # idempotent

        host = user_storage.create_user(db_path, uuid.uuid4().hex, "host@example.com", "hash", "Host")
        guest = user_storage.create_user(db_path, uuid.uuid4().hex, "guest@example.com", "hash", "Guest")
        stranger = user_storage.create_user(db_path, uuid.uuid4().hex, "stranger@example.com", "hash", "Stranger")

        party = party_storage.create_party(db_path, uuid.uuid4().hex, host.id, "Summer BBQ")

        # PartyNotFoundError / UserNotFoundError
        try:
            create_invitation(db_path, uuid.uuid4().hex, "unknown-party", host.id, guest.id)
            raise AssertionError("sollte PartyNotFoundError werfen")
        except PartyNotFoundError:
            pass
        try:
            create_invitation(db_path, uuid.uuid4().hex, party.id, host.id, "unknown-user")
            raise AssertionError("sollte UserNotFoundError werfen")
        except UserNotFoundError:
            pass

        inv_id = uuid.uuid4().hex
        invitation = create_invitation(db_path, inv_id, party.id, host.id, guest.id, invitation_message="Come!")
        assert invitation.status == RsvpStatus.PENDING
        assert invitation.version == 1

        membership = party_storage.get_membership(db_path, party.id, guest.id)
        assert membership is not None
        assert membership.role == PartyRole.GUEST
        assert membership.rsvp_status == RsvpStatus.PENDING

        # Duplicate invitation rejected
        try:
            create_invitation(db_path, uuid.uuid4().hex, party.id, host.id, guest.id)
            raise AssertionError("sollte InvitationAlreadyExistsError werfen")
        except InvitationAlreadyExistsError:
            pass

        fetched = get_invitation(db_path, inv_id)
        assert fetched is not None
        assert fetched.invitation_message == "Come!"

        assert get_invitation(db_path, "unknown") is None

        # mark_invitation_viewed - idempotent, kein version bump
        viewed = mark_invitation_viewed(db_path, inv_id)
        assert viewed.viewed_at is not None
        assert viewed.version == 1
        viewed_again = mark_invitation_viewed(db_path, inv_id)
        assert viewed_again.viewed_at == viewed.viewed_at

        # Happy path: PENDING -> ACCEPTED
        result = apply_rsvp_transition(db_path, inv_id, RsvpStatus.ACCEPTED, guest.id, expected_version=1)
        assert result.status == RsvpStatus.ACCEPTED
        assert result.version == 2
        assert result.responded_at is not None

        membership = party_storage.get_membership(db_path, party.id, guest.id)
        assert membership.rsvp_status == RsvpStatus.ACCEPTED

        counts = party_storage.count_rsvp_statuses(db_path, party.id)
        assert counts["accepted"] == 1
        assert counts["pending"] == 0

        # Version conflict: stale expected_version, no mutation
        try:
            apply_rsvp_transition(db_path, inv_id, RsvpStatus.TENTATIVE, guest.id, expected_version=1)
            raise AssertionError("sollte VersionConflictError werfen")
        except VersionConflictError as exc:
            assert exc.current_version == 2
            assert exc.expected_version == 1
        unchanged = get_invitation(db_path, inv_id)
        assert unchanged.status == RsvpStatus.ACCEPTED
        assert unchanged.version == 2

        # Invalid transition: ACCEPTED -> nothing invalid exists except REVOKED/EXPIRED via guest path
        try:
            apply_rsvp_transition(db_path, inv_id, RsvpStatus.REVOKED, guest.id, expected_version=2)
            raise AssertionError("sollte InvalidTransitionError werfen")
        except InvalidTransitionError:
            pass

        # Idempotent replay: same client_request_id + same status -> no-op success
        crid = uuid.uuid4().hex
        r1 = apply_rsvp_transition(
            db_path, inv_id, RsvpStatus.TENTATIVE, guest.id, expected_version=2, client_request_id=crid
        )
        assert r1.status == RsvpStatus.TENTATIVE
        assert r1.version == 3
        r2 = apply_rsvp_transition(
            db_path, inv_id, RsvpStatus.TENTATIVE, guest.id, expected_version=2, client_request_id=crid
        )
        assert r2.status == RsvpStatus.TENTATIVE
        assert r2.version == 3  # unverändert, kein zweiter Bump

        # Idempotency-key reuse mit anderem Status -> Fehler
        try:
            apply_rsvp_transition(
                db_path, inv_id, RsvpStatus.DECLINED, guest.id, expected_version=3, client_request_id=crid
            )
            raise AssertionError("sollte IdempotencyKeyReuseError werfen")
        except IdempotencyKeyReuseError:
            pass

        # InvitationNotFoundError
        try:
            apply_rsvp_transition(db_path, "unknown-invitation", RsvpStatus.ACCEPTED, guest.id, expected_version=1)
            raise AssertionError("sollte InvitationNotFoundError werfen")
        except InvitationNotFoundError:
            pass

        # revoke_invitation (Host-Aktion)
        revoke_result = revoke_invitation(db_path, inv_id, host.id)
        assert revoke_result.status == RsvpStatus.REVOKED
        assert revoke_result.version == 4
        membership = party_storage.get_membership(db_path, party.id, guest.id)
        assert membership.rsvp_status == RsvpStatus.REVOKED

        # Revoke aus terminalem Zustand nicht erlaubt
        try:
            revoke_invitation(db_path, inv_id, host.id)
            raise AssertionError("sollte InvalidTransitionError werfen")
        except InvalidTransitionError:
            pass

        # list_invitations_for_user / list_invitations_for_party
        for_user = list_invitations_for_user(db_path, guest.id)
        assert len(for_user) == 1
        for_user_filtered = list_invitations_for_user(db_path, guest.id, status=RsvpStatus.REVOKED)
        assert len(for_user_filtered) == 1
        for_user_wrong_status = list_invitations_for_user(db_path, guest.id, status=RsvpStatus.ACCEPTED)
        assert len(for_user_wrong_status) == 0
        for_party = list_invitations_for_party(db_path, party.id)
        assert len(for_party) == 1

        for_stranger = list_invitations_for_user(db_path, stranger.id)
        assert len(for_stranger) == 0

        print("accounts/invitation_storage.py sanity check OK.")
