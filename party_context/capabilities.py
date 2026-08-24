"""Leitet aus den Infrastruktur-Flags einer Party die Menge verfügbarer
``available_capabilities`` ab (Spec §17/§18)."""

from __future__ import annotations

from party_context.domain import PartyContext

# Boolean-Flag -> Menge abgeleiteter Capabilities (§18-Beispiele).
_INFRA_CAPABILITY_MAP: dict[str, set[str]] = {
    "has_grill": {"grill", "hot_food_outdoor", "grill_or_equivalent"},
    "has_kitchen": {"kitchen", "oven", "fryer_or_oven", "grill_or_kitchen"},
    "has_fridge": {"fridge", "cooling"},
    "has_freezer": {"freezer", "cooling"},
    "has_ice_machine": {"ice", "ice_machine"},
    "has_bar": {"bar_setup", "cocktail_service", "shaker_possible"},
    "has_coffee_machine": {"espresso", "coffee_service"},
    "has_power": {"power"},
    "has_running_water": {"running_water"},
}


def derive_capabilities(party_context: PartyContext) -> set[str]:
    """Erzeugt ``available_capabilities`` aus den Infrastruktur-Flags einer
    Party (§17/§18). ``has_grill`` UND ``has_kitchen`` liefern zusätzlich das
    kombinierte Grill-oder-Küche-Tag, das viele Food-Rezepte als
    ``required_capabilities`` erwarten (§61)."""
    capabilities: set[str] = set()
    for flag_name, derived in _INFRA_CAPABILITY_MAP.items():
        if getattr(party_context, flag_name, False):
            capabilities |= derived

    if party_context.has_grill or party_context.has_kitchen:
        capabilities.add("grill_or_kitchen")
    if party_context.has_fridge and party_context.has_ice_machine:
        capabilities.add("ice_machine")
    if party_context.dancing_possible:
        capabilities.add("dancefloor")
    if party_context.self_service:
        capabilities.add("self_service")
    return capabilities


if __name__ == "__main__":
    ctx = PartyContext(has_grill=True, has_bar=True, has_coffee_machine=True, dancing_possible=True)
    caps = derive_capabilities(ctx)
    assert "grill" in caps
    assert "hot_food_outdoor" in caps
    assert "grill_or_equivalent" in caps
    assert "cocktail_service" in caps
    assert "shaker_possible" in caps
    assert "espresso" in caps
    assert "coffee_service" in caps
    assert "dancefloor" in caps
    assert "grill_or_kitchen" in caps

    empty_ctx = PartyContext()
    assert derive_capabilities(empty_ctx) == {"self_service"}
    print(f"capabilities (grill+bar+coffee) -> {sorted(caps)}")
    print("party_context/capabilities.py sanity check OK.")
