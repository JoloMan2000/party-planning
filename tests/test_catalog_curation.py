"""Tests für die Admin-Limitierung der Getränke-/Speisenauswahl
(``party_engine/catalog_curation.py``): erlaubt dem Admin, die für Gäste
sichtbare Auswahl auf eine selbst gewählte "engere Auswahl" zu limitieren.

Nutzt den ECHTEN Katalog (kein Mocking, siehe conftest.py / AUFGABE §43) für
die Filter-Szenarien und eine temporäre sqlite-DB (``tmp_path``) für die
Persistenz-Tests.
"""

from __future__ import annotations

from party_engine.catalog_curation import (
    filter_items_by_curation,
    get_catalog_curation_settings,
    init_catalog_curation,
    save_catalog_curation_settings,
)
from party_engine.domain import CatalogCurationSettings


def test_disabled_gibt_alle_items_zurueck(catalog):
    items = catalog.all_selectable_items()
    settings = CatalogCurationSettings(enabled=False, curated_item_ids={"beer_pils"})
    assert filter_items_by_curation(items, settings) == items


def test_enabled_aber_leer_gibt_alle_items_zurueck_sicherheitsfallback(catalog):
    items = catalog.all_selectable_items()
    settings = CatalogCurationSettings(enabled=True, curated_item_ids=set())
    assert filter_items_by_curation(items, settings) == items


def test_enabled_mit_auswahl_filtert_auf_kuratierte_ids(catalog):
    items = catalog.all_selectable_items()
    beer = catalog.get_item("beer_pils")
    assert beer is not None
    settings = CatalogCurationSettings(enabled=True, curated_item_ids={"beer_pils"})
    filtered = filter_items_by_curation(items, settings)
    assert {i.id for i in filtered} == {"beer_pils"}
    assert len(filtered) < len(items)


def test_filter_behaelt_reihenfolge_der_eingabeliste(catalog):
    items = catalog.all_selectable_items()
    curated_ids = {items[2].id, items[0].id}
    settings = CatalogCurationSettings(enabled=True, curated_item_ids=curated_ids)
    filtered = filter_items_by_curation(items, settings)
    assert [i.id for i in filtered] == [items[0].id, items[2].id]


def test_init_ist_idempotent(tmp_path):
    db_path = tmp_path / "curation.db"
    init_catalog_curation(db_path)
    init_catalog_curation(db_path)  # darf nicht crashen

    settings = get_catalog_curation_settings(db_path)
    assert settings.enabled is False
    assert settings.curated_item_ids == set()


def test_save_und_reload_roundtrip(tmp_path):
    db_path = tmp_path / "curation.db"
    init_catalog_curation(db_path)

    settings = CatalogCurationSettings(enabled=True, curated_item_ids={"beer_pils", "masala_chai"})
    save_catalog_curation_settings(db_path, settings)

    reloaded = get_catalog_curation_settings(db_path)
    assert reloaded.enabled is True
    assert reloaded.curated_item_ids == {"beer_pils", "masala_chai"}


def test_erneutes_speichern_ersetzt_kuratierte_menge_vollstaendig(tmp_path):
    db_path = tmp_path / "curation.db"
    init_catalog_curation(db_path)

    save_catalog_curation_settings(
        db_path, CatalogCurationSettings(enabled=True, curated_item_ids={"beer_pils"})
    )
    save_catalog_curation_settings(
        db_path, CatalogCurationSettings(enabled=False, curated_item_ids={"masala_chai"})
    )

    reloaded = get_catalog_curation_settings(db_path)
    assert reloaded.enabled is False
    assert reloaded.curated_item_ids == {"masala_chai"}


def test_get_settings_ohne_init_wirft_nicht(tmp_path):
    db_path = tmp_path / "never_initialized.db"
    # Kein init_catalog_curation() aufgerufen -> Tabellen existieren nicht.
    settings = get_catalog_curation_settings(db_path)
    assert settings == CatalogCurationSettings()
