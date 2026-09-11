"""SQLite-Persistenz für das Host-Equipment-Inventar (Spec §7) - im
Gegensatz zu Food/Beverage/Music (die alle live neu berechnet werden, siehe
``backend/app/routers/admin_shopping_list.py``) ist das Inventar ECHTE,
dauerhafte User-Daten (mirrort ``accounts/profile_storage.py``) und braucht
eine echte Tabelle + CRUD von Anfang an.

``UNIQUE(owner_user_id, equipment_item_id)``: eine Zeile pro (Host,
Katalog-Item) - "2 Beer-Pong-Tische besitzen" ist ``quantity=2`` auf EINER
Zeile, nicht zwei Zeilen. Ein zweiter ``create_inventory_item``-Aufruf für
dasselbe Paar wirft ``InventoryItemAlreadyExistsError`` (Router -> 409,
mirrort ``social/friend_requests.py::FriendRequestAlreadyExistsError``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from equipment_engine.domain import PartyEquipmentInventoryItem


class InventoryItemAlreadyExistsError(Exception):
    """Es existiert bereits eine Inventar-Zeile für (owner_user_id,
    equipment_item_id) - der Aufrufer sollte stattdessen ``update_inventory_item``
    verwenden."""


def init_equipment_storage(db_path: str | Path) -> None:
    """Legt ``equipment_inventory`` an, falls nicht vorhanden. Idempotent,
    sicher bei jedem App-Start aufrufbar (mirrort ``party_context/storage.py``'s
    Migrations-Idiom - aktuell ohne ``ALTER TABLE``-Migrationen, da die
    Tabelle brandneu ist, mirrort ``organizers/storage.py``)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_inventory (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id),
                equipment_item_id TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 1.0,
                condition TEXT NOT NULL DEFAULT '',
                available INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_user_id, equipment_item_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_equipment_inventory_owner ON equipment_inventory(owner_user_id)"
        )


def _row_to_item(row: sqlite3.Row) -> PartyEquipmentInventoryItem:
    return PartyEquipmentInventoryItem(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        equipment_item_id=row["equipment_item_id"],
        quantity=row["quantity"],
        condition=row["condition"],
        available=bool(row["available"]),
        notes=row["notes"],
    )


def create_inventory_item(
    db_path: str | Path,
    item_id: str,
    owner_user_id: str,
    equipment_item_id: str,
    *,
    quantity: float = 1.0,
    condition: str = "",
    available: bool = True,
    notes: str = "",
) -> PartyEquipmentInventoryItem:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO equipment_inventory
                    (id, owner_user_id, equipment_item_id, quantity, condition, available, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, owner_user_id, equipment_item_id, quantity, condition, int(available), notes, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise InventoryItemAlreadyExistsError(
                f"{owner_user_id} already has an inventory row for {equipment_item_id}"
            ) from exc
    return PartyEquipmentInventoryItem(
        id=item_id, owner_user_id=owner_user_id, equipment_item_id=equipment_item_id,
        quantity=quantity, condition=condition, available=available, notes=notes,
    )


def list_inventory_for_user(db_path: str | Path, owner_user_id: str) -> list[PartyEquipmentInventoryItem]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM equipment_inventory WHERE owner_user_id = ? ORDER BY created_at", (owner_user_id,)
        ).fetchall()
    return [_row_to_item(r) for r in rows]


def get_inventory_item(db_path: str | Path, item_id: str) -> PartyEquipmentInventoryItem | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM equipment_inventory WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row is not None else None


def update_inventory_item(
    db_path: str | Path,
    item_id: str,
    *,
    quantity: float | None = None,
    condition: str | None = None,
    available: bool | None = None,
    notes: str | None = None,
) -> PartyEquipmentInventoryItem | None:
    """Partial Update - ``None`` bedeutet je Feld "unverändert lassen"
    (mirrort ``ProfileUpdateRequest``/``SocialPrivacyUpdateRequest``-Konvention).
    Liefert ``None``, falls die Zeile nicht existiert."""
    fields: dict[str, object] = {}
    if quantity is not None:
        fields["quantity"] = quantity
    if condition is not None:
        fields["condition"] = condition
    if available is not None:
        fields["available"] = int(available)
    if notes is not None:
        fields["notes"] = notes

    if fields:
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{col} = ?" for col in fields)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                f"UPDATE equipment_inventory SET {set_clause} WHERE id = ?",
                (*fields.values(), item_id),
            )
    return get_inventory_item(db_path, item_id)


def delete_inventory_item(db_path: str | Path, item_id: str) -> None:
    """No-Op, falls keine Zeile existiert (mirrort ``remove_friendship``/
    ``unfollow_organizer``-Idempotenz-Konvention)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM equipment_inventory WHERE id = ?", (item_id,))


if __name__ == "__main__":
    import tempfile
    import uuid

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "equipment_storage_selftest.db"
        init_equipment_storage(db_path)

        owner = uuid.uuid4().hex
        item_id = uuid.uuid4().hex
        created = create_inventory_item(db_path, item_id, owner, "wine_glass", quantity=12.0)
        assert created.quantity == 12.0

        try:
            create_inventory_item(db_path, uuid.uuid4().hex, owner, "wine_glass", quantity=1.0)
            raise AssertionError("expected InventoryItemAlreadyExistsError")
        except InventoryItemAlreadyExistsError:
            pass

        assert len(list_inventory_for_user(db_path, owner)) == 1

        updated = update_inventory_item(db_path, item_id, quantity=20.0)
        assert updated is not None and updated.quantity == 20.0
        assert updated.condition == ""  # unverändert

        delete_inventory_item(db_path, item_id)
        assert get_inventory_item(db_path, item_id) is None
        delete_inventory_item(db_path, item_id)  # idempotent, kein Fehler

        print("OK: equipment_engine.storage self-test passed.")
