"""Culture-Stammdaten: länderspezifisches Tag-/Genre-Re-Weighting (Geo-Kultur-
Spec §4), spiegelt exakt ``locations.py``'s Muster (kuratierte Teilmenge +
generischer neutraler Fallback für alle übrigen Länder).

**Wichtig - Tag-Vokabular:** ``preferred/discouraged_food_tags`` und
``preferred/discouraged_beverage_tags`` müssen ausschließlich Tags aus der
zentralen Registry ``party_engine.tags.ALL_TAGS`` verwenden (§70-Validierung
in ``build_catalog.py`` erlaubt sonst keine neuen Katalog-Items mit
abweichenden Tags). ``tea`` wurde dafür ergänzt (§4 der Geo-Kultur-Spec,
vorher fehlte ein Tee-Gegenstück zu ``coffee``). Sehr länderspezifische
Begriffe (Currypaste, Ceviche, Pisco, Sake, Aquavit, Smørrebrød, ...) werden
bewusst auf das nächstliegende bestehende Tag abgebildet (z.B. Pisco/Sake ->
``spirit``/``wine``) statt neue Nischen-Tags einzuführen - die tatsächlichen
neuen Katalog-Items (siehe §6) tragen zusätzlich ihre eigenen, bereits
registrierten Charakter-Tags (``fish``, ``seafood``, ``rice``, ``spicy_food``, ...).
``genre_bias`` ist NICHT gegen diese Registry validiert (eigenes, freies
Musik-Genre-Vokabular aus ``music_catalog/tracks.json``).

**Wichtig - kulturelle Sensibilität:** Die Profile bilden BREITE, gut
belegte kulinarische/musikalische Trends ab (z.B. "Tee ist in Indien bei
Feiern verbreiteter als Kaffee"), keine stereotypisierenden Aussagen über
einzelne Personen. Sie wirken NUR als leichtes, gecapptes Re-Weighting
bestehender Tags (analog zu den etablierten Season-/Location-Deltas via
``config.apply_capped_modifier``), NIE als harte Filterung - ein Gast kann
in Indien trotzdem Bier wählen, es wird nur nicht bevorzugt vorgeschlagen.
Genau wie bei Location-Profilen bereits etabliert (§4 der Geo-Kultur-Spec)."""

from __future__ import annotations

from functools import lru_cache

from party_context.domain import CultureProfile

