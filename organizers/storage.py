"""SQLite-Persistenz für ``Organizer``/``OrganizerMembership``
(Social-Graph-Phase-4). Mirrort ``accounts/party_storage.py``'s Muster
(atomische Entity+Owner-Membership-Erstellung, ON-CONFLICT-Upsert für
Mitgliedschaften) - beide Tabellen sind brandneu, daher keine
``ALTER TABLE``-Migrations-Dict nötig (anders als z.B.
``accounts/profile_storage.py``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from organizers.domain import Organizer, OrganizerMembership, OrganizerRole, OrganizerVerificationStatus


def init_organizer_storage(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS organizers (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                organizer_type TEXT NOT NULL DEFAULT '',
                verification_status TEXT NOT NULL DEFAULT 'unverified',
                description TEXT NOT NULL DEFAULT '',
                website_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (owner_user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_organizers_owner ON organizers(owner_user_id)")
        # Hot Path für is_user_verified_organizer_member (auf jedem Publish-
        # Versuch aufgerufen).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_organizers_verification_status ON organizers(verification_status)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS organizer_memberships (
                id TEXT PRIMARY KEY,
                organizer_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(organizer_id, user_id),
                FOREIGN KEY (organizer_id) REFERENCES organizers(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_org_memberships_user ON organizer_memberships(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_org_memberships_organizer ON organizer_memberships(organizer_id)")


def _row_to_organizer(row: sqlite3.Row) -> Organizer:
    return Organizer(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        display_name=row["display_name"],
        organizer_type=row["organizer_type"],
        verification_status=OrganizerVerificationStatus(row["verification_status"]),
        description=row["description"],
        website_url=row["website_url"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_membership(row: sqlite3.Row) -> OrganizerMembership:
    return OrganizerMembership(
        id=row["id"],
        organizer_id=row["organizer_id"],
        user_id=row["user_id"],
        role=OrganizerRole(row["role"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def create_organizer(
    db_path: str | Path,
    organizer_id: str,
    owner_user_id: str,
    display_name: str,
    organizer_type: str = "",
    description: str = "",
    website_url: str = "",
) -> Organizer:
    """Legt den Organizer UND (atomisch, gleiche Transaktion) eine
    ``OWNER``-Membership für den Ersteller an - exaktes Pendant zu
    ``party_storage.create_party``'s Host-Membership-Auto-Erstellung."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO organizers "
            "(id, owner_user_id, display_name, organizer_type, verification_status, description, website_url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                organizer_id, owner_user_id, display_name, organizer_type,
                OrganizerVerificationStatus.UNVERIFIED.value, description, website_url, now, now,
            ),
        )
        conn.execute(
            "INSERT INTO organizer_memberships (id, organizer_id, user_id, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"{organizer_id}:{owner_user_id}", organizer_id, owner_user_id, OrganizerRole.OWNER.value, now, now),
        )
    return Organizer(
        id=organizer_id,
        owner_user_id=owner_user_id,
        display_name=display_name,
        organizer_type=organizer_type,
        verification_status=OrganizerVerificationStatus.UNVERIFIED,
        description=description,
        website_url=website_url,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


def get_organizer(db_path: str | Path, organizer_id: str) -> Organizer | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM organizers WHERE id = ?", (organizer_id,)).fetchone()
    return _row_to_organizer(row) if row is not None else None


def list_organizers_for_user(db_path: str | Path, user_id: str) -> list[tuple[Organizer, OrganizerMembership]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT o.*, m.id AS membership_id, m.role AS membership_role,
                   m.created_at AS membership_created_at, m.updated_at AS membership_updated_at
            FROM organizers o
            JOIN organizer_memberships m ON m.organizer_id = o.id
            WHERE m.user_id = ?
            ORDER BY o.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    result = []
    for row in rows:
        organizer = _row_to_organizer(row)
        membership = OrganizerMembership(
            id=row["membership_id"],
            organizer_id=row["id"],
            user_id=user_id,
            role=OrganizerRole(row["membership_role"]),
            created_at=datetime.fromisoformat(row["membership_created_at"]),
            updated_at=datetime.fromisoformat(row["membership_updated_at"]),
        )
        result.append((organizer, membership))
    return result


def get_membership(db_path: str | Path, organizer_id: str, user_id: str) -> OrganizerMembership | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM organizer_memberships WHERE organizer_id = ? AND user_id = ?", (organizer_id, user_id)
        ).fetchone()
    return _row_to_membership(row) if row is not None else None


def upsert_membership(db_path: str | Path, organizer_id: str, user_id: str, role: OrganizerRole) -> OrganizerMembership:
    now = datetime.now().isoformat()
    membership_id = f"{organizer_id}:{user_id}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO organizer_memberships (id, organizer_id, user_id, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(organizer_id, user_id) DO UPDATE SET
                role = excluded.role, updated_at = excluded.updated_at
            """,
            (membership_id, organizer_id, user_id, role.value, now, now),
        )
    return get_membership(db_path, organizer_id, user_id)


def list_members(db_path: str | Path, organizer_id: str) -> list[OrganizerMembership]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM organizer_memberships WHERE organizer_id = ? ORDER BY created_at", (organizer_id,)
        ).fetchall()
    return [_row_to_membership(r) for r in rows]


def set_verification_status(db_path: str | Path, organizer_id: str, status: OrganizerVerificationStatus) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE organizers SET verification_status = ?, updated_at = ? WHERE id = ?",
            (status.value, datetime.now().isoformat(), organizer_id),
        )


def list_organizers(db_path: str | Path) -> list[Organizer]:
    """Admin-Listing (mirrors ``user_storage.list_users``) - keine
    Pagination, diese App hat in diesem Umfang keinen Bedarf dafür."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM organizers ORDER BY created_at DESC").fetchall()
    return [_row_to_organizer(r) for r in rows]


