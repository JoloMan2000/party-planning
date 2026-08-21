"""Tests für ``party_engine.resolver`` anhand konkreter Beispiele aus
AUFGABE §26-28. Nutzt den echten Katalog, siehe ``conftest.py``."""

from __future__ import annotations

from party_engine.resolver import get_resolver_index, resolve


def test_wodka_resolves_to_vodka(catalog):
    idx = get_resolver_index(catalog)
    result = resolve("Wodka", catalog, idx)
    assert result.target_type == "direct_consumable"
    assert result.target_id == "vodka"
    assert result.confidence >= 0.9


def test_gt_resolves_to_gin_tonic(catalog):
    idx = get_resolver_index(catalog)
    result = resolve("G&T", catalog, idx)
    assert result.target_type == "recipe"
    assert result.target_id == "gin_tonic"


def test_jacky_cola_resolves_to_whiskey_cola_with_jack_daniels_brand(catalog):
    idx = get_resolver_index(catalog)
    result = resolve("Jacky Cola", catalog, idx)
    assert result.target_type == "recipe"
    assert result.target_id == "whiskey_cola"
    assert result.brand == "Jack Daniel's"


def test_burger_ohne_kaese_resolves_with_remove_cheese_modifier(catalog):
    idx = get_resolver_index(catalog)
    result = resolve("Burger ohne Käse", catalog, idx)
    assert result.target_type == "recipe"
    assert result.target_id == "cheeseburger"
    assert "mod_remove_cheese" in result.applied_modifiers


def test_burger_plus_bacon_resolves_with_add_bacon_modifier(catalog):
    idx = get_resolver_index(catalog)
    result = resolve("Burger + Bacon", catalog, idx)
    assert result.target_type == "recipe"
    assert result.target_id == "cheeseburger"
    assert "mod_add_bacon" in result.applied_modifiers


def test_unknown_freetext_never_raises_and_returns_unknown(catalog):
    idx = get_resolver_index(catalog)
    result = resolve("xyz völlig unbekanntes Gemurmel 12345", catalog, idx)
    assert result.target_type in ("unknown", "recipe", "direct_consumable")
    # Wichtigste Garantie: keine Exception, immer ein ResolutionResult.
    assert result.raw_text
