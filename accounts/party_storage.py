"""SQLite-Persistenz für Multi-Tenant-Parties + Party-Memberships
(Account-basierter Pivot, Phase 1). Mirrort das Muster aus
``accounts/user_storage.py``/``party_context/storage.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from accounts.domain import Party, PartyMembership, PartyRole, RsvpStatus


def init_party_storage(db_path: str | Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parties (
                id TEXT PRIMARY KEY,
                host_user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                starts_at TEXT,
                location TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (host_user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parties_host ON parties(host_user_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_memberships (
                id TEXT PRIMARY KEY,
                party_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                rsvp_status TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(party_id, user_id),
                FOREIGN KEY (party_id) REFERENCES parties(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memberships_user ON party_memberships(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memberships_party ON party_memberships(party_id)")


def _row_to_party(row: sqlite3.Row) -> Party:
    return Party(
        id=row["id"],
        host_user_id=row["host_user_id"],
        name=row["name"],
        description=row["description"],
        starts_at=datetime.fromisoformat(row["starts_at"]) if row["starts_at"] else None,
        location=row["location"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_membership(row: sqlite3.Row) -> PartyMembership:
    return PartyMembership(
        id=row["id"],
        party_id=row["party_id"],
        user_id=row["user_id"],
        role=PartyRole(row["role"]),
        rsvp_status=RsvpStatus(row["rsvp_status"]),
        joined_at=datetime.fromisoformat(row["joined_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def create_party(
    db_path: str | Path,
    party_id: str,
    host_user_id: str,
    name: str,
    description: str = "",
    starts_at: datetime | None = None,
    location: str = "",
) -> Party:
    """Legt die Party UND (atomisch, gleiche Transaktion) eine
    ``host``/``accepted``-Membership für den Ersteller an - der Host muss
    seiner eigenen Party nie zusagen."""
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO parties (id, host_user_id, name, description, starts_at, location, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (party_id, host_user_id, name, description, starts_at.isoformat() if starts_at else None, location, now, now),
        )
        conn.execute(
            "INSERT INTO party_memberships (id, party_id, user_id, role, rsvp_status, joined_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"{party_id}:{host_user_id}", party_id, host_user_id, PartyRole.HOST.value, RsvpStatus.ACCEPTED.value, now, now),
        )
    return Party(
        id=party_id,
        host_user_id=host_user_id,
        name=name,
        description=description,
        starts_at=starts_at,
        location=location,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


def get_party(db_path: str | Path, party_id: str) -> Party | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM parties WHERE id = ?", (party_id,)).fetchone()
    return _row_to_party(row) if row is not None else None


def update_party(db_path: str | Path, party_id: str, **fields) -> Party | None:
    """Partielles Update - nur übergebene Keys werden geändert."""
    allowed = {"name", "description", "starts_at", "location"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_party(db_path, party_id)
    if "starts_at" in updates and isinstance(updates["starts_at"], datetime):
        updates["starts_at"] = updates["starts_at"].isoformat()
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"UPDATE parties SET {set_clause} WHERE id = ?", (*updates.values(), party_id))
    return get_party(db_path, party_id)


def get_membership(db_path: str | Path, party_id: str, user_id: str) -> PartyMembership | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM party_memberships WHERE party_id = ? AND user_id = ?", (party_id, user_id)
        ).fetchone()
    return _row_to_membership(row) if row is not None else None


def upsert_membership(
    db_path: str | Path, party_id: str, user_id: str, role: PartyRole, rsvp_status: RsvpStatus
) -> PartyMembership:
    now = datetime.now().isoformat()
    membership_id = f"{party_id}:{user_id}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO party_memberships (id, party_id, user_id, role, rsvp_status, joined_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(party_id, user_id) DO UPDATE SET
                role = excluded.role, rsvp_status = excluded.rsvp_status, updated_at = excluded.updated_at
            """,
            (membership_id, party_id, user_id, role.value, rsvp_status.value, now, now),
        )
    return get_membership(db_path, party_id, user_id)