def is_user_verified_organizer_member(db_path: str | Path, user_id: str) -> bool:
    """Der zentrale Publish-Gate-Check (Social-Graph-Phase-4): ersetzt
    funktional das alte ``User.is_verified`` (siehe
    ``backend/app/routers/parties.py::_host_is_verified``). Gilt für JEDE
    Rolle, nicht nur ``OWNER`` - schon Mitglied eines verifizierten
    Organizers zu sein reicht aus, unabhängig von der eigenen Rolle darin."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM organizer_memberships m
            JOIN organizers o ON o.id = m.organizer_id
            WHERE m.user_id = ? AND o.verification_status = ?
            LIMIT 1
            """,
            (user_id, OrganizerVerificationStatus.VERIFIED.value),
        ).fetchone()
    return row is not None


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_organizer_storage.db"
        user_storage.init_user_storage(db_path)
        init_organizer_storage(db_path)
        init_organizer_storage(db_path)  # idempotent

        owner = user_storage.create_user(db_path, uuid.uuid4().hex, "owner@example.com", "hash", "Owner")
        member = user_storage.create_user(db_path, uuid.uuid4().hex, "member@example.com", "hash", "Member")

        organizer = create_organizer(db_path, uuid.uuid4().hex, owner.id, "Acme Events", organizer_type="company")
        assert organizer.display_name == "Acme Events"
        assert organizer.verification_status == OrganizerVerificationStatus.UNVERIFIED

        owner_membership = get_membership(db_path, organizer.id, owner.id)
        assert owner_membership is not None
        assert owner_membership.role == OrganizerRole.OWNER

        assert get_organizer(db_path, "unknown") is None
        assert get_membership(db_path, organizer.id, "unknown") is None

        upsert_membership(db_path, organizer.id, member.id, OrganizerRole.EDITOR)
        member_membership = get_membership(db_path, organizer.id, member.id)
        assert member_membership.role == OrganizerRole.EDITOR

        members = list_members(db_path, organizer.id)
        assert len(members) == 2

        upsert_membership(db_path, organizer.id, member.id, OrganizerRole.ADMIN)
        assert get_membership(db_path, organizer.id, member.id).role == OrganizerRole.ADMIN
        assert len(list_members(db_path, organizer.id)) == 2  # weiterhin nur 2 (Upsert, kein Duplikat)

        organizers_for_owner = list_organizers_for_user(db_path, owner.id)
        assert len(organizers_for_owner) == 1
        assert organizers_for_owner[0][0].id == organizer.id
        assert organizers_for_owner[0][1].role == OrganizerRole.OWNER

        assert is_user_verified_organizer_member(db_path, owner.id) is False
        assert is_user_verified_organizer_member(db_path, member.id) is False

        set_verification_status(db_path, organizer.id, OrganizerVerificationStatus.VERIFIED)
        assert get_organizer(db_path, organizer.id).verification_status == OrganizerVerificationStatus.VERIFIED
        assert is_user_verified_organizer_member(db_path, owner.id) is True
        assert is_user_verified_organizer_member(db_path, member.id) is True  # jede Rolle zaehlt

        set_verification_status(db_path, organizer.id, OrganizerVerificationStatus.SUSPENDED)
        assert is_user_verified_organizer_member(db_path, owner.id) is False

        assert any(o.id == organizer.id for o in list_organizers(db_path))

        print("organizers/storage.py sanity check OK.")
