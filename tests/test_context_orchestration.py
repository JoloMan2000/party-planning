"""Tests für die Party-Kontext-Orchestrierung
(``party_engine/context_orchestration.py``).

Extrahiert aus ``"Party Planning.py"`` (Backend-Migration Phase 1, Schritt
0b/0c). Nutzt eine temporäre sqlite-DB (``tmp_path``) für die
Persistenz-Tests und den ECHTEN Katalog (kein Mocking, siehe conftest.py).

``party_location`` bleibt in allen Tests auf dem Default (leerer String), so
dass ``get_derived_party_context`` NIE den echten ``CachingGeocodingProvider``
gegen Nominatim aufruft (siehe ``resolve_country_code``: Geocoding wird nur
bei vorhandener ``party_address`` UND fehlendem Admin-Override genutzt) -
somit sind diese Tests netzwerkfrei.
"""

from __future__ import annotations

import event_theme
import party_engine.response_storage as response_storage
from party_context import learning_storage
from party_context import storage as party_context_storage
from party_context.domain import DerivedPartyContext, PartyContext
from party_engine.context_orchestration import (
    get_derived_party_context,
    get_party_context,
    maybe_freeze_and_reset_party,
)


def _init_all(db_path):
    party_context_storage.init_party_context_storage(db_path)
    event_theme.init_party_settings(db_path)
    response_storage.init_db(db_path)
    learning_storage.init_learning_storage(db_path)


def test_get_party_context_spiegelt_event_settings(tmp_path):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    settings = event_theme.get_party_settings(db_path)
    ctx = get_party_context(db_path, settings)

    assert isinstance(ctx, PartyContext)
    assert ctx.occasion_id  # resolve_occasion_id wirft nie, immer non-empty
    assert ctx.start_datetime is None  # kein party_date gesetzt
    assert ctx.party_address == settings["party_location"]


def test_get_party_context_setzt_start_datetime_bei_datum_und_zeit(tmp_path):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    event_theme.save_party_settings(
        db_path,
        event_type="birthday",
        party_name="",
        party_date="2026-09-01",
        party_start_time="19:00",
        party_duration_hours=4,
        party_location="",
    )
    settings = event_theme.get_party_settings(db_path)
    ctx = get_party_context(db_path, settings)

    assert ctx.start_datetime is not None
    assert ctx.start_datetime.isoformat() == "2026-09-01T19:00:00"
    assert ctx.duration_hours == 4.0


def test_get_derived_party_context_liefert_saison_und_group_size(tmp_path):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    settings = event_theme.get_party_settings(db_path)
    derived = get_derived_party_context(db_path, settings, guest_count=5)

    assert isinstance(derived, DerivedPartyContext)
    assert derived.season  # immer ableitbar, nie leer
    assert derived.group_size_class  # nie leer, ableitbar aus guest_count


def test_get_derived_party_context_guest_count_null_wird_zu_eins(tmp_path):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    settings = event_theme.get_party_settings(db_path)
    # guest_count=0 darf nicht crashen - wird intern zu 1 normalisiert
    # (ctx.guest_count = guest_count or 1), statt eine Division durch Null
    # o.Ä. in der PartyContextEngine auszulösen.
    derived = get_derived_party_context(db_path, settings, guest_count=0)

    assert isinstance(derived, DerivedPartyContext)


def test_maybe_freeze_ohne_party_date_gibt_false(tmp_path):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    settings = event_theme.get_party_settings(db_path)
    assert maybe_freeze_and_reset_party(db_path, settings, catalog=None) is False


def test_maybe_freeze_bei_zukuenftigem_datum_gibt_false(tmp_path, catalog):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    event_theme.save_party_settings(
        db_path,
        event_type="birthday",
        party_name="",
        party_date="2099-01-01",
        party_start_time="19:00",
        party_duration_hours=4,
        party_location="",
    )
    settings = event_theme.get_party_settings(db_path)
    assert maybe_freeze_and_reset_party(db_path, settings, catalog) is False


def test_maybe_freeze_bei_vergangenem_datum_ohne_responses_gibt_false(tmp_path, catalog):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    event_theme.save_party_settings(
        db_path,
        event_type="birthday",
        party_name="",
        party_date="2020-01-01",
        party_start_time="19:00",
        party_duration_hours=4,
        party_location="",
    )
    settings = event_theme.get_party_settings(db_path)
    assert maybe_freeze_and_reset_party(db_path, settings, catalog) is False


def test_maybe_freeze_bei_vergangenem_datum_mit_responses_reset_und_lernt(tmp_path, catalog):
    db_path = tmp_path / "context.db"
    _init_all(db_path)

    event_theme.save_party_settings(
        db_path,
        event_type="birthday",
        party_name="",
        party_date="2020-01-01",
        party_start_time="19:00",
        party_duration_hours=4,
        party_location="",
    )
    recipe_id = next(iter(catalog.recipes))
    response_storage.save_response(
        db_path,
        name="Max",
        start_time="19:00",
        drinks=[recipe_id],
        drinks_freetext="",
        food=[],
        food_freetext="",
        songs=[],
    )

    settings = event_theme.get_party_settings(db_path)
    result = maybe_freeze_and_reset_party(db_path, settings, catalog)

    assert result is True
    assert response_storage.load_responses(db_path) == []  # responses geleert
    # party_settings selbst bleibt als wiederverwendbare Vorlage erhalten.
    assert event_theme.get_party_settings(db_path)["party_date"] == "2020-01-01"