def list_memberships_for_party(db_path: str | Path, party_id: str) -> list[PartyMembership]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM party_memberships WHERE party_id = ? ORDER BY joined_at", (party_id,)
        ).fetchall()
    return [_row_to_membership(r) for r in rows]


def list_parties_for_user(db_path: str | Path, user_id: str) -> list[tuple[Party, PartyMembership]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT p.*, m.id AS membership_id, m.role AS membership_role,
                   m.rsvp_status AS membership_rsvp_status, m.joined_at AS membership_joined_at,
                   m.updated_at AS membership_updated_at
            FROM parties p
            JOIN party_memberships m ON m.party_id = p.id
            WHERE m.user_id = ?
            ORDER BY p.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    result = []
    for row in rows:
        party = _row_to_party(row)
        membership = PartyMembership(
            id=row["membership_id"],
            party_id=row["id"],
            user_id=user_id,
            role=PartyRole(row["membership_role"]),
            rsvp_status=RsvpStatus(row["membership_rsvp_status"]),
            joined_at=datetime.fromisoformat(row["membership_joined_at"]),
            updated_at=datetime.fromisoformat(row["membership_updated_at"]),
        )
        result.append((party, membership))
    return result


def count_rsvp_statuses(db_path: str | Path, party_id: str) -> dict[str, int]:
    """Liefert eine vollständige Aggregation (alle RsvpStatus-Keys, auch bei
    0) für Gäste (Rolle != host/co_host) einer Party (AUFGABE-Spec §57)."""
    counts = {status.value: 0 for status in RsvpStatus}
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT rsvp_status, COUNT(*) FROM party_memberships WHERE party_id = ? AND role = ? GROUP BY rsvp_status",
            (party_id, PartyRole.GUEST.value),
        ).fetchall()
    for status, count in rows:
        counts[status] = count
    return counts


if __name__ == "__main__":
    import tempfile
    import uuid

    import accounts.user_storage as user_storage

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_party_storage.db"
        user_storage.init_user_storage(db_path)
        init_party_storage(db_path)
        init_party_storage(db_path)  # idempotent

        host = user_storage.create_user(db_path, uuid.uuid4().hex, "host@example.com", "hash", "Host")
        guest = user_storage.create_user(db_path, uuid.uuid4().hex, "guest@example.com", "hash", "Guest")

        party = create_party(db_path, uuid.uuid4().hex, host.id, "Summer BBQ", location="Max's Garden")
        assert party.name == "Summer BBQ"

        host_membership = get_membership(db_path, party.id, host.id)
        assert host_membership is not None
        assert host_membership.role == PartyRole.HOST
        assert host_membership.rsvp_status == RsvpStatus.ACCEPTED

        fetched = get_party(db_path, party.id)
        assert fetched is not None
        assert fetched.location == "Max's Garden"

        updated = update_party(db_path, party.id, name="Summer BBQ 2.0")
        assert updated.name == "Summer BBQ 2.0"
        assert updated.location == "Max's Garden"  # unverändert

        upsert_membership(db_path, party.id, guest.id, PartyRole.GUEST, RsvpStatus.PENDING)
        guest_membership = get_membership(db_path, party.id, guest.id)
        assert guest_membership.rsvp_status == RsvpStatus.PENDING

        memberships = list_memberships_for_party(db_path, party.id)
        assert len(memberships) == 2

        parties_for_guest = list_parties_for_user(db_path, guest.id)
        assert len(parties_for_guest) == 1
        assert parties_for_guest[0][0].id == party.id
        assert parties_for_guest[0][1].role == PartyRole.GUEST

        counts = count_rsvp_statuses(db_path, party.id)
        assert counts["pending"] == 1
        assert counts["accepted"] == 0  # Host zählt nicht (role=host, nicht guest)

        upsert_membership(db_path, party.id, guest.id, PartyRole.GUEST, RsvpStatus.ACCEPTED)
        counts2 = count_rsvp_statuses(db_path, party.id)
        assert counts2["accepted"] == 1
        assert counts2["pending"] == 0

        assert get_party(db_path, "unknown") is None
        assert get_membership(db_path, party.id, "unknown") is None

        print("accounts/party_storage.py sanity check OK.")
