"""
Admin Catalog Curation Storage & Filter-Logik.
=================================================

Persistenz für ``CatalogCurationSettings`` (siehe party_engine/domain.py):
erlaubt dem Admin, die für Gäste sichtbare Getränke-/Speisen-Auswahl auf eine
selbst gewählte "engere Auswahl" zu limitieren. Mirroring des
sqlite3-Single-Row-Upsert-Musters aus ``event_theme.py``/
``music_engine/admin_settings.py`` (dieses Modul ist bewusst ebenfalls
Streamlit-frei, reines sqlite3 + Dataclasses).

Zwei Tabellen: ``catalog_curation_settings`` (Single-Row, nur der
``enabled``-Schalter) und ``catalog_curated_items`` (eine Zeile pro
kuratierter Item-ID - beliebig viele, sowohl Getränke als auch Speisen in
derselben Tabelle, die Domain-Zuordnung ergibt sich bereits aus
``item.demand_group`` beim Filtern).

Verwendung ("Party Planning.py"):
    import party_engine.catalog_curation as catalog_curation

    catalog_curation.init_catalog_curation(DB_PATH)   # einmal beim App-Start
    settings = catalog_curation.get_catalog_curation_settings(DB_PATH)
    catalog_curation.save_catalog_curation_settings(DB_PATH, settings)

    visible_items = catalog_curation.filter_items_by_curation(items, settings)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from party_engine.domain import CatalogCurationSettings, CatalogItem


def init_catalog_curation(db_path: str | Path) -> None:
    """Legt die Curation-Tabellen an, falls sie noch nicht existieren, und
    fügt die Default-Einstellungszeile ein. Sicher bei jedem App-Start
    aufrufbar (mirroring event_theme.init_party_settings())."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_curation_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_curated_items (
                item_id TEXT PRIMARY KEY
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO catalog_curation_settings (id, enabled) VALUES (1, 0)")


def get_catalog_curation_settings(db_path: str | Path) -> CatalogCurationSettings:
    """Liest die aktuellen Curation-Settings. Gibt bei fehlender Zeile
    (z.B. ``init_catalog_curation`` noch nicht aufgerufen) sicherheitshalber
    die reinen Dataclass-Defaults zurück (enabled=False, kein Effekt) - wirft
    nie."""
    with sqlite3.connect(db_path) as conn:
        try:
            row = conn.execute("SELECT enabled FROM catalog_curation_settings WHERE id = 1").fetchone()
            item_rows = conn.execute("SELECT item_id FROM catalog_curated_items").fetchall()
        except sqlite3.OperationalError:
            # Tabellen existieren noch nicht (init_catalog_curation() nicht aufgerufen).
            return CatalogCurationSettings()
    if row is None:
        return CatalogCurationSettings()
    return CatalogCurationSettings(
        enabled=bool(row[0]),
        curated_item_ids={item_id for (item_id,) in item_rows},
    )


def save_catalog_curation_settings(db_path: str | Path, settings: CatalogCurationSettings) -> None:
    """Speichert die Curation-Settings (Single-Row-Upsert für ``enabled`` +
    komplette Neu-Befüllung von ``catalog_curated_items`` - die kuratierte
    Menge wird beim Speichern immer vollständig ersetzt, kein inkrementelles
    Hinzufügen/Entfernen einzelner IDs nötig)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO catalog_curation_settings (id, enabled) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled
            """,
            (int(settings.enabled),),
        )
        conn.execute("DELETE FROM catalog_curated_items")
        if settings.curated_item_ids:
            conn.executemany(
                "INSERT INTO catalog_curated_items (item_id) VALUES (?)",
                [(item_id,) for item_id in sorted(settings.curated_item_ids)],
            )


def filter_items_by_curation(
    items: list[CatalogItem], settings: CatalogCurationSettings
) -> list[CatalogItem]:
    """Wendet die Admin-Limitierung an: ist ``enabled`` False ODER keine
    Items kuratiert, werden ALLE Items unverändert zurückgegeben (kein
    versehentliches Leer-Rendern der Gäste-Auswahl, falls der Admin die
    Limitierung aktiviert, aber noch nichts ausgewählt hat). Ist ``enabled``
    True UND mindestens ein Item kuratiert, werden NUR die kuratierten IDs
    behalten - Reihenfolge der Eingabeliste bleibt erhalten."""
    if not settings.enabled or not settings.curated_item_ids:
        return items
    return [item for item in items if item.id in settings.curated_item_ids]


if __name__ == "__main__":
    import tempfile

    from party_engine.domain import DirectConsumable

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_catalog_curation.db"
        init_catalog_curation(db_path)
        init_catalog_curation(db_path)  # idempotent, darf nicht crashen

        default_settings = get_catalog_curation_settings(db_path)
        assert default_settings.enabled is False
        assert default_settings.curated_item_ids == set()

        beer = DirectConsumable(id="beer_pils", name="Pils", category="beer", demand_group="alcoholic_beverage")
        chai = DirectConsumable(id="masala_chai", name="Chai", category="tea", demand_group="non_alcoholic_beverage")
        pizza = DirectConsumable(id="pizza_margherita", name="Pizza", category="main", demand_group="food")
        items = [beer, chai, pizza]

        # enabled=False -> kein Effekt, alle Items sichtbar.
        assert filter_items_by_curation(items, default_settings) == items

        # enabled=True, aber keine kuratierten IDs -> Sicherheits-Fallback: alle Items sichtbar.
        enabled_but_empty = CatalogCurationSettings(enabled=True, curated_item_ids=set())
        assert filter_items_by_curation(items, enabled_but_empty) == items

        # enabled=True mit konkreter Auswahl -> NUR diese Items.
        curated = CatalogCurationSettings(enabled=True, curated_item_ids={"beer_pils", "pizza_margherita"})
        filtered = filter_items_by_curation(items, curated)
        assert {i.id for i in filtered} == {"beer_pils", "pizza_margherita"}
        assert chai not in filtered

        # Round-Trip über die Persistenz.
        save_catalog_curation_settings(db_path, curated)
        reloaded = get_catalog_curation_settings(db_path)
        assert reloaded.enabled is True
        assert reloaded.curated_item_ids == {"beer_pils", "pizza_margherita"}

        # Erneutes Speichern ersetzt die kuratierte Menge vollständig.
        save_catalog_curation_settings(db_path, CatalogCurationSettings(enabled=False, curated_item_ids={"masala_chai"}))
        reloaded2 = get_catalog_curation_settings(db_path)
        assert reloaded2.enabled is False
        assert reloaded2.curated_item_ids == {"masala_chai"}

        print("party_engine/catalog_curation.py sanity check OK.")