# Kuratierte Länder für den ersten Ausbau (vom Nutzer explizit genannt +
# sinnvolle Ergänzungen für Testabdeckung unterschiedlicher Kulturkreise).
# Alle anderen ISO-3166-1-alpha-2-Codes erhalten über ``get_culture_profile()``
# ein neutrales Fallback-Profil (kein Bias) - spätere Sessions können weitere
# Länder ergänzen, ohne Code zu ändern (reine Daten).
COUNTRY_CULTURE_PROFILES: dict[str, CultureProfile] = {
    "DE": CultureProfile(
        country_code="DE",
        country_name="Germany",
        # Katalog ist heute schon DE-lastig (Baseline) - daher bewusst nur
        # leichtes Tag-Mapping bestehender Items, kaum zusätzlicher Bias nötig.
        preferred_food_tags={"bread": 0.3, "grill": 0.2, "comfort_food": 0.2},
        preferred_beverage_tags={"beer": 0.3, "wine": 0.2},
        genre_bias={"schlager": 0.4, "volksmusik": 0.3, "german_pop": 0.3},
    ),
    "IN": CultureProfile(
        country_code="IN",
        country_name="India",
        preferred_food_tags={"vegetarian": 0.7, "spicy_food": 0.8, "rice": 0.5},
        discouraged_food_tags={"beef": 0.8, "pork": 0.5},
        preferred_beverage_tags={"tea": 0.7, "non_alcoholic": 0.3},
        discouraged_beverage_tags={"beer": 0.2, "wine": 0.2},
        genre_bias={"bollywood": 0.8, "indian_pop": 0.6, "bhangra": 0.5},
    ),
    "PE": CultureProfile(
        country_code="PE",
        country_name="Peru",
        preferred_food_tags={"seafood": 0.7, "fish": 0.6, "fresh": 0.4, "spicy_food": 0.4},
        preferred_beverage_tags={"spirit": 0.6, "cocktail": 0.3},
        genre_bias={"latin": 0.7, "reggaeton": 0.5, "cumbia": 0.6},
    ),
    "DK": CultureProfile(
        country_code="DK",
        country_name="Denmark",
        preferred_food_tags={"fish": 0.5, "comfort_food": 0.5, "bread": 0.4},
        preferred_beverage_tags={"spirit": 0.5, "beer": 0.4, "coffee": 0.4},
        genre_bias={"indie_rock": 0.4, "pop": 0.3},
    ),
    "JP": CultureProfile(
        country_code="JP",
        country_name="Japan",
        preferred_food_tags={"seafood": 0.6, "fish": 0.6, "rice": 0.6, "fresh": 0.6, "light_food": 0.5},
        discouraged_food_tags={"comfort_food": 0.3},
        preferred_beverage_tags={"tea": 0.6, "wine": 0.3},
        genre_bias={"jpop": 0.8, "city_pop": 0.6},
    ),
    "US": CultureProfile(
        country_code="US",
        country_name="United States",
        preferred_food_tags={"bbq": 0.6, "grill": 0.5, "meat": 0.4, "comfort_food": 0.4},
        preferred_beverage_tags={"beer": 0.6, "cocktail": 0.5, "spirit": 0.5},
        genre_bias={"hip_hop": 0.4, "country": 0.4, "rock": 0.3},
    ),
}

_NEUTRAL_FALLBACK = CultureProfile(country_code="", country_name="")


@lru_cache(maxsize=None)
def get_culture_profile(country_code: str) -> CultureProfile:
    """Liefert das ``CultureProfile`` für einen ISO-3166-1-alpha-2-Ländercode.
    Nie ``None`` - liefert bei unbekanntem/leerem ``country_code`` ein
    neutrales Profil (alle Tag-Dicts leer -> kein Bias), mirrors
    ``locations.get_location_profile()``'s Fallback-Konvention."""
    if not country_code:
        return _NEUTRAL_FALLBACK
    return COUNTRY_CULTURE_PROFILES.get(country_code.upper(), _NEUTRAL_FALLBACK)


if __name__ == "__main__":
    from party_engine.tags import validate_tags

    de = get_culture_profile("DE")
    assert de.country_name == "Germany"
    assert de.genre_bias["schlager"] == 0.4

    india = get_culture_profile("in")  # lowercase-Eingabe muss funktionieren
    assert india.country_code == "IN"
    assert india.preferred_food_tags["vegetarian"] == 0.7
    assert india.discouraged_food_tags["beef"] == 0.8
    assert india.preferred_beverage_tags["tea"] == 0.7

    japan = get_culture_profile("JP")
    assert japan.preferred_beverage_tags["tea"] == 0.6
    assert japan.genre_bias["jpop"] == 0.8

    unknown = get_culture_profile("ZZ")
    assert unknown.preferred_food_tags == {}
    assert unknown.genre_bias == {}

    empty = get_culture_profile("")
    assert empty.preferred_food_tags == {}

    # §4: alle food/beverage Tags müssen aus der zentralen Registry stammen.
    for profile in COUNTRY_CULTURE_PROFILES.values():
        food_tags = set(profile.preferred_food_tags) | set(profile.discouraged_food_tags)
        bev_tags = set(profile.preferred_beverage_tags) | set(profile.discouraged_beverage_tags)
        assert not validate_tags(food_tags), f"{profile.country_code}: invalid food tags {validate_tags(food_tags)}"
        assert not validate_tags(bev_tags), f"{profile.country_code}: invalid beverage tags {validate_tags(bev_tags)}"

    print("party_context/culture.py sanity check OK.")
