"""
Katalog-Generator für die Unified Party Demand Engine.
========================================================

Dieses Skript erzeugt die statischen JSON-Kataloge unter catalog/*.json.
Es ist ein reines Daten-Autoring-Werkzeug — die Berechnungsengine
(party_engine/engine.py) liest zur Laufzeit AUSSCHLIESSLICH die
generierten JSON-Dateien und kennt keine konkreten Gerichte/Cocktails.

Ausführen:
    python3 build_catalog.py

Neue Getränke/Speisen können entweder hier ergänzt und neu generiert,
oder direkt in den JSON-Dateien nachgepflegt werden.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from party_engine.domain import (
    DirectConsumable,
    Ingredient,
    PartyCatalog,
    Recipe,
    RecipeComponent,
)
from party_engine.recommendation_tagging import apply_recommendation_metadata
from party_engine.tags import validate_tags

CATALOG_DIR = Path(__file__).parent / "catalog"

# --- Ingredient-Familien: sinnvolle Defaults -----------------------------------

FAMILY_DEFAULTS: dict[str, dict] = {
    "spirit": dict(unit="l", category="spirit", demand_group="alcoholic_beverage",
                   contains_alcohol=True, abv=40.0, is_vegan=True),
    "liqueur": dict(unit="l", category="liqueur", demand_group="alcoholic_beverage",
                     contains_alcohol=True, abv=20.0, is_vegan=True),
    "fortified_wine": dict(unit="l", category="fortified_wine", demand_group="alcoholic_beverage",
                            contains_alcohol=True, abv=17.0, is_vegan=True),
    "wine": dict(unit="l", category="wine", demand_group="alcoholic_beverage",
                 contains_alcohol=True, abv=12.0, is_vegan=True),
    "sparkling_wine": dict(unit="l", category="sparkling_wine", demand_group="alcoholic_beverage",
                            contains_alcohol=True, abv=11.0, is_vegan=True),
    "beer": dict(unit="l", category="beer", demand_group="alcoholic_beverage",
                 contains_alcohol=True, abv=5.0, is_vegan=True),
    "softdrink": dict(unit="l", category="softdrink", demand_group="non_alcoholic_beverage", is_vegan=True),
    "energy": dict(unit="l", category="energy", demand_group="energy", is_vegan=True, contains_caffeine=True),
    "juice": dict(unit="l", category="juice", demand_group="non_alcoholic_beverage", is_vegan=True),
    "syrup": dict(unit="l", category="syrup", demand_group="condiment", is_vegan=True),
    "coffee": dict(unit="l", category="coffee", demand_group="non_alcoholic_beverage",
                    is_vegan=True, contains_caffeine=True),
    "dairy": dict(unit="l", category="dairy", demand_group="condiment", is_vegan=False, lactose_free=False),
    "fruit": dict(unit="kg", category="fruit", demand_group="dessert", is_vegan=True),
    "citrus": dict(unit="kg", category="citrus", demand_group="condiment", is_vegan=True),
    "herb": dict(unit="kg", category="herb", demand_group="condiment", is_vegan=True),
    "meat_beef": dict(unit="kg", category="meat", demand_group="main", is_meat=True,
                       is_vegetarian=False, is_vegan=False, tags=["beef"]),
    "meat_pork": dict(unit="kg", category="meat", demand_group="main", is_meat=True,
                       is_vegetarian=False, is_vegan=False, tags=["pork"]),
    "meat_lamb": dict(unit="kg", category="meat", demand_group="main", is_meat=True,
                       is_vegetarian=False, is_vegan=False, tags=["lamb"]),
    "poultry": dict(unit="kg", category="poultry", demand_group="main", is_meat=True,
                     is_vegetarian=False, is_vegan=False, tags=["poultry"]),
    "fish": dict(unit="kg", category="fish", demand_group="main", is_fish=True,
                 is_vegetarian=False, is_vegan=False, tags=["fish"]),
    "veg_protein": dict(unit="kg", category="veg_protein", demand_group="main",
                         is_vegetarian=True, is_vegan=False, lactose_free=False),
    "vegan_protein": dict(unit="kg", category="vegan_protein", demand_group="main",
                           is_vegetarian=True, is_vegan=True),
    "bread": dict(unit="pcs", category="bread", demand_group="side", gluten_free=False),
    "potato": dict(unit="kg", category="potato", demand_group="side", is_vegan=True),
    "pasta": dict(unit="kg", category="pasta", demand_group="side", gluten_free=False, is_vegan=True),
    "grain": dict(unit="kg", category="grain", demand_group="side", is_vegan=True),
    "salad_green": dict(unit="kg", category="salad", demand_group="salad", is_vegan=True),
    "vegetable": dict(unit="kg", category="vegetable", demand_group="side", is_vegan=True),
    "cheese": dict(unit="kg", category="cheese", demand_group="condiment", is_vegan=False, lactose_free=False),
    "sauce": dict(unit="l", category="sauce", demand_group="condiment", is_vegan=True),
    "spice": dict(unit="kg", category="spice", demand_group="condiment", is_vegan=True),
    "snack": dict(unit="kg", category="snack", demand_group="snack", is_vegan=True),
    "dessert_ing": dict(unit="kg", category="dessert", demand_group="dessert", is_vegan=False),
    "ice": dict(unit="kg", category="ice", demand_group="condiment", is_vegan=True),
    "water": dict(unit="l", category="water", demand_group="beverage_general", is_vegan=True),
}


def mk_ingredient(item_id: str, name: str, family: str, **overrides) -> dict:
    base = dict(FAMILY_DEFAULTS[family])
    base.update(overrides)
    return dict(
        id=item_id,
        name=name,
        category=base.get("category", family),
        demand_group=base.get("demand_group", "misc"),
        tags=base.get("tags", []),
        popular=base.get("popular", False),
        aliases_hint=base.get("aliases_hint", []),
        unit=base.get("unit", "l"),
        family=family,
        purchasable=base.get("purchasable", True),
        is_meat=base.get("is_meat", False),
        is_fish=base.get("is_fish", False),
        is_vegetarian=base.get("is_vegetarian", True),
        is_vegan=base.get("is_vegan", False),
        contains_alcohol=base.get("contains_alcohol", False),
        abv=base.get("abv", 0.0),
        contains_caffeine=base.get("contains_caffeine", False),
        allergens=base.get("allergens", []),
        gluten_free=base.get("gluten_free", True),
        lactose_free=base.get("lactose_free", True),
    )


# --- INGREDIENTS ---------------------------------------------------------------
# Format: (id, name, family, overrides-dict-or-{})

INGREDIENTS_RAW: list[tuple] = [
    # Spirituosen
    ("vodka", "Vodka", "spirit", {}),
    ("vodka_vanilla", "Vanilla Vodka", "spirit", {}),
    ("gin", "Gin", "spirit", {}),
    ("gin_london_dry", "London Dry Gin", "spirit", {}),
    ("gin_pink", "Pink Gin", "spirit", {}),
    ("rum_white", "White Rum", "spirit", {}),
    ("rum_dark", "Dark Rum", "spirit", {}),
    ("rum_aged", "Aged Rum", "spirit", {}),
    ("rum_spiced", "Spiced Rum", "spirit", {}),
    ("rum_overproof", "Overproof Rum", "spirit", {"abv": 60.0}),
    ("bourbon", "Bourbon", "spirit", {}),
    ("rye_whiskey", "Rye Whiskey", "spirit", {}),
    ("scotch_whisky", "Scotch Whisky", "spirit", {}),
    ("irish_whiskey", "Irish Whiskey", "spirit", {}),
    ("tennessee_whiskey", "Tennessee Whiskey", "spirit", {}),
    ("canadian_whisky", "Canadian Whisky", "spirit", {}),
    ("tequila_blanco", "Tequila Blanco", "spirit", {}),
    ("tequila_reposado", "Tequila Reposado", "spirit", {}),
    ("tequila_anejo", "Tequila Añejo", "spirit", {}),
    ("mezcal", "Mezcal", "spirit", {}),
    ("cachaca", "Cachaça", "spirit", {}),
    ("pisco", "Pisco", "spirit", {}),
    ("cognac", "Cognac", "spirit", {}),
    ("brandy", "Brandy", "spirit", {}),
    ("calvados", "Calvados", "spirit", {}),
    ("grappa", "Grappa", "spirit", {}),
    ("korn", "Korn", "spirit", {"abv": 32.0}),
    ("doppelkorn", "Doppelkorn", "spirit", {"abv": 38.0}),
    ("obstler", "Obstler", "spirit", {}),
    ("williams_birne", "Williamsbirne", "spirit", {}),
    ("kirschwasser", "Kirschwasser", "spirit", {}),
    ("sambuca", "Sambuca", "liqueur", {"abv": 38.0}),
    ("ouzo", "Ouzo", "spirit", {"abv": 38.0}),
    ("raki", "Raki", "spirit", {"abv": 45.0}),
    ("aquavit", "Aquavit", "spirit", {}),
    # Liköre / Bitterliköre / Fortified Wine
    ("jaegermeister", "Jägermeister / Kräuterlikör", "liqueur", {"abv": 35.0}),
    ("baileys", "Baileys / Irish Cream", "liqueur", {"abv": 17.0, "lactose_free": False, "is_vegan": False}),
    ("amaretto", "Amaretto", "liqueur", {"abv": 24.0}),
    ("limoncello", "Limoncello", "liqueur", {"abv": 30.0}),
    ("aperol", "Aperol", "liqueur", {"abv": 11.0}),
    ("campari", "Campari", "liqueur", {"abv": 25.0}),
    ("cynar", "Cynar", "liqueur", {"abv": 16.5}),
    ("fernet", "Fernet", "liqueur", {"abv": 39.0}),
    ("ramazzotti", "Ramazzotti", "liqueur", {"abv": 30.0}),
    ("averna", "Averna", "liqueur", {"abv": 29.0}),
    ("amaro_generic", "Amaro", "liqueur", {"abv": 28.0}),
    ("coffee_liqueur", "Kaffeelikör", "liqueur", {"abv": 20.0}),
    ("triple_sec", "Triple Sec", "liqueur", {"abv": 30.0}),
    ("grand_marnier", "Grand Marnier", "liqueur", {"abv": 40.0}),
    ("peach_liqueur", "Pfirsichlikör", "liqueur", {"abv": 18.0}),
    ("maraschino", "Maraschino", "liqueur", {"abv": 32.0}),
    ("blackberry_liqueur", "Brombeerlikör", "liqueur", {"abv": 18.0}),
    ("raspberry_liqueur", "Himbeerlikör", "liqueur", {"abv": 18.0}),
    ("passionfruit_liqueur", "Passionsfruchtlikör", "liqueur", {"abv": 18.0}),
    ("elderflower_liqueur", "Holunderblütenlikör", "liqueur", {"abv": 20.0}),
    ("creme_de_cassis", "Crème de Cassis", "liqueur", {"abv": 18.0}),
    ("blue_curacao", "Blue Curaçao", "liqueur", {"abv": 20.0}),
    ("malibu", "Malibu / Coconut Rum", "liqueur", {"abv": 21.0}),
    ("dry_vermouth", "Dry Vermouth", "fortified_wine", {}),
    ("sweet_vermouth", "Sweet Vermouth", "fortified_wine", {}),
    ("lillet_blanc", "Lillet Blanc", "fortified_wine", {}),
    ("sherry", "Sherry", "fortified_wine", {}),
    ("port_wine", "Portwein", "fortified_wine", {"abv": 20.0}),
    ("chartreuse_green", "Chartreuse Green", "liqueur", {"abv": 55.0}),
    ("chartreuse_yellow", "Chartreuse Yellow", "liqueur", {"abv": 40.0}),
    # Wein
    ("red_wine", "Rotwein", "wine", {"popular": True}),
    ("white_wine", "Weißwein", "wine", {"popular": True}),
    ("rose_wine", "Rosé", "wine", {}),
    ("grauburgunder", "Grauburgunder", "wine", {}),
    ("weissburgunder", "Weißburgunder", "wine", {}),
    ("riesling", "Riesling", "wine", {}),
    ("chardonnay", "Chardonnay", "wine", {}),
    ("sauvignon_blanc", "Sauvignon Blanc", "wine", {}),
    ("silvaner", "Silvaner", "wine", {}),
    ("mueller_thurgau", "Müller-Thurgau", "wine", {}),
    ("gruener_veltliner", "Grüner Veltliner", "wine", {}),
    ("gewuerztraminer", "Gewürztraminer", "wine", {}),
    ("primitivo", "Primitivo", "wine", {}),
    ("merlot", "Merlot", "wine", {}),
    ("cabernet_sauvignon", "Cabernet Sauvignon", "wine", {}),
    ("pinot_noir", "Pinot Noir", "wine", {}),
    ("spaetburgunder", "Spätburgunder", "wine", {}),
    ("tempranillo", "Tempranillo", "wine", {}),
    ("syrah", "Syrah", "wine", {}),
    ("shiraz", "Shiraz", "wine", {}),
    ("rioja", "Rioja", "wine", {}),
    ("chianti", "Chianti", "wine", {}),
    ("lambrusco", "Lambrusco", "wine", {"abv": 8.0}),
    ("wine_alcohol_free", "alkoholfreier Wein", "wine",
     {"contains_alcohol": False, "abv": 0.0, "demand_group": "non_alcoholic_beverage"}),
    # Schaumwein
    ("prosecco", "Prosecco", "sparkling_wine", {"popular": True}),
    ("sekt", "Sekt", "sparkling_wine", {}),
    ("champagne", "Champagner", "sparkling_wine", {"abv": 12.0}),
    ("cremant", "Crémant", "sparkling_wine", {}),
    ("cava", "Cava", "sparkling_wine", {}),
    ("franciacorta", "Franciacorta", "sparkling_wine", {}),
    ("sparkling_wine_alcohol_free", "alkoholfreier Sekt", "sparkling_wine",
     {"contains_alcohol": False, "abv": 0.0, "demand_group": "non_alcoholic_beverage"}),
    # Bier
    ("beer_pils", "Pils", "beer", {"popular": True}),
    ("beer_helles", "Helles", "beer", {}),
    ("beer_export", "Export", "beer", {}),
    ("beer_kellerbier", "Kellerbier", "beer", {}),
    ("beer_zwickel", "Zwickel", "beer", {}),
    ("beer_hefeweizen", "Hefeweizen", "beer", {}),
    ("beer_kristallweizen", "Kristallweizen", "beer", {}),
    ("beer_dunkelweizen", "Dunkelweizen", "beer", {}),
    ("beer_dunkel", "Dunkelbier", "beer", {}),
    ("beer_schwarzbier", "Schwarzbier", "beer", {}),
    ("beer_bockbier", "Bockbier", "beer", {"abv": 6.5}),
    ("beer_doppelbock", "Doppelbock", "beer", {"abv": 7.5}),
    ("beer_maerzen", "Märzen", "beer", {}),
    ("beer_festbier", "Festbier", "beer", {}),
    ("beer_koelsch", "Kölsch", "beer", {}),
    ("beer_altbier", "Altbier", "beer", {}),
    ("beer_lager", "Lager", "beer", {}),
    ("beer_pale_ale", "Pale Ale", "beer", {}),
    ("beer_ipa", "IPA", "beer", {"abv": 6.0}),
    ("beer_double_ipa", "Double IPA", "beer", {"abv": 8.0}),
    ("beer_session_ipa", "Session IPA", "beer", {"abv": 4.0}),
    ("beer_stout", "Stout", "beer", {"abv": 6.0}),
    ("beer_porter", "Porter", "beer", {"abv": 6.0}),
    ("beer_sour", "Sour Beer", "beer", {"abv": 5.0}),
    ("beer_craft_generic", "Craft Beer", "beer", {}),
    ("beer_pils_alcohol_free", "alkoholfreies Pils", "beer",
     {"contains_alcohol": False, "abv": 0.0, "demand_group": "non_alcoholic_beverage"}),
    ("beer_helles_alcohol_free", "alkoholfreies Helles", "beer",
     {"contains_alcohol": False, "abv": 0.0, "demand_group": "non_alcoholic_beverage"}),
    ("beer_weizen_alcohol_free", "alkoholfreies Weizen", "beer",
     {"contains_alcohol": False, "abv": 0.0, "demand_group": "non_alcoholic_beverage"}),
    # Softdrinks
    ("cola", "Cola", "softdrink", {"contains_caffeine": True, "popular": True}),
    ("cola_zero", "Cola Zero", "softdrink", {"contains_caffeine": True, "popular": True}),
    ("cola_light", "Cola Light", "softdrink", {"contains_caffeine": True}),
    ("fanta_orange", "Fanta Orange", "softdrink", {}),
    ("fanta_lemon", "Fanta Lemon", "softdrink", {}),
    ("sprite", "Sprite", "softdrink", {}),
    ("seven_up", "7Up", "softdrink", {}),
    ("lemonade_orange", "Orangenlimonade", "softdrink", {}),
    ("lemonade_lemon", "Zitronenlimonade", "softdrink", {}),
    ("tonic_water", "Tonic Water", "softdrink", {}),
    ("bitter_lemon", "Bitter Lemon", "softdrink", {}),
    ("ginger_ale", "Ginger Ale", "softdrink", {}),
    ("ginger_beer", "Ginger Beer", "softdrink", {}),
    ("wild_berry_soda", "Wild Berry", "softdrink", {}),
    ("grapefruit_soda", "Pink Grapefruit-Limonade", "softdrink", {}),
    ("club_mate", "Club Mate", "softdrink", {"contains_caffeine": True}),
    ("mate_lemonade", "Mate-Limonade", "softdrink", {"contains_caffeine": True}),
    ("fassbrause", "Fassbrause", "softdrink", {}),
    ("malt_beer", "Malzbier", "softdrink", {}),
    ("root_beer", "Root Beer", "softdrink", {}),
    ("cream_soda", "Cream Soda", "softdrink", {}),
    ("soda_water", "Soda Water", "softdrink", {}),
    ("mineral_water_still", "Mineralwasser still", "water", {"popular": True}),
    ("mineral_water_medium", "Mineralwasser medium", "water", {}),
    ("mineral_water_sparkling", "Mineralwasser sprudel", "water", {}),
    ("water", "Wasser", "water", {"popular": True}),
    # Energy / Koffein
    ("energy_drink_generic", "Energy Drink", "energy", {"popular": True}),
    ("energy_drink_sugarfree", "Energy Drink Zero", "energy", {}),
    ("energy_drink_tropical", "Energy Drink Edition", "energy", {}),
    # Kaffee
    ("coffee_beans", "Kaffeebohnen", "coffee", {"purchasable": True}),
    ("espresso", "Espresso", "coffee", {"purchasable": False}),
    # Säfte
    ("orange_juice", "Orangensaft", "juice", {}),
    ("apple_juice", "Apfelsaft", "juice", {}),
    ("pineapple_juice", "Ananassaft", "juice", {}),
    ("cranberry_juice", "Cranberrysaft", "juice", {}),
    ("cherry_juice", "Kirschsaft", "juice", {}),
    ("banana_juice", "Bananensaft", "juice", {}),
    ("passionfruit_juice", "Passionsfruchtsaft / Maracujasaft", "juice", {}),
    ("mango_juice", "Mangosaft", "juice", {}),
    ("peach_juice", "Pfirsichsaft", "juice", {}),
    ("grapefruit_juice", "Grapefruitsaft", "juice", {}),
    ("tomato_juice", "Tomatensaft", "juice", {}),
    ("grape_juice", "Traubensaft", "juice", {}),
    ("currant_juice", "Johannisbeersaft", "juice", {}),
    ("multivitamin_juice", "Multivitaminsaft", "juice", {}),
    ("rhubarb_juice", "Rhabarbersaft", "juice", {}),
    ("lime_juice_fresh", "Limettensaft (frisch)", "juice", {"purchasable": False}),
    ("lemon_juice_fresh", "Zitronensaft (frisch)", "juice", {"purchasable": False}),
    # Sirupe
    ("simple_syrup", "Zuckersirup", "syrup", {"purchasable": False}),
    ("grenadine", "Grenadine", "syrup", {}),
    ("lime_cordial", "Lime Cordial", "syrup", {}),
    ("elderflower_syrup", "Holunderblütensirup", "syrup", {}),
    ("passionfruit_syrup", "Passionsfruchtsirup", "syrup", {}),
    ("raspberry_syrup", "Himbeersirup", "syrup", {}),
    ("vanilla_syrup", "Vanillesirup", "syrup", {}),
    ("agave_syrup", "Agavendicksaft", "syrup", {}),
    ("orgeat_syrup", "Orgeat-Sirup (Mandel)", "syrup", {"allergens": ["nuts"]}),
    ("cane_sugar_syrup", "Rohrzuckersirup", "syrup", {}),
    # Milchprodukte
    ("milk", "Milch", "dairy", {}),
    ("cream", "Sahne", "dairy", {}),
    ("yogurt", "Joghurt", "dairy", {}),
    ("sour_cream", "Sour Cream / Schmand", "dairy", {}),
    ("butter", "Butter", "dairy", {}),
    ("mascarpone", "Mascarpone", "dairy", {}),
    ("cream_cheese", "Frischkäse", "dairy", {}),
    # Obst
    ("apple", "Apfel", "fruit", {}),
    ("banana", "Banane", "fruit", {}),
    ("strawberry", "Erdbeere", "fruit", {}),
    ("blueberry", "Blaubeere", "fruit", {}),
    ("raspberry", "Himbeere", "fruit", {}),
    ("blackberry", "Brombeere", "fruit", {}),
    ("pineapple", "Ananas", "fruit", {}),
    ("watermelon", "Wassermelone", "fruit", {}),
    ("grape", "Traube", "fruit", {}),
    ("peach", "Pfirsich", "fruit", {}),
    ("mango", "Mango", "fruit", {}),
    ("passionfruit", "Maracuja", "fruit", {}),
    ("cherry", "Kirsche", "fruit", {}),
    ("pomegranate", "Granatapfel", "fruit", {}),
    ("mixed_berries", "Beerenmix", "fruit", {}),
    # Zitrusfrüchte
    ("lime", "Limette", "citrus", {}),
    ("lemon", "Zitrone", "citrus", {}),
    ("orange", "Orange", "citrus", {}),
    ("grapefruit", "Grapefruit", "citrus", {}),
    # Kräuter
    ("mint", "Minze", "herb", {}),
    ("basil", "Basilikum", "herb", {}),
    ("rosemary", "Rosmarin", "herb", {}),
    ("thyme", "Thymian", "herb", {}),
    ("parsley", "Petersilie", "herb", {}),
    ("dill", "Dill", "herb", {}),
    ("chives", "Schnittlauch", "herb", {}),
    ("cilantro", "Koriander", "herb", {}),
    ("ginger", "Ingwer", "herb", {}),
    # Fleisch (Rind)
    ("beef_patty", "Beef Patty", "meat_beef", {}),
    ("beef_steak_ribeye", "Ribeye", "meat_beef", {}),
    ("beef_steak_rump", "Rumpsteak", "meat_beef", {}),
    ("beef_entrecote", "Entrecôte", "meat_beef", {}),
    ("ground_beef", "Hackfleisch (Rind)", "meat_beef", {}),
    ("beef_sausage", "Rindswurst", "meat_beef", {}),
    # Fleisch (Schwein)
    ("pork_sausage_bratwurst", "Bratwurst", "meat_pork", {}),
    ("pork_sausage_nuernberger", "Nürnberger", "meat_pork", {}),
    ("pork_sausage_thueringer", "Thüringer", "meat_pork", {}),
    ("pork_sausage_krakauer", "Krakauer", "meat_pork", {}),
    ("pork_sausage_currywurst", "Currywurst-Wurst", "meat_pork", {}),
    ("pork_neck_steak", "Schweinenacken / Nackensteak", "meat_pork", {}),
    ("pork_belly", "Schweinebauch", "meat_pork", {}),
    ("pork_chop", "Schweinekotelett", "meat_pork", {}),
    ("pork_ribs", "Spareribs", "meat_pork", {}),
    ("ground_pork", "Hackfleisch (Schwein)", "meat_pork", {}),
    ("bacon", "Bacon", "meat_pork", {}),
    ("ham", "Schinken", "meat_pork", {}),
    # Fleisch (Lamm)
    ("lamb_chop", "Lammkotelett", "meat_lamb", {}),
    ("lamb_skewer_meat", "Lammfleisch (Spieß)", "meat_lamb", {}),
    # Geflügel
    ("chicken_breast", "Hähnchenbrust", "poultry", {}),
    ("chicken_thigh", "Hähnchenschenkel", "poultry", {}),
    ("chicken_wing", "Chicken Wing", "poultry", {}),
    ("chicken_drumstick", "Chicken Drumstick", "poultry", {}),
    ("ground_chicken", "Hackfleisch (Hähnchen)", "poultry", {}),
    ("turkey_breast", "Putenbrust", "poultry", {}),
    # Fisch
    ("salmon_fillet", "Lachsfilet", "fish", {}),
    ("shrimp", "Garnele", "fish", {"allergens": ["shellfish"]}),
    ("dorade", "Dorade", "fish", {}),
    ("trout", "Forelle", "fish", {}),
    ("tuna_steak", "Thunfischsteak", "fish", {}),
    ("cod", "Kabeljau", "fish", {}),
    # Vegetarische Proteine
    ("halloumi", "Halloumi / Grillkäse", "veg_protein", {}),
    ("feta", "Feta", "veg_protein", {}),
    # Vegane Proteine
    ("tofu", "Tofu", "vegan_protein", {"is_vegan": True}),
    ("tofu_marinated", "Marinierter Tofu", "vegan_protein", {"is_vegan": True}),
    ("tempeh", "Tempeh", "vegan_protein", {"is_vegan": True}),
    ("seitan", "Seitan", "vegan_protein", {"is_vegan": True, "gluten_free": False}),
    ("vegan_sausage", "Vegane Bratwurst", "vegan_protein", {"is_vegan": True}),
    ("vegan_burger_patty", "Veganes Patty", "vegan_protein", {"is_vegan": True}),
    ("vegetarian_sausage", "Vegetarische Bratwurst", "veg_protein", {}),
    ("vegetarian_burger_patty", "Vegetarisches Patty", "veg_protein", {}),
    ("jackfruit", "Jackfruit", "vegan_protein", {"is_vegan": True}),
    # Brot / Backwaren
    ("burger_bun", "Burger Bun", "bread", {}),
    ("hotdog_bun", "Hotdog Bun", "bread", {}),
    ("baguette", "Baguette", "bread", {}),
    ("ciabatta", "Ciabatta", "bread", {}),
    ("flatbread", "Fladenbrot", "bread", {}),
    ("bread_roll", "Brötchen", "bread", {}),
    ("pretzel", "Brezel", "bread", {}),
    ("laugenstange", "Laugenstange", "bread", {}),
    ("white_bread", "Weißbrot", "bread", {}),
    ("toast_bread", "Toastbrot", "bread", {}),
    ("tortilla_wrap", "Tortilla Wrap", "bread", {}),
    # Kartoffeln
    ("potato", "Kartoffel", "potato", {}),
    ("sweet_potato", "Süßkartoffel", "potato", {}),
    # Nudeln
    ("pasta_penne", "Penne", "pasta", {}),
    ("pasta_spaghetti", "Spaghetti", "pasta", {}),
    ("tortellini", "Tortellini", "pasta", {"is_vegan": False}),
    ("macaroni", "Makkaroni", "pasta", {}),
    # Reis / Getreide
    ("rice", "Reis", "grain", {}),
    ("basmati_rice", "Basmati-Reis", "grain", {}),
    ("couscous", "Couscous", "grain", {"gluten_free": False}),
    ("bulgur", "Bulgur", "grain", {"gluten_free": False}),
    ("quinoa", "Quinoa", "grain", {}),
    # Salat
    ("lettuce", "Kopfsalat", "salad_green", {}),
    ("arugula", "Rucola", "salad_green", {}),
    ("romaine_lettuce", "Römersalat", "salad_green", {}),
    ("mixed_greens", "Blattsalatmischung", "salad_green", {}),
    # Gemüse
    ("tomato", "Tomate", "vegetable", {}),
    ("cucumber", "Gurke", "vegetable", {}),
    ("onion", "Zwiebel", "vegetable", {}),
    ("red_onion", "Rote Zwiebel", "vegetable", {}),
    ("bell_pepper", "Paprika", "vegetable", {}),
    ("corn", "Mais / Maiskolben", "vegetable", {}),
    ("zucchini", "Zucchini", "vegetable", {}),
    ("eggplant", "Aubergine", "vegetable", {}),
    ("mushroom", "Champignon", "vegetable", {}),
    ("avocado", "Avocado", "vegetable", {}),
    ("carrot", "Karotte", "vegetable", {}),
    ("cabbage", "Kohl / Kraut", "vegetable", {}),
    ("kidney_beans", "Kidneybohnen", "vegetable", {}),
    ("chickpeas", "Kichererbsen", "vegetable", {}),
    ("lentils", "Linsen", "vegetable", {}),
    ("garlic", "Knoblauch", "vegetable", {}),
    ("jalapeno", "Jalapeño", "vegetable", {}),
    ("olives", "Oliven", "vegetable", {}),
    # Käse
    ("cheddar", "Cheddar", "cheese", {}),
    ("mozzarella", "Mozzarella", "cheese", {}),
    ("parmesan", "Parmesan", "cheese", {}),
    ("gouda", "Gouda", "cheese", {}),
    ("blue_cheese", "Blauschimmelkäse", "cheese", {}),
    ("cheese_slices_generic", "Käsescheiben (generisch)", "cheese", {}),
    # Saucen / Dips
    ("ketchup", "Ketchup", "sauce", {}),
    ("mayonnaise", "Mayonnaise", "sauce", {"is_vegan": False}),
    ("mustard", "Senf", "sauce", {}),
    ("sweet_mustard", "Süßer Senf", "sauce", {}),
    ("bbq_sauce", "BBQ Sauce", "sauce", {}),
    ("burger_sauce", "Burger Sauce", "sauce", {"is_vegan": False}),
    ("cocktail_sauce", "Cocktailsauce", "sauce", {"is_vegan": False}),
    ("curry_sauce", "Currysauce", "sauce", {}),
    ("aioli", "Aioli", "sauce", {"is_vegan": False}),
    ("garlic_dip", "Knoblauchdip", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("herb_dip", "Kräuterdip", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("tzatziki", "Tzatziki", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("hummus", "Hummus", "sauce", {"is_vegan": True}),
    ("salsa_mild", "Salsa mild", "sauce", {"is_vegan": True}),
    ("salsa_hot", "Salsa scharf", "sauce", {"is_vegan": True}),
    ("guacamole", "Guacamole", "sauce", {"is_vegan": True}),
    ("sweet_chili_sauce", "Sweet Chili Sauce", "sauce", {"is_vegan": True}),
    ("sriracha", "Sriracha", "sauce", {"is_vegan": True}),
    ("hot_sauce", "Hot Sauce", "sauce", {"is_vegan": True}),
    ("tabasco", "Tabasco", "sauce", {"is_vegan": True}),
    ("remoulade", "Remoulade", "sauce", {"is_vegan": False}),
    ("honey_mustard_sauce", "Honig-Senf-Sauce", "sauce", {"is_vegan": False}),
    ("teriyaki_sauce", "Teriyaki Sauce", "sauce", {"is_vegan": True}),
    ("cheese_sauce", "Käsesauce", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("chili_cheese_sauce", "Chili Cheese Sauce", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("herb_butter", "Kräuterbutter", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("garlic_butter", "Knoblauchbutter", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("tomato_sauce", "Tomatensauce", "sauce", {"is_vegan": True}),
    ("pesto", "Pesto", "sauce", {"is_vegan": False, "lactose_free": False}),
    # Gewürze
    ("salt", "Salz", "spice", {}),
    ("pepper", "Pfeffer", "spice", {}),
    ("paprika_powder", "Paprikapulver", "spice", {}),
    ("cumin", "Kreuzkümmel", "spice", {}),
    ("oregano", "Oregano", "spice", {}),
    ("chili_flakes", "Chiliflocken", "spice", {}),
    ("cinnamon", "Zimt", "spice", {}),
    ("sugar", "Zucker", "spice", {}),
    ("vanilla_sugar", "Vanillezucker", "spice", {}),
    # Snacks
    ("potato_chips", "Kartoffelchips", "snack", {"popular": True}),
    ("paprika_chips", "Paprikachips", "snack", {}),
    ("salt_vinegar_chips", "Salt & Vinegar Chips", "snack", {}),
    ("tortilla_chips", "Tortilla Chips", "snack", {"popular": True}),
    ("pretzel_sticks", "Salzstangen", "snack", {}),
    ("crackers", "Cracker", "snack", {"gluten_free": False}),
    ("cheese_crackers", "Käsecracker", "snack", {"gluten_free": False, "is_vegan": False}),
    ("peanuts", "Erdnüsse", "snack", {"allergens": ["peanuts"]}),
    ("cashews", "Cashews", "snack", {"allergens": ["nuts"]}),
    ("almonds", "Mandeln", "snack", {"allergens": ["nuts"]}),
    ("nut_mix", "Nussmix", "snack", {"allergens": ["nuts"]}),
    ("popcorn_salty", "Popcorn salzig", "snack", {}),
    ("popcorn_sweet", "Popcorn süß", "snack", {}),
    ("rice_cakes", "Reiswaffeln", "snack", {}),
    ("grissini", "Grissini", "snack", {"gluten_free": False}),
    ("mini_salami", "Mini-Salami", "snack", {"is_vegan": False}),
    ("beef_jerky", "Beef Jerky", "snack", {"is_vegan": False}),
    ("snack_sausages", "Snackwürstchen", "snack", {"is_vegan": False}),
    ("grapes_snack", "Trauben (Snack)", "snack", {}),
    # Dessert-Zutaten
    ("flour", "Mehl", "dessert_ing", {"gluten_free": False, "is_vegan": True}),
    ("eggs", "Eier", "dessert_ing", {"is_vegan": False}),
    ("cocoa_powder", "Kakaopulver", "dessert_ing", {"is_vegan": True}),
    ("vanilla_ice_cream", "Vanilleeis", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    ("chocolate_ice_cream", "Schokoladeneis", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    ("strawberry_ice_cream", "Erdbeereis", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    ("sorbet", "Sorbet", "dessert_ing", {"is_vegan": True}),
    ("pudding_vanilla", "Vanillepudding", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    ("pudding_chocolate", "Schokopudding", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    ("gelatin", "Gelatine", "dessert_ing", {"is_vegan": False}),
    ("biscuit_base", "Kekse / Löffelbiskuit", "dessert_ing", {"gluten_free": False, "is_vegan": False}),
    ("chocolate", "Schokolade", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    # Eis
    ("ice_cubes", "Eiswürfel", "ice", {}),
    ("crushed_ice", "Crushed Ice", "ice", {}),
]

# --- Zusätzliche Ingredient-Familien für Bar-/Rezeptzutaten --------------------

FAMILY_DEFAULTS.update({
    "bitters": dict(unit="l", category="bitters", demand_group="condiment",
                     contains_alcohol=True, abv=40.0, is_vegan=True),
    "bar_misc": dict(unit="l", category="bar_misc", demand_group="condiment", is_vegan=True),
    "plant_milk": dict(unit="l", category="plant_milk", demand_group="condiment", is_vegan=True),
})

# --- Zusätzliche Ingredients, die für konkrete Rezept-BOMs benötigt werden -----
# (nur ergänzt, wenn kein passendes Ingredient in INGREDIENTS_RAW existierte)

EXTRA_INGREDIENTS_RAW: list[tuple] = [
    # Bitters
    ("angostura_bitters", "Angostura Bitters", "bitters", {}),
    ("peychauds_bitters", "Peychaud's Bitters", "bitters", {}),
    ("orange_bitters", "Orange Bitters", "bitters", {}),
    # Spirituose
    ("absinthe", "Absinth", "spirit", {"abv": 68.0}),
    # Bar-Sonstiges
    ("egg_white", "Eiweiß", "bar_misc", {"unit": "pcs", "is_vegan": False, "allergens": ["egg"]}),
    ("coconut_cream", "Kokoscreme", "plant_milk", {}),
    ("coconut_milk", "Kokosmilch", "plant_milk", {}),
    # Liköre
    ("drambuie", "Drambuie", "liqueur", {"abv": 40.0}),
    ("creme_de_cacao", "Crème de Cacao", "liqueur", {"abv": 24.0}),
    ("melon_liqueur", "Melonenlikör (Midori-Stil)", "liqueur", {"abv": 20.0}),
    ("cherry_liqueur", "Kirschlikör (Cherry Brandy)", "liqueur", {"abv": 24.0}),
    ("falernum", "Falernum", "liqueur", {"abv": 11.0}),
    # Sirupe
    ("honey_syrup", "Honigsirup", "syrup", {}),
    ("ginger_syrup", "Ingwersirup", "syrup", {}),
    ("cinnamon_syrup", "Zimtsirup", "syrup", {}),
    # Saucen
    ("worcestershire_sauce", "Worcestersauce", "sauce", {}),
    ("peanut_sauce", "Erdnusssauce", "sauce", {}),
    # Gewürze
    ("celery_salt", "Selleriesalz", "spice", {}),
    # Fleisch
    ("pork_shoulder", "Schweineschulter (Pulled Pork)", "meat_pork", {}),
    ("salami", "Salami", "meat_pork", {}),
    ("beef_stew_meat", "Rindfleisch (Gulasch/Schmorfleisch)", "meat_beef", {}),
    # Brot/Teig
    ("pizza_dough", "Pizzateig", "bread", {}),
    ("taco_shell", "Taco Shell", "bread", {}),
    ("spring_roll_wrapper", "Frühlingsrollenteig", "bread", {}),
    ("puff_pastry", "Blätterteig", "bread", {}),
    ("croutons", "Croutons", "bread", {}),
    # Nudeln
    ("lasagne_sheets", "Lasagneplatten", "pasta", {}),
    # Vegan
    ("vegan_cheese", "Veganer Käse", "vegan_protein", {"is_vegan": True}),
    # Gemüse/Obst
    ("green_beans", "Grüne Bohnen", "vegetable", {}),
    ("dates", "Datteln", "fruit", {}),
    # Dessert
    ("ice_pop", "Eis am Stiel", "dessert_ing", {"is_vegan": False, "lactose_free": False}),
    ("frosting", "Frosting / Zuckerguss", "dessert_ing", {"is_vegan": False}),
]

INGREDIENTS_RAW.extend(EXTRA_INGREDIENTS_RAW)

# Kaffee-Zwischenprodukte (für Kaffee-Direktkonsum bzw. Kaffee-Rezepte)
INGREDIENTS_RAW.extend([
    ("filter_coffee", "Filterkaffee", "coffee", {"purchasable": False}),
    ("cold_brew", "Cold Brew Kaffee", "coffee", {}),
    ("licor_43", "Licor 43", "liqueur", {"abv": 31.0}),
])


# --- GEO-KULTUR-INGREDIENTS (Geo-/Kultur-Kontext-Spec §4/§6) --------------------
# Neue Zutaten für authentische, länderspezifische Rezepte (Indien, Peru,
# Dänemark, Japan, USA), die von party_context/culture.py bereits als
# Tag-Re-Weighting-Ziele referenziert werden (siehe dortiger Modul-Docstring).
# "sake" ist eine neue Ingredient-Familie (kein bestehendes Family-Pattern
# passt: kein Spirituose/Wein im engeren Sinne, eigene ABV/Reifecharakteristik).

FAMILY_DEFAULTS.update({
    "sake": dict(unit="l", category="sake", demand_group="alcoholic_beverage",
                 contains_alcohol=True, abv=15.0, is_vegan=True),
})

GEO_CULTURE_INGREDIENTS_RAW: list[tuple] = [
    # --- Indien -------------------------------------------------------------
    ("paneer", "Paneer", "veg_protein", {}),
    ("naan_bread", "Naan-Brot", "bread", {}),
    ("cardamom", "Kardamom", "spice", {}),
    ("chickpea_flour", "Kichererbsenmehl", "spice", {}),
    ("cauliflower", "Blumenkohl", "vegetable", {}),
    ("black_tea", "Schwarzer Tee", "spice", {"contains_caffeine": True}),
    ("spinach", "Spinat", "vegetable", {}),
    # --- Peru -----------------------------------------------------------------
    ("aji_amarillo", "Aji Amarillo Paste", "sauce", {}),
    ("queso_fresco", "Queso Fresco", "cheese", {}),
    ("purple_corn", "Lila Mais", "vegetable", {}),
    ("vinegar", "Essig", "sauce", {}),
    ("inca_kola", "Inca Kola", "softdrink", {}),
    # --- Dänemark -------------------------------------------------------------
    ("rye_bread", "Roggenbrot (Rugbrød)", "bread", {}),
    ("liver_pate", "Leberpastete", "meat_pork", {}),
    ("red_cabbage", "Rotkohl", "vegetable", {}),
    ("herring", "Hering", "fish", {"allergens": ["fish"]}),
    ("raisins", "Rosinen", "fruit", {}),
    ("beer_dk_pilsner", "Dänisches Pilsner", "beer", {"abv": 4.6}),
    ("cherry_wine", "Kirschwein", "wine", {}),
    # --- Japan ------------------------------------------------------------------
    ("mirin", "Mirin", "sauce", {}),
    ("soy_sauce", "Sojasauce", "sauce", {}),
    ("nori", "Nori (Algenblätter)", "spice", {}),
    ("edamame", "Edamame", "vegetable", {}),
    ("miso_paste", "Miso-Paste", "sauce", {}),
    ("scallion", "Frühlingszwiebel", "vegetable", {}),
    ("okonomiyaki_sauce", "Okonomiyaki-Sauce", "sauce", {}),
    ("matcha", "Matcha-Pulver", "spice", {"contains_caffeine": True}),
    ("sake", "Sake", "sake", {}),
    ("umeshu", "Umeshu (Pflaumenwein)", "liqueur", {"abv": 10.0}),
    ("ramune", "Ramune", "softdrink", {}),
    ("green_tea_bottled", "Grüner Tee (Flasche)", "softdrink", {"contains_caffeine": True}),
    # --- USA --------------------------------------------------------------------
    ("cornmeal", "Maismehl", "grain", {}),
    ("beef_brisket", "Beef Brisket", "meat_beef", {}),
    ("clams", "Venusmuscheln", "fish", {"allergens": ["shellfish"]}),
    ("celery", "Staudensellerie", "vegetable", {}),
    ("pecans", "Pekannüsse", "snack", {}),
    ("graham_crackers", "Graham Cracker", "snack", {}),
    ("marshmallow", "Marshmallow", "dessert_ing", {}),
]
INGREDIENTS_RAW.extend(GEO_CULTURE_INGREDIENTS_RAW)


# --- DIRECT CONSUMABLES ---------------------------------------------------------
# Direkt konsumierbare Getränke ohne Rezept. Die meisten werden programmatisch
# aus INGREDIENTS_RAW erzeugt (1 Ingredient == 1 DirectConsumable in typischer
# Portionsgröße). Kaffee-Spezialitäten mit Rezept-BOM (Cappuccino etc.) landen
# stattdessen unter RECIPES_RAW.


def mk_direct(item_id: str, name: str, category: str, demand_group: str,
              ingredient_id: str, serving_size_l: float, **overrides) -> dict:
    return dict(
        id=item_id,
        name=name,
        category=category,
        demand_group=demand_group,
        tags=overrides.get("tags", []),
        popular=overrides.get("popular", False),
        aliases_hint=overrides.get("aliases_hint", []),
        ingredient_id=ingredient_id,
        serving_size_l=serving_size_l,
        abv=overrides.get("abv", 0.0),
        contains_caffeine=overrides.get("contains_caffeine", False),
    )


# Standard-Portionsgröße (Liter) je Ingredient-Familie für Direktkonsum
_DIRECT_SERVING_SIZE_L: dict[str, float] = {
    "beer": 0.3,
    "wine": 0.2,
    "sparkling_wine": 0.15,
    "softdrink": 0.33,
    "water": 0.5,
    "energy": 0.25,
    "juice": 0.2,
    "spirit": 0.04,
    "liqueur": 0.04,
    "fortified_wine": 0.06,
}

# Ingredients, die zwar zu einer der obigen Familien gehören, aber NICHT
# direkt (unverändert) trinkbar sind (nur Rezeptzutat).
_DIRECT_CONSUMABLE_EXCLUDE_IDS: set[str] = {
    "lime_juice_fresh", "lemon_juice_fresh",
    # Grüner Tee (Flasche) braucht explizite "tea"-Tags (§4 Geo-Kultur-Spec) und
    # wird deshalb weiter unten manuell via mk_direct() gebaut statt generisch
    # aus der Softdrink-Familie erzeugt zu werden.
    "green_tea_bottled",
}

DIRECT_CONSUMABLES_RAW: list[dict] = []
for _iid, _name, _family, _overrides in INGREDIENTS_RAW:
    if _family not in _DIRECT_SERVING_SIZE_L:
        continue
    if _iid in _DIRECT_CONSUMABLE_EXCLUDE_IDS:
        continue
    _serving = _DIRECT_SERVING_SIZE_L[_family]
    _fam_defaults = FAMILY_DEFAULTS[_family]
    _abv = _overrides.get("abv", _fam_defaults.get("abv", 0.0))
    _demand_group = _overrides.get("demand_group", _fam_defaults["demand_group"])
    _caffeine = _overrides.get("contains_caffeine", _fam_defaults.get("contains_caffeine", False))
    _category = _overrides.get("category", _fam_defaults["category"])
    _popular = _overrides.get("popular", False)
    DIRECT_CONSUMABLES_RAW.append(
        mk_direct(_iid, _name, _category, _demand_group, _iid, _serving,
                  abv=_abv, contains_caffeine=_caffeine, popular=_popular)
    )

# Kaffee-Direktkonsum (manuell, da Familie "coffee" unterschiedliche Portionsgrößen hat)
DIRECT_CONSUMABLES_RAW.extend([
    mk_direct("filter_coffee", "Kaffee", "coffee", "non_alcoholic_beverage",
              "filter_coffee", 0.2, contains_caffeine=True, popular=True),
    mk_direct("espresso", "Espresso", "coffee", "non_alcoholic_beverage",
              "espresso", 0.03, contains_caffeine=True),
    mk_direct("cold_brew", "Cold Brew", "coffee", "non_alcoholic_beverage",
              "cold_brew", 0.25, contains_caffeine=True),
])

# Zusätzliche Softdrink-Varianten / Wasser-Varianten, die nicht 1:1 aus der
# Ingredient-Liste kommen (z. B. Tafelwasser als Alias-Konzept auf Mineralwasser).
DIRECT_CONSUMABLES_RAW.extend([
    mk_direct("tafelwasser", "Tafelwasser", "water", "beverage_general",
              "mineral_water_still", 0.5),
])


# --- Snack / Obst-Direktkonsum (feste Speisen ohne Rezept) ----------------------
# Diese Artikel werden "wie gekauft" verzehrt (Chips, Nüsse, Oliven, Trauben, ...).
# serving_size_l wird hier im Sinne von "typische Portionsgröße in der Einheit
# des Ingredients" verwendet (bei diesen Einträgen kg statt Liter).

_SNACK_DIRECT_IDS: list[tuple] = [
    ("potato_chips", "Kartoffelchips", 0.04, True),
    ("paprika_chips", "Paprikachips", 0.04, False),
    ("salt_vinegar_chips", "Salt & Vinegar Chips", 0.04, False),
    ("tortilla_chips", "Tortilla Chips", 0.04, True),
    ("pretzel_sticks", "Salzstangen", 0.03, False),
    ("crackers", "Cracker", 0.03, False),
    ("cheese_crackers", "Käsecracker", 0.03, False),
    ("peanuts", "Erdnüsse", 0.03, False),
    ("cashews", "Cashews", 0.03, False),
    ("almonds", "Mandeln", 0.03, False),
    ("nut_mix", "Nussmix", 0.04, False),
    ("popcorn_salty", "Popcorn salzig", 0.03, False),
    ("popcorn_sweet", "Popcorn süß", 0.03, False),
    ("rice_cakes", "Reiswaffeln", 0.02, False),
    ("grissini", "Grissini", 0.02, False),
    ("mini_salami", "Mini-Salami", 0.04, False),
    ("beef_jerky", "Beef Jerky", 0.03, False),
    ("snack_sausages", "Snackwürstchen", 0.06, False),
    ("grapes_snack", "Trauben (Snack)", 0.08, False),
    ("olives", "Oliven", 0.05, False),
    ("watermelon", "Wassermelone", 0.15, False),
    ("strawberry", "Erdbeeren", 0.1, False),
    ("mixed_berries", "Beerenmix", 0.08, False),
]

for _sid, _sname, _sserving, _spopular in _SNACK_DIRECT_IDS:
    _sing_family = next(f for i, n, f, o in INGREDIENTS_RAW if i == _sid)
    _sing_defaults = FAMILY_DEFAULTS[_sing_family]
    DIRECT_CONSUMABLES_RAW.append(
        mk_direct(_sid, _sname, _sing_defaults["category"], "snack",
                  _sid, _sserving, popular=_spopular)
    )

# Käsewürfel und Antipasti als eigene Snack-Direktkonsum-Einträge (auf Basis
# vorhandener Käse-/Gemüse-Ingredients)
DIRECT_CONSUMABLES_RAW.extend([
    mk_direct("cheese_cubes", "Käsewürfel", "cheese", "snack", "cheddar", 0.04),
    mk_direct("gemuesesticks", "Gemüsesticks", "vegetable", "snack", "carrot", 0.08),
])


# --- Zusätzliche Ingredients für Food-Rezept-BOMs -------------------------------

FAMILY_DEFAULTS.update({
    "oil": dict(unit="l", category="oil", demand_group="condiment", is_vegan=True),
})

FOOD_EXTRA_INGREDIENTS_RAW: list[tuple] = [
    ("baking_powder", "Backpulver", "spice", {}),
    ("vanilla_extract", "Vanilleextrakt", "spice", {}),
    ("powdered_sugar", "Puderzucker", "spice", {}),
    ("breadcrumbs", "Paniermehl", "bread", {"gluten_free": False}),
    ("cooking_oil", "Pflanzenöl", "oil", {}),
    ("olive_oil", "Olivenöl", "oil", {}),
    ("caesar_dressing", "Caesar Dressing", "sauce", {"is_vegan": False, "lactose_free": False}),
    ("vinaigrette", "Vinaigrette", "sauce", {"is_vegan": True}),
    ("vegetable_stock", "Gemüsebrühe", "sauce", {"is_vegan": True}),
    ("beef_stock", "Rinderbrühe", "sauce", {"is_vegan": False, "is_vegetarian": False}),
    ("fried_onions", "Röstzwiebeln", "vegetable", {}),
    ("soy_mince", "Sojahack", "vegan_protein", {"is_vegan": True}),
    ("curry_paste", "Currypaste", "sauce", {"is_vegan": True}),
    ("garam_masala", "Garam Masala", "spice", {}),
    ("peas", "Erbsen", "vegetable", {}),
    ("pickles", "Essiggurken", "vegetable", {}),
    ("taco_seasoning", "Taco-Gewürzmischung", "spice", {}),
    ("honey", "Honig", "syrup", {"is_vegan": False}),
    ("cornstarch", "Speisestärke", "spice", {}),
    ("galliano", "Galliano", "liqueur", {"abv": 40.0}),
]
INGREDIENTS_RAW.extend(FOOD_EXTRA_INGREDIENTS_RAW)


# --- Ingredient-Lookup (für automatische Dietary-Flag-Ableitung bei Recipes) ----

INGREDIENTS_BY_ID: dict[str, dict] = {
    _iid: mk_ingredient(_iid, _name, _fam, **_ov) for _iid, _name, _fam, _ov in INGREDIENTS_RAW
}


# --- RECIPES: gemeinsame Hilfsfunktionen ----------------------------------------


def comp(ingredient_id: str, amount: float, unit: str = "l", optional: bool = False, note: str = "") -> dict:
    """Eine RecipeComponent als dict. Prüft sofort, dass das Ingredient existiert."""
    if ingredient_id not in INGREDIENTS_BY_ID:
        raise KeyError(f"Unbekannte ingredient_id in Rezeptkomponente: {ingredient_id!r}")
    return dict(ingredient_id=ingredient_id, amount=amount, unit=unit, optional=optional, note=note)


def mk_recipe(item_id: str, name: str, category: str, demand_group: str,
              components: list[dict], *, ice_profile: str = "", garnish: list[str] | None = None,
              satiety_factor: float = 1.0, serving_unit: str = "portion",
              tags: list[str] | None = None, popular: bool = False,
              aliases_hint: list[str] | None = None,
              is_vegetarian: bool | None = None, is_vegan: bool | None = None,
              contains_alcohol: bool | None = None) -> dict:
    core_ids = [c["ingredient_id"] for c in components if not c.get("optional")]
    if is_vegan is None:
        is_vegan = all(INGREDIENTS_BY_ID[i]["is_vegan"] for i in core_ids) if core_ids else True
    if is_vegetarian is None:
        is_vegetarian = all(INGREDIENTS_BY_ID[i]["is_vegetarian"] for i in core_ids) if core_ids else True
    if contains_alcohol is None:
        contains_alcohol = any(INGREDIENTS_BY_ID[i]["contains_alcohol"] for i in core_ids)
    return dict(
        id=item_id,
        name=name,
        category=category,
        demand_group=demand_group,
        tags=tags or [],
        popular=popular,
        aliases_hint=aliases_hint or [],
        components=components,
        ice_profile=ice_profile,
        garnish=garnish or [],
        satiety_factor=satiety_factor,
        serving_unit=serving_unit,
        is_vegetarian=is_vegetarian,
        is_vegan=is_vegan,
        contains_alcohol=contains_alcohol,
    )


def mk_highball(item_id: str, name: str, category: str,
                 spirit_id: str, spirit_amount: float,
                 mixer_id: str, mixer_amount: float, *,
                 second_spirit: tuple[str, float] | None = None,
                 garnish: list[str] | None = None,
                 ice_profile: str = "highball", popular: bool = False) -> dict:
    """Kompakter Helfer für einfache Spirituose+Mixer-Longdrinks."""
    components = [comp(spirit_id, spirit_amount, "l")]
    if second_spirit:
        components.append(comp(second_spirit[0], second_spirit[1], "l"))
    components.append(comp(mixer_id, mixer_amount, "l"))
    return mk_recipe(item_id, name, category, "alcoholic_beverage", components,
                      ice_profile=ice_profile, garnish=garnish or [], serving_unit="glass",
                      popular=popular)


# --- COCKTAIL-REZEPTE (Spec §11-13) ---------------------------------------------
# Jeder Cocktail wird genau einmal implementiert, auch wenn er in mehreren
# Spec-Unterabschnitten genannt wird (z.B. Rum Cola taucht sowohl unter
# "Rum-Cocktails" als auch unter "Party-Longdrinks" auf).

COCKTAILS_RAW: list[dict] = [
    # --- Vodka-Cocktails ---------------------------------------------------
    mk_recipe("espresso_martini", "Espresso Martini", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("coffee_liqueur", 0.02), comp("espresso", 0.02), comp("simple_syrup", 0.01),
    ], ice_profile="shaken", garnish=["coffee beans"], serving_unit="glass", popular=True),
    mk_recipe("porn_star_martini", "Porn Star Martini", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("passionfruit_liqueur", 0.015), comp("passionfruit_juice", 0.03),
        comp("lime_juice_fresh", 0.01), comp("simple_syrup", 0.01),
        comp("prosecco", 0.03, note="Side-Shot"),
    ], ice_profile="shaken", garnish=["passion fruit"], serving_unit="glass", popular=True),
    mk_recipe("moscow_mule", "Moscow Mule", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.045), comp("ginger_beer", 0.12), comp("lime_juice_fresh", 0.015),
    ], ice_profile="highball", garnish=["lime wedge", "mint"], serving_unit="glass", popular=True),
    mk_recipe("vodka_red_bull", "Vodka Red Bull", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("energy_drink_generic", 0.15),
    ], ice_profile="highball", serving_unit="glass", popular=True),
    mk_recipe("vodka_lemon", "Vodka Lemon", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("lemonade_lemon", 0.15),
    ], ice_profile="highball", garnish=["lemon wedge"], serving_unit="glass"),
    mk_recipe("vodka_tonic", "Vodka Tonic", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("tonic_water", 0.12),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("vodka_soda", "Vodka Soda", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("soda_water", 0.12),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("screwdriver", "Vodka Orange / Screwdriver", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("orange_juice", 0.14),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("vodka_cranberry", "Vodka Cranberry", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("cranberry_juice", 0.14),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("sea_breeze", "Sea Breeze", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("cranberry_juice", 0.08), comp("grapefruit_juice", 0.06),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("bay_breeze", "Bay Breeze", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("cranberry_juice", 0.08), comp("pineapple_juice", 0.06),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("cape_codder", "Cape Codder", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("cranberry_juice", 0.14),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("black_russian", "Black Russian", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("coffee_liqueur", 0.02),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("white_russian", "White Russian", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("coffee_liqueur", 0.02), comp("cream", 0.02),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("cosmopolitan", "Cosmopolitan", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("triple_sec", 0.015), comp("cranberry_juice", 0.03), comp("lime_juice_fresh", 0.015),
    ], ice_profile="shaken", garnish=["orange peel"], serving_unit="glass"),
    mk_recipe("sex_on_the_beach", "Sex on the Beach", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("peach_liqueur", 0.02), comp("orange_juice", 0.06), comp("cranberry_juice", 0.06),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("woo_woo", "Woo Woo", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("peach_liqueur", 0.02), comp("cranberry_juice", 0.1),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("french_martini", "French Martini", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("raspberry_liqueur", 0.015), comp("pineapple_juice", 0.03),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("bloody_mary", "Bloody Mary", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("tomato_juice", 0.12), comp("lemon_juice_fresh", 0.01),
        comp("tabasco", 0.002), comp("worcestershire_sauce", 0.003),
        comp("salt", 0.001, "kg", optional=True), comp("pepper", 0.001, "kg", optional=True),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("harvey_wallbanger", "Harvey Wallbanger", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("orange_juice", 0.12), comp("galliano", 0.01),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("blue_lagoon", "Blue Lagoon", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("blue_curacao", 0.02), comp("lemonade_lemon", 0.1),
    ], ice_profile="highball", garnish=["cocktail cherry"], serving_unit="glass"),
    mk_recipe("caipiroska", "Caipiroska", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("lime", 0.06, "kg"), comp("sugar", 0.015, "kg"),
    ], ice_profile="crushed", serving_unit="glass"),
    mk_recipe("vodka_martini", "Vodka Martini", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.06), comp("dry_vermouth", 0.01),
    ], ice_profile="stirred", garnish=["olive"], serving_unit="glass"),
    mk_recipe("lemon_drop_martini", "Lemon Drop Martini", "cocktail_vodka", "alcoholic_beverage", [
        comp("vodka", 0.05), comp("triple_sec", 0.015), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.01),
    ], ice_profile="shaken", garnish=["sugar rim"], serving_unit="glass"),

    # --- Gin-Cocktails -------------------------------------------------------
    mk_recipe("gin_tonic", "Gin Tonic", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.04), comp("tonic_water", 0.12),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass", popular=True),
    mk_recipe("gin_lemon", "Gin Lemon", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.04), comp("lemonade_lemon", 0.14),
    ], ice_profile="highball", garnish=["lemon wedge"], serving_unit="glass"),
    mk_recipe("gin_soda", "Gin Soda", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.04), comp("soda_water", 0.12),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("dry_martini", "Dry Martini", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.06), comp("dry_vermouth", 0.01),
    ], ice_profile="stirred", garnish=["olive"], serving_unit="glass"),
    mk_recipe("dirty_martini", "Dirty Martini", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.06), comp("dry_vermouth", 0.01), comp("olives", 0.01, "kg", note="Olivenlake"),
    ], ice_profile="stirred", garnish=["olive"], serving_unit="glass"),
    mk_recipe("gibson", "Gibson", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.06), comp("dry_vermouth", 0.01), comp("onion", 0.005, "kg", note="Cocktailzwiebel"),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("negroni", "Negroni", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.03), comp("campari", 0.03), comp("sweet_vermouth", 0.03),
    ], ice_profile="stirred", garnish=["orange peel"], serving_unit="glass", popular=True),
    mk_recipe("white_negroni", "White Negroni", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.03), comp("lillet_blanc", 0.03), comp("cynar", 0.03),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("tom_collins", "Tom Collins", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("soda_water", 0.06),
    ], ice_profile="highball", garnish=["lemon wedge"], serving_unit="glass"),
    mk_recipe("john_collins", "John Collins", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("soda_water", 0.06),
    ], ice_profile="highball", garnish=["lemon wedge"], serving_unit="glass"),
    mk_recipe("gin_fizz", "Gin Fizz", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015),
        comp("soda_water", 0.06), comp("egg_white", 1, "pcs", optional=True),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("ramos_gin_fizz", "Ramos Gin Fizz", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("lemon_juice_fresh", 0.015), comp("lime_juice_fresh", 0.015),
        comp("simple_syrup", 0.02), comp("cream", 0.015), comp("egg_white", 1, "pcs"), comp("soda_water", 0.03),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("bramble", "Bramble", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.05), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.01), comp("blackberry_liqueur", 0.015),
    ], ice_profile="crushed", garnish=["berries"], serving_unit="glass"),
    mk_recipe("gin_basil_smash", "Gin Basil Smash", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.05), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("basil", 0.003, "kg"),
    ], ice_profile="shaken", garnish=["basil"], serving_unit="glass"),
    mk_recipe("bees_knees", "Bee's Knees", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.05), comp("lemon_juice_fresh", 0.02), comp("honey_syrup", 0.02),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("clover_club", "Clover Club", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("lemon_juice_fresh", 0.015), comp("raspberry_syrup", 0.015), comp("egg_white", 1, "pcs"),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("southside", "Southside", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.05), comp("lime_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("mint", 0.002, "kg"),
    ], ice_profile="shaken", garnish=["mint"], serving_unit="glass"),
    mk_recipe("french_75", "French 75", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.03), comp("lemon_juice_fresh", 0.015), comp("simple_syrup", 0.01), comp("champagne", 0.09),
    ], ice_profile="no_ice", garnish=["lemon peel"], serving_unit="glass"),
    mk_recipe("martinez", "Martinez", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.04), comp("sweet_vermouth", 0.04), comp("maraschino", 0.01), comp("orange_bitters", 0.001),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("vesper", "Vesper", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("vodka", 0.015), comp("lillet_blanc", 0.0075),
    ], ice_profile="stirred", garnish=["lemon peel"], serving_unit="glass"),
    mk_recipe("singapore_sling", "Singapore Sling", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.03), comp("cherry_liqueur", 0.015), comp("triple_sec", 0.0075), comp("amaro_generic", 0.0075),
        comp("pineapple_juice", 0.03), comp("lime_juice_fresh", 0.015), comp("grenadine", 0.005),
        comp("angostura_bitters", 0.001),
    ], ice_profile="highball", garnish=["pineapple", "cocktail cherry"], serving_unit="glass"),
    mk_recipe("aviation", "Aviation", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("maraschino", 0.015), comp("lemon_juice_fresh", 0.015),
    ], ice_profile="shaken", garnish=["cocktail cherry"], serving_unit="glass"),
    mk_recipe("last_word", "Last Word", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.02), comp("chartreuse_green", 0.02), comp("maraschino", 0.02), comp("lime_juice_fresh", 0.02),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("gin_rickey", "Gin Rickey", "cocktail_gin", "alcoholic_beverage", [
        comp("gin", 0.045), comp("lime_juice_fresh", 0.015), comp("soda_water", 0.1),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("pink_lady", "Pink Lady", "cocktail_gin", "alcoholic_beverage", [
        comp("gin_pink", 0.045), comp("grenadine", 0.01), comp("lemon_juice_fresh", 0.015), comp("egg_white", 1, "pcs"),
    ], ice_profile="shaken", serving_unit="glass"),

    # --- Rum-Cocktails ---------------------------------------------------
    mk_recipe("cuba_libre", "Cuba Libre", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.04), comp("cola", 0.12), comp("lime_juice_fresh", 0.01),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("rum_cola", "Rum Cola", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.04), comp("cola", 0.14),
    ], ice_profile="highball", serving_unit="glass", popular=True),
    mk_recipe("mojito", "Mojito", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("lime_juice_fresh", 0.02), comp("simple_syrup", 0.015),
        comp("mint", 0.003, "kg"), comp("soda_water", 0.06),
    ], ice_profile="crushed", garnish=["mint", "lime wedge"], serving_unit="glass", popular=True),
    mk_recipe("daiquiri", "Daiquiri", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("lime_juice_fresh", 0.02), comp("simple_syrup", 0.015),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("frozen_daiquiri", "Frozen Daiquiri", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("lime_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("crushed_ice", 0.05, "kg"),
    ], ice_profile="blended", serving_unit="glass"),
    mk_recipe("strawberry_daiquiri", "Strawberry Daiquiri", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("lime_juice_fresh", 0.02), comp("simple_syrup", 0.01), comp("strawberry", 0.05, "kg"),
    ], ice_profile="blended", serving_unit="glass"),
    mk_recipe("hemingway_daiquiri", "Hemingway Daiquiri", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("lime_juice_fresh", 0.015), comp("grapefruit_juice", 0.02), comp("maraschino", 0.01),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("pina_colada", "Piña Colada", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.04), comp("coconut_cream", 0.04), comp("pineapple_juice", 0.08),
    ], ice_profile="blended", garnish=["pineapple"], serving_unit="glass", popular=True),
    mk_recipe("mai_tai", "Mai Tai", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_aged", 0.03), comp("rum_dark", 0.02), comp("triple_sec", 0.015), comp("lime_juice_fresh", 0.02),
        comp("orgeat_syrup", 0.01), comp("grenadine", 0.005),
    ], ice_profile="crushed", garnish=["mint", "pineapple"], serving_unit="glass"),
    mk_recipe("dark_n_stormy", "Dark 'N' Stormy", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.05), comp("ginger_beer", 0.12), comp("lime_juice_fresh", 0.01),
    ], ice_profile="highball", garnish=["lime wedge"], serving_unit="glass"),
    mk_recipe("planters_punch", "Planter's Punch", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.05), comp("orange_juice", 0.04), comp("pineapple_juice", 0.04),
        comp("lime_juice_fresh", 0.015), comp("grenadine", 0.01), comp("angostura_bitters", 0.001),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("zombie", "Zombie", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.02), comp("rum_dark", 0.02), comp("rum_overproof", 0.015), comp("lime_juice_fresh", 0.02),
        comp("passionfruit_juice", 0.02), comp("grenadine", 0.01), comp("falernum", 0.01),
    ], ice_profile="crushed", serving_unit="glass"),
    mk_recipe("hurricane", "Hurricane", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.03), comp("rum_dark", 0.03), comp("passionfruit_juice", 0.04),
        comp("orange_juice", 0.02), comp("lime_juice_fresh", 0.015), comp("grenadine", 0.01),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("jungle_bird", "Jungle Bird", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.04), comp("campari", 0.015), comp("pineapple_juice", 0.03),
        comp("lime_juice_fresh", 0.01), comp("simple_syrup", 0.005),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("mary_pickford", "Mary Pickford", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("pineapple_juice", 0.04), comp("grenadine", 0.01), comp("maraschino", 0.005),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("rum_punch", "Rum Punch", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.04), comp("orange_juice", 0.05), comp("pineapple_juice", 0.05), comp("grenadine", 0.01),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("painkiller", "Painkiller", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.05), comp("pineapple_juice", 0.06), comp("orange_juice", 0.02), comp("coconut_cream", 0.02),
    ], ice_profile="crushed", garnish=["orange slice"], serving_unit="glass"),
    mk_recipe("bahama_mama", "Bahama Mama", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.02), comp("rum_spiced", 0.02), comp("coffee_liqueur", 0.01),
        comp("orange_juice", 0.04), comp("pineapple_juice", 0.04), comp("grenadine", 0.005),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("blue_hawaiian", "Blue Hawaiian", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.04), comp("blue_curacao", 0.02), comp("pineapple_juice", 0.06), comp("coconut_cream", 0.02),
    ], ice_profile="blended", serving_unit="glass"),
    mk_recipe("el_presidente", "El Presidente", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_white", 0.05), comp("dry_vermouth", 0.015), comp("triple_sec", 0.01), comp("grenadine", 0.005),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("corn_n_oil", "Corn 'n' Oil", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_dark", 0.05), comp("falernum", 0.01), comp("lime_juice_fresh", 0.01), comp("angostura_bitters", 0.002),
    ], ice_profile="crushed", serving_unit="glass"),
    mk_recipe("rum_old_fashioned", "Rum Old Fashioned", "cocktail_rum", "alcoholic_beverage", [
        comp("rum_aged", 0.05), comp("simple_syrup", 0.01), comp("angostura_bitters", 0.002),
    ], ice_profile="stirred", garnish=["orange peel"], serving_unit="glass"),

    # --- Tequila / Mezcal ---------------------------------------------------
    mk_recipe("margarita", "Margarita", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("triple_sec", 0.02), comp("lime_juice_fresh", 0.02),
    ], ice_profile="shaken", garnish=["salt rim"], serving_unit="glass", popular=True),
    mk_recipe("frozen_margarita", "Frozen Margarita", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("triple_sec", 0.02), comp("lime_juice_fresh", 0.02), comp("crushed_ice", 0.06, "kg"),
    ], ice_profile="blended", serving_unit="glass"),
    mk_recipe("strawberry_margarita", "Strawberry Margarita", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("triple_sec", 0.015), comp("lime_juice_fresh", 0.015), comp("strawberry", 0.05, "kg"),
    ], ice_profile="blended", serving_unit="glass"),
    mk_recipe("tommys_margarita", "Tommy's Margarita", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("lime_juice_fresh", 0.02), comp("agave_syrup", 0.015),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("spicy_margarita", "Spicy Margarita", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("triple_sec", 0.015), comp("lime_juice_fresh", 0.02), comp("jalapeno", 0.005, "kg"),
    ], ice_profile="shaken", garnish=["salt rim"], serving_unit="glass"),
    mk_recipe("mezcal_margarita", "Mezcal Margarita", "cocktail_tequila", "alcoholic_beverage", [
        comp("mezcal", 0.05), comp("triple_sec", 0.02), comp("lime_juice_fresh", 0.02),
    ], ice_profile="shaken", garnish=["salt rim"], serving_unit="glass"),
    mk_recipe("paloma", "Paloma", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("grapefruit_juice", 0.1), comp("lime_juice_fresh", 0.01), comp("soda_water", 0.03),
    ], ice_profile="highball", garnish=["salt rim"], serving_unit="glass"),
    mk_recipe("tequila_sunrise", "Tequila Sunrise", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("orange_juice", 0.12), comp("grenadine", 0.01),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("tequila_soda", "Tequila Soda", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.04), comp("soda_water", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("tequila_tonic", "Tequila Tonic", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.04), comp("tonic_water", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("ranch_water", "Ranch Water", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("soda_water", 0.12), comp("lime_juice_fresh", 0.02),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("el_diablo", "El Diablo", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.04), comp("creme_de_cassis", 0.01), comp("lime_juice_fresh", 0.015), comp("ginger_beer", 0.1),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("matador", "Matador", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.05), comp("pineapple_juice", 0.08), comp("lime_juice_fresh", 0.015),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("naked_and_famous", "Naked & Famous", "cocktail_tequila", "alcoholic_beverage", [
        comp("mezcal", 0.02), comp("chartreuse_yellow", 0.02), comp("aperol", 0.02), comp("lime_juice_fresh", 0.02),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("oaxaca_old_fashioned", "Oaxaca Old Fashioned", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_reposado", 0.04), comp("mezcal", 0.01), comp("agave_syrup", 0.01), comp("angostura_bitters", 0.002),
    ], ice_profile="stirred", garnish=["orange peel"], serving_unit="glass"),
    mk_recipe("mexican_mule", "Mexican Mule", "cocktail_tequila", "alcoholic_beverage", [
        comp("tequila_blanco", 0.04), comp("ginger_beer", 0.12), comp("lime_juice_fresh", 0.015),
    ], ice_profile="highball", serving_unit="glass"),

    # --- Whiskey ---------------------------------------------------------
    mk_recipe("whiskey_cola", "Whiskey Cola", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.04), comp("cola", 0.14),
    ], ice_profile="highball", serving_unit="glass", popular=True),
    mk_recipe("whiskey_ginger", "Whiskey Ginger", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.04), comp("ginger_ale", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("whiskey_sour", "Whiskey Sour", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.05), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015),
        comp("egg_white", 1, "pcs", optional=True),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("new_york_sour", "New York Sour", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.05), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("red_wine", 0.015),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("old_fashioned", "Old Fashioned", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.06), comp("simple_syrup", 0.01), comp("angostura_bitters", 0.002),
    ], ice_profile="stirred", garnish=["orange peel"], serving_unit="glass", popular=True),
    mk_recipe("manhattan", "Manhattan", "cocktail_whiskey", "alcoholic_beverage", [
        comp("rye_whiskey", 0.05), comp("sweet_vermouth", 0.02), comp("angostura_bitters", 0.002),
    ], ice_profile="stirred", garnish=["cocktail cherry"], serving_unit="glass"),
    mk_recipe("perfect_manhattan", "Perfect Manhattan", "cocktail_whiskey", "alcoholic_beverage", [
        comp("rye_whiskey", 0.05), comp("sweet_vermouth", 0.01), comp("dry_vermouth", 0.01), comp("angostura_bitters", 0.002),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("dry_manhattan", "Dry Manhattan", "cocktail_whiskey", "alcoholic_beverage", [
        comp("rye_whiskey", 0.05), comp("dry_vermouth", 0.02), comp("angostura_bitters", 0.002),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("boulevardier", "Boulevardier", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.03), comp("campari", 0.03), comp("sweet_vermouth", 0.03),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("mint_julep", "Mint Julep", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.06), comp("simple_syrup", 0.01), comp("mint", 0.004, "kg"),
    ], ice_profile="crushed", garnish=["mint"], serving_unit="glass"),
    mk_recipe("lynchburg_lemonade", "Lynchburg Lemonade", "cocktail_whiskey", "alcoholic_beverage", [
        comp("tennessee_whiskey", 0.04), comp("triple_sec", 0.015), comp("lemon_juice_fresh", 0.02), comp("lemonade_lemon", 0.08),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("penicillin", "Penicillin", "cocktail_whiskey", "alcoholic_beverage", [
        comp("scotch_whisky", 0.05), comp("honey_syrup", 0.015), comp("lemon_juice_fresh", 0.02), comp("ginger_syrup", 0.01),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("paper_plane", "Paper Plane", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.02), comp("amaro_generic", 0.02), comp("aperol", 0.02), comp("lemon_juice_fresh", 0.02),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("godfather", "Godfather", "cocktail_whiskey", "alcoholic_beverage", [
        comp("scotch_whisky", 0.04), comp("amaretto", 0.02),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("irish_coffee", "Irish Coffee", "cocktail_whiskey", "alcoholic_beverage", [
        comp("irish_whiskey", 0.04), comp("filter_coffee", 0.1), comp("cream", 0.02), comp("sugar", 0.005, "kg"),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("rusty_nail", "Rusty Nail", "cocktail_whiskey", "alcoholic_beverage", [
        comp("scotch_whisky", 0.04), comp("drambuie", 0.02),
    ], ice_profile="stirred", serving_unit="glass"),
    mk_recipe("whiskey_highball", "Whiskey Highball", "cocktail_whiskey", "alcoholic_beverage", [
        comp("scotch_whisky", 0.04), comp("soda_water", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("john_collins_whiskey", "John Collins (Whiskey-Variante)", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.045), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("soda_water", 0.06),
    ], ice_profile="highball", garnish=["lemon wedge"], serving_unit="glass"),

    # --- Brandy / Cognac / Sonstige ---------------------------------------
    mk_recipe("sidecar", "Sidecar", "cocktail_brandy", "alcoholic_beverage", [
        comp("cognac", 0.05), comp("triple_sec", 0.02), comp("lemon_juice_fresh", 0.02),
    ], ice_profile="shaken", garnish=["sugar rim"], serving_unit="glass"),
    mk_recipe("french_connection", "French Connection", "cocktail_brandy", "alcoholic_beverage", [
        comp("cognac", 0.04), comp("amaretto", 0.02),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("brandy_alexander", "Brandy Alexander", "cocktail_brandy", "alcoholic_beverage", [
        comp("cognac", 0.03), comp("creme_de_cacao", 0.03), comp("cream", 0.03),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("between_the_sheets", "Between the Sheets", "cocktail_brandy", "alcoholic_beverage", [
        comp("cognac", 0.02), comp("rum_white", 0.02), comp("triple_sec", 0.02), comp("lemon_juice_fresh", 0.02),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("horses_neck", "Horse's Neck", "cocktail_brandy", "alcoholic_beverage", [
        comp("brandy", 0.05), comp("ginger_ale", 0.12),
    ], ice_profile="highball", garnish=["lemon peel"], serving_unit="glass"),
    mk_recipe("sazerac", "Sazerac", "cocktail_brandy", "alcoholic_beverage", [
        comp("rye_whiskey", 0.06), comp("absinthe", 0.005), comp("simple_syrup", 0.01), comp("peychauds_bitters", 0.002),
    ], ice_profile="stirred", garnish=["lemon peel"], serving_unit="glass"),
    mk_recipe("pisco_sour", "Pisco Sour", "cocktail_brandy", "alcoholic_beverage", [
        comp("pisco", 0.05), comp("lime_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("egg_white", 1, "pcs"),
    ], ice_profile="shaken", garnish=["angostura drops"], serving_unit="glass"),
    mk_recipe("caipirinha", "Caipirinha", "cocktail_brandy", "alcoholic_beverage", [
        comp("cachaca", 0.05), comp("lime", 0.06, "kg"), comp("sugar", 0.015, "kg"),
    ], ice_profile="crushed", serving_unit="glass", popular=True),
    mk_recipe("amaretto_sour", "Amaretto Sour", "cocktail_brandy", "alcoholic_beverage", [
        comp("amaretto", 0.05), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.01),
        comp("egg_white", 1, "pcs", optional=True),
    ], ice_profile="shaken", serving_unit="glass"),
    mk_recipe("godmother", "Godmother", "cocktail_brandy", "alcoholic_beverage", [
        comp("vodka", 0.04), comp("amaretto", 0.02),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("jaegerbomb", "Jägerbomb", "cocktail_brandy", "alcoholic_beverage", [
        comp("jaegermeister", 0.04), comp("energy_drink_generic", 0.1),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("sambuca_coffee", "Sambuca Coffee", "cocktail_brandy", "alcoholic_beverage", [
        comp("sambuca", 0.03), comp("espresso", 0.03),
    ], ice_profile="no_ice", serving_unit="glass"),

    # --- Spritz / Wein / Schaumwein ---------------------------------------
    mk_recipe("aperol_spritz", "Aperol Spritz", "cocktail_spritz", "alcoholic_beverage", [
        comp("aperol", 0.06), comp("prosecco", 0.09), comp("soda_water", 0.03),
    ], ice_profile="no_ice", garnish=["orange slice"], serving_unit="glass", popular=True),
    mk_recipe("campari_spritz", "Campari Spritz", "cocktail_spritz", "alcoholic_beverage", [
        comp("campari", 0.06), comp("prosecco", 0.09), comp("soda_water", 0.03),
    ], ice_profile="no_ice", garnish=["orange slice"], serving_unit="glass"),
    mk_recipe("limoncello_spritz", "Limoncello Spritz", "cocktail_spritz", "alcoholic_beverage", [
        comp("limoncello", 0.05), comp("prosecco", 0.09), comp("soda_water", 0.03),
    ], ice_profile="no_ice", garnish=["lemon peel"], serving_unit="glass"),
    mk_recipe("hugo", "Hugo", "cocktail_spritz", "alcoholic_beverage", [
        comp("elderflower_syrup", 0.02), comp("prosecco", 0.1), comp("soda_water", 0.03), comp("mint", 0.002, "kg"),
    ], ice_profile="no_ice", garnish=["mint", "lime wedge"], serving_unit="glass", popular=True),
    mk_recipe("lillet_wild_berry", "Lillet Wild Berry", "cocktail_spritz", "alcoholic_beverage", [
        comp("lillet_blanc", 0.06), comp("wild_berry_soda", 0.1),
    ], ice_profile="highball", garnish=["berries"], serving_unit="glass"),
    mk_recipe("mimosa", "Mimosa", "cocktail_spritz", "alcoholic_beverage", [
        comp("champagne", 0.075), comp("orange_juice", 0.075),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("bellini", "Bellini", "cocktail_spritz", "alcoholic_beverage", [
        comp("prosecco", 0.1), comp("peach_juice", 0.05),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("kir", "Kir", "cocktail_spritz", "alcoholic_beverage", [
        comp("white_wine", 0.12), comp("creme_de_cassis", 0.01),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("kir_royal", "Kir Royal", "cocktail_spritz", "alcoholic_beverage", [
        comp("champagne", 0.1), comp("creme_de_cassis", 0.01),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("rossini", "Rossini", "cocktail_spritz", "alcoholic_beverage", [
        comp("prosecco", 0.1), comp("strawberry", 0.04, "kg", note="püriert"),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("sgroppino", "Sgroppino", "cocktail_spritz", "alcoholic_beverage", [
        comp("prosecco", 0.06), comp("sorbet", 0.05, "kg"), comp("vodka", 0.01),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("americano", "Americano", "cocktail_spritz", "alcoholic_beverage", [
        comp("campari", 0.03), comp("sweet_vermouth", 0.03), comp("soda_water", 0.06),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("negroni_sbagliato", "Negroni Sbagliato", "cocktail_spritz", "alcoholic_beverage", [
        comp("prosecco", 0.06), comp("campari", 0.03), comp("sweet_vermouth", 0.03),
    ], ice_profile="no_ice", serving_unit="glass"),
    mk_recipe("sangria_rot", "Sangria Rot", "cocktail_spritz", "alcoholic_beverage", [
        comp("red_wine", 0.15), comp("orange", 0.02, "kg"), comp("apple", 0.02, "kg"),
        comp("triple_sec", 0.01), comp("orange_juice", 0.03),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("sangria_weiss", "Sangria Weiß", "cocktail_spritz", "alcoholic_beverage", [
        comp("white_wine", 0.15), comp("peach", 0.02, "kg"), comp("apple", 0.02, "kg"), comp("triple_sec", 0.01),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("tinto_de_verano", "Tinto de Verano", "cocktail_spritz", "alcoholic_beverage", [
        comp("red_wine", 0.1), comp("lemonade_lemon", 0.1),
    ], ice_profile="highball", serving_unit="glass"),

    # --- Party-Longdrinks (weitere, noch nicht genannte) --------------------
    mk_recipe("gin_wild_berry", "Gin Wild Berry", "cocktail_longdrink", "alcoholic_beverage", [
        comp("gin", 0.04), comp("wild_berry_soda", 0.14),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("malibu_orange", "Malibu Orange", "cocktail_longdrink", "alcoholic_beverage", [
        comp("malibu", 0.04), comp("orange_juice", 0.14),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("malibu_ananas", "Malibu Ananas", "cocktail_longdrink", "alcoholic_beverage", [
        comp("malibu", 0.04), comp("pineapple_juice", 0.14),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("jaegermeister_energy", "Jägermeister Energy", "cocktail_longdrink", "alcoholic_beverage", [
        comp("jaegermeister", 0.04), comp("energy_drink_generic", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("campari_orange", "Campari Orange", "cocktail_longdrink", "alcoholic_beverage", [
        comp("campari", 0.04), comp("orange_juice", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("aperol_orange", "Aperol Orange", "cocktail_longdrink", "alcoholic_beverage", [
        comp("aperol", 0.04), comp("orange_juice", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("lillet_tonic", "Lillet Tonic", "cocktail_longdrink", "alcoholic_beverage", [
        comp("lillet_blanc", 0.05), comp("tonic_water", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("tequila_orange", "Tequila Orange", "cocktail_longdrink", "alcoholic_beverage", [
        comp("tequila_blanco", 0.04), comp("orange_juice", 0.14),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("licor_43_milch", "Licor 43 Milch", "cocktail_longdrink", "alcoholic_beverage", [
        comp("licor_43", 0.04), comp("milk", 0.12),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("licor_43_orange", "Licor 43 Orange", "cocktail_longdrink", "alcoholic_beverage", [
        comp("licor_43", 0.04), comp("orange_juice", 0.12),
    ], ice_profile="highball", serving_unit="glass"),

    # --- Komplexe Drinks ---------------------------------------------------
    mk_recipe("long_island_iced_tea", "Long Island Iced Tea", "cocktail_complex", "alcoholic_beverage", [
        comp("vodka", 0.015), comp("gin", 0.015), comp("rum_white", 0.015), comp("tequila_blanco", 0.015),
        comp("triple_sec", 0.015), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015), comp("cola", 0.06),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("tokyo_iced_tea", "Tokyo Iced Tea", "cocktail_complex", "alcoholic_beverage", [
        comp("vodka", 0.015), comp("gin", 0.015), comp("rum_white", 0.015), comp("tequila_blanco", 0.015),
        comp("triple_sec", 0.015), comp("lemon_juice_fresh", 0.02), comp("simple_syrup", 0.015),
        comp("melon_liqueur", 0.015), comp("soda_water", 0.04),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("adios_motherfucker", "Adios Motherfucker", "cocktail_complex", "alcoholic_beverage", [
        comp("vodka", 0.015), comp("gin", 0.015), comp("rum_white", 0.015), comp("tequila_blanco", 0.015),
        comp("blue_curacao", 0.015), comp("lemon_juice_fresh", 0.02), comp("sprite", 0.06),
    ], ice_profile="highball", serving_unit="glass"),
    mk_recipe("tiki_punch", "Tiki Punch", "cocktail_complex", "alcoholic_beverage", [
        comp("rum_white", 0.03), comp("rum_dark", 0.03), comp("orange_juice", 0.04), comp("pineapple_juice", 0.04),
        comp("lime_juice_fresh", 0.015), comp("grenadine", 0.01), comp("orgeat_syrup", 0.01),
    ], ice_profile="crushed", serving_unit="glass"),
]

# --- Geo-Kultur-Cocktails (Geo-/Kultur-Kontext-Spec §4/§6) ----------------------
# Alkoholische Länder-Signature-Drinks für Peru, Dänemark und USA. Pisco Sour
# existiert bereits im Katalog (siehe COCKTAILS_RAW "cocktail_brandy" oben) und
# wird bewusst NICHT erneut angelegt - stattdessen zwei eigenständige weitere
# Pisco-Drinks (Chilcano, Maracuyá Sour).
COCKTAILS_RAW.extend([
    mk_recipe("chilcano", "Chilcano", "cocktail_brandy", "alcoholic_beverage", [
        comp("pisco", 0.05), comp("ginger_ale", 0.12), comp("lime_juice_fresh", 0.015),
        comp("angostura_bitters", 0.001, optional=True),
    ], ice_profile="highball", garnish=["lime wheel"], serving_unit="glass",
       tags=["cocktail", "spirit", "longdrink", "citrus", "traditional"]),
    mk_recipe("maracuya_sour", "Maracuyá Sour", "cocktail_brandy", "alcoholic_beverage", [
        comp("pisco", 0.05), comp("passionfruit_juice", 0.03), comp("lime_juice_fresh", 0.015),
        comp("simple_syrup", 0.015), comp("egg_white", 1, "pcs", optional=True),
    ], ice_profile="shaken", serving_unit="glass",
       tags=["cocktail", "spirit", "fruity", "tropical", "traditional"]),
    mk_recipe("gloegg", "Glögg", "cocktail_wine", "alcoholic_beverage", [
        comp("red_wine", 0.15), comp("cinnamon", 0.001, "kg"), comp("orange", 0.02, "kg"),
        comp("raisins", 0.01, "kg", optional=True), comp("sugar", 0.015, "kg"),
        comp("cardamom", 0.001, "kg", optional=True),
    ], ice_profile="no_ice", serving_unit="glass",
       tags=["hot_drink", "wine", "alcoholic", "festive", "traditional", "winter"]),
    mk_recipe("peach_bourbon_smash", "Peach Bourbon Smash", "cocktail_whiskey", "alcoholic_beverage", [
        comp("bourbon", 0.05), comp("peach", 0.04, "kg"), comp("mint", 0.003, "kg"),
        comp("lemon_juice_fresh", 0.015), comp("simple_syrup", 0.01),
    ], ice_profile="crushed", garnish=["mint", "peach slice"], serving_unit="glass",
       tags=["cocktail", "spirit", "fruity", "summer"]),
])


# --- Dips & Saucen sowie Brot als Direktkonsum (Spec §19/22) --------------------
# Diese Ingredients existieren bereits (Sauce-/Brot-Familie) und werden direkt
# als Beilage/Condiment auswählbar gemacht (kein Rezept nötig).

_DIP_DIRECT_IDS: list[str] = [
    "ketchup", "mayonnaise", "mustard", "sweet_mustard", "bbq_sauce", "burger_sauce",
    "cocktail_sauce", "curry_sauce", "aioli", "garlic_dip", "herb_dip", "tzatziki",
    "hummus", "salsa_mild", "salsa_hot", "guacamole", "sour_cream", "sweet_chili_sauce",
    "sriracha", "hot_sauce", "tabasco", "remoulade", "honey_mustard_sauce",
    "teriyaki_sauce", "cheese_sauce", "chili_cheese_sauce", "herb_butter", "garlic_butter",
]
for _did in _DIP_DIRECT_IDS:
    _dname = next(n for i, n, f, o in INGREDIENTS_RAW if i == _did)
    DIRECT_CONSUMABLES_RAW.append(
        mk_direct(_did, _dname, "sauce", "condiment", _did, 0.03)
    )

_BREAD_DIRECT_IDS: list[str] = [
    "baguette", "ciabatta", "flatbread", "bread_roll", "burger_bun", "hotdog_bun",
    "pretzel", "laugenstange", "white_bread", "toast_bread",
]
for _bid in _BREAD_DIRECT_IDS:
    _bname = next(n for i, n, f, o in INGREDIENTS_RAW if i == _bid)
    DIRECT_CONSUMABLES_RAW.append(
        mk_direct(_bid, _bname, "bread", "side", _bid, 1, popular=(_bid in ("baguette", "burger_bun")))
    )


# --- Geo-Kultur-Direktkonsum (manuell, da explizite Tags nötig) -----------------
# "sake" gehört zu keiner der automatisch verarbeiteten Familien (§4 Geo-Kultur-
# Spec), "green_tea_bottled" ist bewusst aus dem generischen Softdrink-Auto-Loop
# ausgeschlossen (siehe _DIRECT_CONSUMABLE_EXCLUDE_IDS oben) - beide brauchen
# handkuratierte Tags statt der generischen Kategorie-Defaults.

GEO_CULTURE_DIRECT_CONSUMABLES_RAW: list[dict] = [
    mk_direct("sake", "Sake", "sake", "alcoholic_beverage", "sake", 0.06,
              abv=15.0, tags=["alcoholic", "traditional", "premium", "wine"]),
    mk_direct("green_tea_bottled", "Grüner Tee (Flasche)", "softdrink", "non_alcoholic_beverage",
              "green_tea_bottled", 0.33, contains_caffeine=True,
              tags=["tea", "non_alcoholic", "refreshing", "caffeinated"]),
]
DIRECT_CONSUMABLES_RAW.extend(GEO_CULTURE_DIRECT_CONSUMABLES_RAW)


# --- FOOD-REZEPTE (Spec §14-23) -------------------------------------------------
# Jedes Gericht wird genau einmal implementiert, auch wenn es in mehreren
# Spec-Unterabschnitten genannt wird (z.B. Chicken Wings in §14 und §18,
# Hotdog/Currywurst in §14 und §17).

FOOD_RAW: list[dict] = [
    # --- Grillen (§14) -----------------------------------------------------
    mk_recipe("bratwurst", "Bratwurst", "grill", "main", [
        comp("pork_sausage_bratwurst", 0.15, "kg"), comp("bread_roll", 1, "pcs", optional=True),
        comp("mustard", 0.01, "l", optional=True),
    ], satiety_factor=0.45, popular=True),
    mk_recipe("rostbratwurst", "Rostbratwurst", "grill", "main", [
        comp("pork_sausage_bratwurst", 0.15, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.45),
    mk_recipe("nuernberger", "Nürnberger", "grill", "main", [
        comp("pork_sausage_nuernberger", 0.12, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.4),
    mk_recipe("thueringer", "Thüringer", "grill", "main", [
        comp("pork_sausage_thueringer", 0.15, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.45),
    mk_recipe("rindswurst", "Rindswurst", "grill", "main", [
        comp("beef_sausage", 0.15, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.45),
    mk_recipe("krakauer", "Krakauer", "grill", "main", [
        comp("pork_sausage_krakauer", 0.15, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.45),
    mk_recipe("currywurst", "Currywurst", "grill", "main", [
        comp("pork_sausage_currywurst", 0.15, "kg"), comp("ketchup", 0.02),
        comp("curry_sauce", 0.03), comp("paprika_powder", 0.002, "kg"),
    ], satiety_factor=0.5, popular=True),
    mk_recipe("bratwurst_im_broetchen", "Bratwurst im Brötchen", "grill", "main", [
        comp("pork_sausage_bratwurst", 0.15, "kg"), comp("bread_roll", 1, "pcs"), comp("mustard", 0.01),
    ], satiety_factor=0.5),
    mk_recipe("hotdog", "Hotdog", "grill", "main", [
        comp("hotdog_bun", 1, "pcs"), comp("pork_sausage_bratwurst", 0.1, "kg"),
        comp("ketchup", 0.015), comp("mustard", 0.01),
    ], satiety_factor=0.55, popular=True),
    mk_recipe("cheese_hotdog", "Cheese Hotdog", "grill", "main", [
        comp("hotdog_bun", 1, "pcs"), comp("pork_sausage_bratwurst", 0.1, "kg"),
        comp("ketchup", 0.015), comp("mustard", 0.01), comp("cheddar", 0.02, "kg"),
    ], satiety_factor=0.6),
    mk_recipe("chili_cheese_hotdog", "Chili Cheese Hotdog", "grill", "main", [
        comp("hotdog_bun", 1, "pcs"), comp("pork_sausage_bratwurst", 0.1, "kg"),
        comp("chili_cheese_sauce", 0.05), comp("jalapeno", 0.01, "kg", optional=True),
    ], satiety_factor=0.65),
    mk_recipe("rumpsteak", "Rumpsteak", "grill", "main", [
        comp("beef_steak_rump", 0.22, "kg"), comp("herb_butter", 0.015, optional=True),
    ], satiety_factor=1.0),
    mk_recipe("ribeye", "Ribeye", "grill", "main", [
        comp("beef_steak_ribeye", 0.25, "kg"), comp("herb_butter", 0.015, optional=True),
    ], satiety_factor=1.0, popular=True),
    mk_recipe("entrecote", "Entrecôte", "grill", "main", [
        comp("beef_entrecote", 0.22, "kg"), comp("herb_butter", 0.015, optional=True),
    ], satiety_factor=1.0),
    mk_recipe("nackensteak", "Nackensteak", "grill", "main", [
        comp("pork_neck_steak", 0.22, "kg"),
    ], satiety_factor=0.9),
    mk_recipe("schweinebauch", "Schweinebauch", "grill", "main", [
        comp("pork_belly", 0.2, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("schweinekotelett", "Schweinekotelett", "grill", "main", [
        comp("pork_chop", 0.22, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("spareribs", "Spareribs", "grill", "main", [
        comp("pork_ribs", 0.3, "kg"), comp("bbq_sauce", 0.03),
    ], satiety_factor=0.9),
    mk_recipe("bbq_ribs", "BBQ Ribs", "grill", "main", [
        comp("pork_ribs", 0.32, "kg"), comp("bbq_sauce", 0.04),
    ], satiety_factor=0.9),
    mk_recipe("pulled_pork", "Pulled Pork", "grill", "main", [
        comp("pork_shoulder", 0.2, "kg"), comp("bbq_sauce", 0.03), comp("paprika_powder", 0.003, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("pulled_pork_burger", "Pulled Pork Burger", "burger", "main", [
        comp("pork_shoulder", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("bbq_sauce", 0.025),
        comp("cabbage", 0.03, "kg", optional=True, note="Krautsalat-Topping"),
    ], satiety_factor=0.90, popular=True),
    mk_recipe("pulled_chicken", "Pulled Chicken", "grill", "main", [
        comp("chicken_thigh", 0.2, "kg"), comp("bbq_sauce", 0.03),
    ], satiety_factor=0.8),
    mk_recipe("haehnchenbrust", "Hähnchenbrust", "grill", "main", [
        comp("chicken_breast", 0.2, "kg"),
    ], satiety_factor=0.85, popular=True),
    mk_recipe("haehnchenschenkel", "Hähnchenschenkel", "grill", "main", [
        comp("chicken_thigh", 0.22, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("chicken_wings", "Chicken Wings", "grill", "main", [
        comp("chicken_wing", 0.25, "kg"), comp("hot_sauce", 0.02, optional=True),
    ], satiety_factor=0.5),
    mk_recipe("chicken_drumsticks", "Chicken Drumsticks", "grill", "main", [
        comp("chicken_drumstick", 0.25, "kg"),
    ], satiety_factor=0.6),
    mk_recipe("chicken_spiesse", "Chicken Spieße", "grill", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("bell_pepper", 0.05, "kg"), comp("onion", 0.03, "kg"),
    ], satiety_factor=0.7),
    mk_recipe("schaschlik", "Schaschlik", "grill", "main", [
        comp("pork_neck_steak", 0.18, "kg"), comp("bell_pepper", 0.05, "kg"), comp("onion", 0.03, "kg"),
    ], satiety_factor=0.75),
    mk_recipe("grillspiess", "Grillspieß", "grill", "main", [
        comp("pork_neck_steak", 0.15, "kg"), comp("bell_pepper", 0.05, "kg"),
        comp("onion", 0.03, "kg"), comp("zucchini", 0.04, "kg"),
    ], satiety_factor=0.7),
    mk_recipe("cevapcici", "Ćevapčići", "grill", "main", [
        comp("ground_beef", 0.1, "kg"), comp("ground_pork", 0.08, "kg"),
        comp("garlic", 0.005, "kg"), comp("cumin", 0.002, "kg"), comp("paprika_powder", 0.002, "kg"),
    ], satiety_factor=0.75),
    mk_recipe("koefte", "Köfte", "grill", "main", [
        comp("ground_beef", 0.18, "kg"), comp("onion", 0.03, "kg"),
        comp("cumin", 0.002, "kg"), comp("paprika_powder", 0.002, "kg"), comp("parsley", 0.003, "kg"),
    ], satiety_factor=0.75),
    mk_recipe("frikadellen", "Frikadellen", "grill", "main", [
        comp("ground_beef", 0.15, "kg"), comp("onion", 0.02, "kg"),
        comp("eggs", 0.5, "pcs"), comp("breadcrumbs", 0.02, "kg"),
    ], satiety_factor=0.7),
    mk_recipe("mini_frikadellen", "Mini-Frikadellen", "fingerfood", "snack", [
        comp("ground_beef", 0.08, "kg"), comp("onion", 0.01, "kg"),
        comp("eggs", 0.25, "pcs"), comp("breadcrumbs", 0.01, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("lammkotelett", "Lammkotelett", "grill", "main", [
        comp("lamb_chop", 0.22, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("lammspiess", "Lammspieß", "grill", "main", [
        comp("lamb_skewer_meat", 0.15, "kg"), comp("bell_pepper", 0.04, "kg"), comp("onion", 0.03, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("lachsfilet", "Lachsfilet", "grill", "main", [
        comp("salmon_fillet", 0.2, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("garnelenspiess", "Garnelenspieß", "grill", "main", [
        comp("shrimp", 0.12, "kg"), comp("lime", 0.02, "kg"), comp("garlic", 0.003, "kg"),
    ], satiety_factor=0.5),
    mk_recipe("dorade", "Dorade", "grill", "main", [
        comp("dorade", 0.3, "kg"),
    ], satiety_factor=0.75),
    mk_recipe("forelle", "Forelle", "grill", "main", [
        comp("trout", 0.3, "kg"),
    ], satiety_factor=0.75),
    mk_recipe("thunfischsteak", "Thunfischsteak", "grill", "main", [
        comp("tuna_steak", 0.2, "kg"),
    ], satiety_factor=0.85),

    # --- Burger (§15) --------------------------------------------------------
    mk_recipe("classic_burger", "Classic Burger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("onion", 0.02, "kg"), comp("ketchup", 0.01), comp("mustard", 0.005),
    ], satiety_factor=0.9, popular=True),
    mk_recipe("cheeseburger", "Cheeseburger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("onion", 0.02, "kg"), comp("cheddar", 0.02, "kg"),
        comp("ketchup", 0.01), comp("mustard", 0.005),
    ], satiety_factor=0.9, popular=True),
    mk_recipe("bacon_burger", "Bacon Burger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("bacon", 0.03, "kg"), comp("burger_sauce", 0.015),
    ], satiety_factor=0.92),
    mk_recipe("bacon_cheeseburger", "Bacon Cheeseburger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("bacon", 0.03, "kg"), comp("cheddar", 0.02, "kg"),
        comp("burger_sauce", 0.015),
    ], satiety_factor=0.95),
    mk_recipe("double_burger", "Double Burger", "burger", "main", [
        comp("beef_patty", 0.3, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("onion", 0.02, "kg"), comp("burger_sauce", 0.015),
    ], satiety_factor=1.05),
    mk_recipe("double_cheeseburger", "Double Cheeseburger", "burger", "main", [
        comp("beef_patty", 0.3, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("cheddar", 0.04, "kg"), comp("burger_sauce", 0.015),
    ], satiety_factor=1.1),
    mk_recipe("bbq_burger", "BBQ Burger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("cheddar", 0.02, "kg"),
        comp("bbq_sauce", 0.02), comp("fried_onions", 0.02, "kg"),
    ], satiety_factor=0.92),
    mk_recipe("chili_cheese_burger", "Chili Cheese Burger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"),
        comp("chili_cheese_sauce", 0.03), comp("jalapeno", 0.01, "kg"),
    ], satiety_factor=0.92),
    mk_recipe("jalapeno_burger", "Jalapeño Burger", "burger", "main", [
        comp("beef_patty", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("cheddar", 0.02, "kg"),
        comp("jalapeno", 0.015, "kg"), comp("burger_sauce", 0.015),
    ], satiety_factor=0.9),
    mk_recipe("chicken_burger", "Chicken Burger", "burger", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("mayonnaise", 0.015),
    ], satiety_factor=0.85),
    mk_recipe("crispy_chicken_burger", "Crispy Chicken Burger", "burger", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("breadcrumbs", 0.02, "kg"), comp("cooking_oil", 0.02),
        comp("burger_bun", 1, "pcs"), comp("lettuce", 0.02, "kg"), comp("mayonnaise", 0.015),
    ], satiety_factor=0.88),
    mk_recipe("fish_burger", "Fish Burger", "burger", "main", [
        comp("cod", 0.15, "kg"), comp("breadcrumbs", 0.02, "kg"), comp("burger_bun", 1, "pcs"),
        comp("lettuce", 0.02, "kg"), comp("remoulade", 0.02),
    ], satiety_factor=0.8),
    mk_recipe("veggie_burger", "Veggie Burger", "burger", "main", [
        comp("vegetarian_burger_patty", 0.13, "kg"), comp("burger_bun", 1, "pcs"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.03, "kg"), comp("burger_sauce", 0.015),
    ], satiety_factor=0.85, popular=True),
    mk_recipe("vegan_burger", "Vegan Burger", "burger", "main", [
        comp("vegan_burger_patty", 0.13, "kg"), comp("burger_bun", 1, "pcs"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.03, "kg"), comp("vegan_cheese", 0.02, "kg", optional=True),
    ], satiety_factor=0.85),
    mk_recipe("halloumi_burger", "Halloumi Burger", "burger", "main", [
        comp("halloumi", 0.13, "kg"), comp("burger_bun", 1, "pcs"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.03, "kg"), comp("honey_mustard_sauce", 0.015),
    ], satiety_factor=0.7),
    mk_recipe("portobello_burger", "Portobello Burger", "burger", "main", [
        comp("mushroom", 0.15, "kg"), comp("burger_bun", 1, "pcs"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.03, "kg"), comp("aioli", 0.015),
    ], satiety_factor=0.65),

    # --- Vegetarisch / Vegan Grill (§16) --------------------------------------
    mk_recipe("veggie_bratwurst", "Veggie Bratwurst", "veg_grill", "main", [
        comp("vegetarian_sausage", 0.13, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.45),
    mk_recipe("vegane_bratwurst", "Vegane Bratwurst", "veg_grill", "main", [
        comp("vegan_sausage", 0.13, "kg"), comp("bread_roll", 1, "pcs", optional=True),
    ], satiety_factor=0.45),
    mk_recipe("halloumi_grilled", "Halloumi (gegrillt)", "veg_grill", "main", [
        comp("halloumi", 0.15, "kg"),
    ], satiety_factor=0.65, popular=True),
    mk_recipe("grillkaese", "Grillkäse", "veg_grill", "main", [
        comp("halloumi", 0.15, "kg"),
    ], satiety_factor=0.65),
    mk_recipe("halloumi_spiess", "Halloumi-Spieß", "veg_grill", "main", [
        comp("halloumi", 0.12, "kg"), comp("bell_pepper", 0.05, "kg"), comp("zucchini", 0.04, "kg"),
    ], satiety_factor=0.6),
    mk_recipe("gemuesespiess", "Gemüsespieß", "veg_grill", "main", [
        comp("bell_pepper", 0.05, "kg"), comp("zucchini", 0.05, "kg"),
        comp("mushroom", 0.04, "kg"), comp("onion", 0.03, "kg"),
    ], satiety_factor=0.4),
    mk_recipe("tofu_spiess", "Tofu-Spieß", "veg_grill", "main", [
        comp("tofu", 0.13, "kg"), comp("bell_pepper", 0.04, "kg"), comp("onion", 0.03, "kg"),
    ], satiety_factor=0.55),
    mk_recipe("marinierter_tofu", "Marinierter Tofu", "veg_grill", "main", [
        comp("tofu_marinated", 0.15, "kg"),
    ], satiety_factor=0.55),
    mk_recipe("tempeh_grill", "Tempeh", "veg_grill", "main", [
        comp("tempeh", 0.15, "kg"),
    ], satiety_factor=0.6),
    mk_recipe("seitan_steak", "Seitan-Steak", "veg_grill", "main", [
        comp("seitan", 0.15, "kg"),
    ], satiety_factor=0.65),
    mk_recipe("portobello_grill", "Portobello (gegrillt)", "veg_grill", "side", [
        comp("mushroom", 0.15, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.4),
    mk_recipe("maiskolben", "Maiskolben", "veg_grill", "side", [
        comp("corn", 0.2, "kg"), comp("butter", 0.01, "kg", optional=True),
    ], satiety_factor=0.35),
    mk_recipe("gegrillte_aubergine", "Gegrillte Aubergine", "veg_grill", "side", [
        comp("eggplant", 0.15, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("gegrillte_zucchini", "Gegrillte Zucchini", "veg_grill", "side", [
        comp("zucchini", 0.15, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("gegrillte_paprika", "Gegrillte Paprika", "veg_grill", "side", [
        comp("bell_pepper", 0.15, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("gefuellte_paprika", "Gefüllte Paprika", "veg_grill", "main", [
        comp("bell_pepper", 0.2, "kg"), comp("rice", 0.05, "kg"),
        comp("cheddar", 0.02, "kg"), comp("tomato_sauce", 0.03),
    ], satiety_factor=0.6),
    mk_recipe("gefuellte_champignons", "Gefüllte Champignons", "fingerfood", "snack", [
        comp("mushroom", 0.15, "kg"), comp("cream_cheese", 0.03, "kg"),
        comp("garlic", 0.003, "kg"), comp("parsley", 0.002, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("ofenkartoffel", "Ofenkartoffel", "veg_grill", "side", [
        comp("potato", 0.25, "kg"), comp("sour_cream", 0.03), comp("chives", 0.003, "kg"),
    ], satiety_factor=0.55),
    mk_recipe("grillkartoffel", "Grillkartoffel", "veg_grill", "side", [
        comp("potato", 0.22, "kg"), comp("cooking_oil", 0.01), comp("rosemary", 0.002, "kg", optional=True),
    ], satiety_factor=0.5),
    mk_recipe("suesskartoffel_grill", "Süßkartoffel (gegrillt)", "veg_grill", "side", [
        comp("sweet_potato", 0.22, "kg"), comp("cooking_oil", 0.01),
    ], satiety_factor=0.5),
    mk_recipe("grillgemuese", "Grillgemüse", "veg_grill", "side", [
        comp("zucchini", 0.06, "kg"), comp("eggplant", 0.06, "kg"),
        comp("bell_pepper", 0.06, "kg"), comp("onion", 0.04, "kg"), comp("olive_oil", 0.015),
    ], satiety_factor=0.4),

    # --- Party-Hauptgerichte (§17) --------------------------------------------
    mk_recipe("chili_con_carne", "Chili con Carne", "main_dish", "main", [
        comp("ground_beef", 0.15, "kg"), comp("kidney_beans", 0.12, "kg"), comp("tomato_sauce", 0.08),
        comp("onion", 0.03, "kg"), comp("bell_pepper", 0.03, "kg"),
        comp("cumin", 0.002, "kg"), comp("chili_flakes", 0.002, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("chili_sin_carne", "Chili sin Carne", "main_dish", "main", [
        comp("soy_mince", 0.12, "kg"), comp("kidney_beans", 0.12, "kg"), comp("tomato_sauce", 0.08),
        comp("onion", 0.03, "kg"), comp("bell_pepper", 0.03, "kg"),
        comp("cumin", 0.002, "kg"), comp("chili_flakes", 0.002, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("gulasch", "Gulasch", "main_dish", "main", [
        comp("beef_stew_meat", 0.18, "kg"), comp("onion", 0.05, "kg"),
        comp("paprika_powder", 0.003, "kg"), comp("tomato_sauce", 0.04), comp("beef_stock", 0.06),
    ], satiety_factor=0.9),
    mk_recipe("gulaschsuppe", "Gulaschsuppe", "main_dish", "main", [
        comp("beef_stew_meat", 0.1, "kg"), comp("onion", 0.03, "kg"), comp("paprika_powder", 0.003, "kg"),
        comp("beef_stock", 0.2), comp("potato", 0.06, "kg"),
    ], satiety_factor=0.75),
    mk_recipe("kartoffelsuppe", "Kartoffelsuppe", "main_dish", "main", [
        comp("potato", 0.15, "kg"), comp("onion", 0.03, "kg"), comp("cream", 0.03),
        comp("vegetable_stock", 0.2), comp("bacon", 0.02, "kg", optional=True),
    ], satiety_factor=0.6),
    mk_recipe("kaesesuppe", "Käsesuppe", "main_dish", "main", [
        comp("cheddar", 0.06, "kg"), comp("cream", 0.04), comp("vegetable_stock", 0.18), comp("onion", 0.02, "kg"),
    ], satiety_factor=0.55),
    mk_recipe("tomatensuppe", "Tomatensuppe", "main_dish", "main", [
        comp("tomato_sauce", 0.15), comp("cream", 0.02), comp("vegetable_stock", 0.1), comp("basil", 0.002, "kg"),
    ], satiety_factor=0.45),
    mk_recipe("lasagne_bolognese", "Lasagne Bolognese", "main_dish", "main", [
        comp("lasagne_sheets", 0.1, "kg"), comp("ground_beef", 0.15, "kg"), comp("tomato_sauce", 0.1),
        comp("mozzarella", 0.04, "kg"), comp("parmesan", 0.02, "kg"),
        comp("onion", 0.02, "kg"), comp("garlic", 0.003, "kg"),
    ], satiety_factor=0.95),
    mk_recipe("gemueselasagne", "Gemüselasagne", "main_dish", "main", [
        comp("lasagne_sheets", 0.1, "kg"), comp("zucchini", 0.06, "kg"), comp("eggplant", 0.06, "kg"),
        comp("tomato_sauce", 0.1), comp("mozzarella", 0.04, "kg"), comp("parmesan", 0.02, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("vegane_lasagne", "Vegane Lasagne", "main_dish", "main", [
        comp("lasagne_sheets", 0.1, "kg"), comp("soy_mince", 0.1, "kg"), comp("tomato_sauce", 0.1),
        comp("vegan_cheese", 0.04, "kg"), comp("zucchini", 0.04, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("spaghetti_bolognese", "Spaghetti Bolognese", "main_dish", "main", [
        comp("pasta_spaghetti", 0.12, "kg"), comp("ground_beef", 0.13, "kg"), comp("tomato_sauce", 0.1),
        comp("onion", 0.02, "kg"), comp("garlic", 0.003, "kg"), comp("parmesan", 0.015, "kg", optional=True),
    ], satiety_factor=0.9),
    mk_recipe("pasta_arrabbiata", "Pasta Arrabbiata", "main_dish", "main", [
        comp("pasta_penne", 0.12, "kg"), comp("tomato_sauce", 0.1),
        comp("chili_flakes", 0.002, "kg"), comp("garlic", 0.003, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.75),
    mk_recipe("pasta_napoli", "Pasta Napoli", "main_dish", "main", [
        comp("pasta_spaghetti", 0.12, "kg"), comp("tomato_sauce", 0.1),
        comp("basil", 0.003, "kg"), comp("garlic", 0.003, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.75),
    mk_recipe("mac_and_cheese", "Mac and Cheese", "main_dish", "main", [
        comp("macaroni", 0.12, "kg"), comp("cheddar", 0.05, "kg"), comp("milk", 0.08),
        comp("butter", 0.015, "kg"), comp("flour", 0.01, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("chicken_alfredo", "Chicken Alfredo", "main_dish", "main", [
        comp("pasta_spaghetti", 0.12, "kg"), comp("chicken_breast", 0.1, "kg"), comp("cream", 0.06),
        comp("parmesan", 0.02, "kg"), comp("garlic", 0.003, "kg"), comp("butter", 0.01, "kg"),
    ], satiety_factor=0.9),
    mk_recipe("carbonara", "Carbonara", "main_dish", "main", [
        comp("pasta_spaghetti", 0.12, "kg"), comp("bacon", 0.05, "kg"), comp("eggs", 1.2, "pcs"),
        comp("parmesan", 0.02, "kg"), comp("pepper", 0.001, "kg"),
    ], satiety_factor=0.9),
    mk_recipe("pesto_pasta", "Pesto Pasta", "main_dish", "main", [
        comp("pasta_penne", 0.12, "kg"), comp("pesto", 0.04), comp("parmesan", 0.015, "kg", optional=True),
    ], satiety_factor=0.8),
    mk_recipe("chicken_curry", "Chicken Curry", "main_dish", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("curry_paste", 0.02), comp("coconut_milk", 0.08),
        comp("onion", 0.03, "kg"), comp("rice", 0.06, "kg"),
    ], satiety_factor=0.9),
    mk_recipe("thai_curry", "Thai Curry", "main_dish", "main", [
        comp("coconut_milk", 0.1), comp("curry_paste", 0.02), comp("bell_pepper", 0.04, "kg"),
        comp("zucchini", 0.04, "kg"), comp("tofu", 0.06, "kg", optional=True), comp("rice", 0.06, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("veganes_curry", "Veganes Curry", "main_dish", "main", [
        comp("chickpeas", 0.1, "kg"), comp("coconut_milk", 0.1), comp("curry_paste", 0.02),
        comp("bell_pepper", 0.04, "kg"), comp("rice", 0.06, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("butter_chicken", "Butter Chicken", "main_dish", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("tomato_sauce", 0.08), comp("cream", 0.04),
        comp("butter", 0.015, "kg"), comp("garam_masala", 0.003, "kg"), comp("rice", 0.06, "kg", optional=True),
    ], satiety_factor=0.9),
    mk_recipe("chicken_tikka_masala", "Chicken Tikka Masala", "main_dish", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("tomato_sauce", 0.08), comp("cream", 0.04),
        comp("garam_masala", 0.003, "kg"), comp("yogurt", 0.03), comp("rice", 0.06, "kg", optional=True),
    ], satiety_factor=0.9),
    mk_recipe("taco_bar", "Taco Bar", "main_dish", "main", [
        comp("taco_shell", 2, "pcs"), comp("ground_beef", 0.1, "kg"), comp("cheddar", 0.02, "kg"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.03, "kg"), comp("salsa_mild", 0.02), comp("sour_cream", 0.02),
    ], satiety_factor=0.85),
    mk_recipe("beef_tacos", "Beef Tacos", "main_dish", "main", [
        comp("taco_shell", 2, "pcs"), comp("ground_beef", 0.1, "kg"), comp("cheddar", 0.02, "kg"),
        comp("lettuce", 0.02, "kg"), comp("salsa_mild", 0.02),
    ], satiety_factor=0.8),
    mk_recipe("chicken_tacos", "Chicken Tacos", "main_dish", "main", [
        comp("taco_shell", 2, "pcs"), comp("chicken_breast", 0.1, "kg"), comp("cheddar", 0.02, "kg"),
        comp("lettuce", 0.02, "kg"), comp("salsa_mild", 0.02),
    ], satiety_factor=0.8),
    mk_recipe("veggie_tacos", "Veggie Tacos", "main_dish", "main", [
        comp("taco_shell", 2, "pcs"), comp("kidney_beans", 0.08, "kg"), comp("cheddar", 0.02, "kg"),
        comp("lettuce", 0.02, "kg"), comp("salsa_mild", 0.02),
    ], satiety_factor=0.75),
    mk_recipe("vegan_tacos", "Vegan Tacos", "main_dish", "main", [
        comp("taco_shell", 2, "pcs"), comp("kidney_beans", 0.08, "kg"), comp("vegan_cheese", 0.02, "kg"),
        comp("lettuce", 0.02, "kg"), comp("guacamole", 0.02),
    ], satiety_factor=0.75),
    mk_recipe("burritos", "Burritos", "main_dish", "main", [
        comp("tortilla_wrap", 1, "pcs"), comp("rice", 0.05, "kg"), comp("kidney_beans", 0.06, "kg"),
        comp("ground_beef", 0.1, "kg"), comp("cheddar", 0.02, "kg"), comp("salsa_mild", 0.02), comp("sour_cream", 0.02),
    ], satiety_factor=0.9),
    mk_recipe("veggie_burritos", "Veggie Burritos", "main_dish", "main", [
        comp("tortilla_wrap", 1, "pcs"), comp("rice", 0.05, "kg"), comp("kidney_beans", 0.08, "kg"),
        comp("cheddar", 0.02, "kg"), comp("salsa_mild", 0.02),
    ], satiety_factor=0.8),
    mk_recipe("wraps", "Wraps", "main_dish", "main", [
        comp("tortilla_wrap", 1, "pcs"), comp("chicken_breast", 0.08, "kg"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.02, "kg"), comp("burger_sauce", 0.015),
    ], satiety_factor=0.7),
    mk_recipe("chicken_wraps", "Chicken Wraps", "main_dish", "main", [
        comp("tortilla_wrap", 1, "pcs"), comp("chicken_breast", 0.09, "kg"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.02, "kg"), comp("mayonnaise", 0.015),
    ], satiety_factor=0.7),
    mk_recipe("veggie_wraps", "Veggie Wraps", "main_dish", "main", [
        comp("tortilla_wrap", 1, "pcs"), comp("halloumi", 0.08, "kg"),
        comp("lettuce", 0.02, "kg"), comp("tomato", 0.02, "kg"), comp("hummus", 0.02),
    ], satiety_factor=0.65),
    mk_recipe("quesadillas", "Quesadillas", "main_dish", "main", [
        comp("tortilla_wrap", 1, "pcs"), comp("cheddar", 0.04, "kg"), comp("bell_pepper", 0.03, "kg"),
        comp("chicken_breast", 0.06, "kg", optional=True),
    ], satiety_factor=0.7),
    mk_recipe("pizza_margherita", "Pizza Margherita", "main_dish", "main", [
        comp("pizza_dough", 0.2, "kg"), comp("tomato_sauce", 0.06), comp("mozzarella", 0.06, "kg"),
        comp("basil", 0.002, "kg"),
    ], satiety_factor=0.85, popular=True),
    mk_recipe("pizza_salami", "Pizza Salami", "main_dish", "main", [
        comp("pizza_dough", 0.2, "kg"), comp("tomato_sauce", 0.06), comp("mozzarella", 0.06, "kg"),
        comp("salami", 0.04, "kg"),
    ], satiety_factor=0.9),
    mk_recipe("pizza_schinken", "Pizza Schinken", "main_dish", "main", [
        comp("pizza_dough", 0.2, "kg"), comp("tomato_sauce", 0.06), comp("mozzarella", 0.06, "kg"),
        comp("ham", 0.04, "kg"),
    ], satiety_factor=0.85),
    mk_recipe("pizza_funghi", "Pizza Funghi", "main_dish", "main", [
        comp("pizza_dough", 0.2, "kg"), comp("tomato_sauce", 0.06), comp("mozzarella", 0.06, "kg"),
        comp("mushroom", 0.05, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("pizza_vegetaria", "Pizza Vegetaria", "main_dish", "main", [
        comp("pizza_dough", 0.2, "kg"), comp("tomato_sauce", 0.06), comp("mozzarella", 0.06, "kg"),
        comp("bell_pepper", 0.03, "kg"), comp("zucchini", 0.03, "kg"), comp("olives", 0.02, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("pizza_vegan", "Pizza Vegan", "main_dish", "main", [
        comp("pizza_dough", 0.2, "kg"), comp("tomato_sauce", 0.06), comp("vegan_cheese", 0.06, "kg"),
        comp("bell_pepper", 0.03, "kg"), comp("mushroom", 0.03, "kg"),
    ], satiety_factor=0.8),
    mk_recipe("flammkuchen_klassisch", "Flammkuchen klassisch", "main_dish", "main", [
        comp("pizza_dough", 0.15, "kg"), comp("sour_cream", 0.04), comp("bacon", 0.03, "kg"), comp("onion", 0.03, "kg"),
    ], satiety_factor=0.7),
    mk_recipe("flammkuchen_vegetarisch", "Flammkuchen vegetarisch", "main_dish", "main", [
        comp("pizza_dough", 0.15, "kg"), comp("sour_cream", 0.04), comp("onion", 0.03, "kg"), comp("mushroom", 0.04, "kg"),
    ], satiety_factor=0.65),
    mk_recipe("loaded_fries", "Loaded Fries", "main_dish", "side", [
        comp("potato", 0.2, "kg"), comp("cooking_oil", 0.02), comp("chili_cheese_sauce", 0.04),
        comp("bacon", 0.02, "kg", optional=True), comp("fried_onions", 0.02, "kg"), comp("sour_cream", 0.02),
    ], satiety_factor=0.75),
    mk_recipe("loaded_nachos", "Loaded Nachos", "main_dish", "snack", [
        comp("tortilla_chips", 0.1, "kg"), comp("chili_cheese_sauce", 0.05), comp("jalapeno", 0.01, "kg"),
        comp("sour_cream", 0.02), comp("salsa_mild", 0.02), comp("guacamole", 0.03),
    ], satiety_factor=0.7),

    # --- Fingerfood (§18) ------------------------------------------------------
    mk_recipe("chicken_nuggets", "Chicken Nuggets", "fingerfood", "snack", [
        comp("chicken_breast", 0.12, "kg"), comp("breadcrumbs", 0.02, "kg"),
        comp("eggs", 0.5, "pcs"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.4),
    mk_recipe("mini_schnitzel", "Mini-Schnitzel", "fingerfood", "snack", [
        comp("chicken_breast", 0.12, "kg"), comp("breadcrumbs", 0.02, "kg"),
        comp("eggs", 0.5, "pcs"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.4),
    mk_recipe("mozzarella_sticks", "Mozzarella Sticks", "fingerfood", "snack", [
        comp("mozzarella", 0.1, "kg"), comp("breadcrumbs", 0.02, "kg"),
        comp("eggs", 0.5, "pcs"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.3),
    mk_recipe("onion_rings", "Onion Rings", "fingerfood", "snack", [
        comp("onion", 0.1, "kg"), comp("flour", 0.03, "kg"), comp("breadcrumbs", 0.02, "kg"), comp("cooking_oil", 0.03),
    ], satiety_factor=0.25),
    mk_recipe("fruehlingsrollen", "Frühlingsrollen", "fingerfood", "snack", [
        comp("spring_roll_wrapper", 0.06, "kg"), comp("cabbage", 0.06, "kg"),
        comp("carrot", 0.03, "kg"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.3),
    mk_recipe("mini_fruehlingsrollen", "Mini-Frühlingsrollen", "fingerfood", "snack", [
        comp("spring_roll_wrapper", 0.03, "kg"), comp("cabbage", 0.03, "kg"),
        comp("carrot", 0.015, "kg"), comp("cooking_oil", 0.015),
    ], satiety_factor=0.2),
    mk_recipe("samosas", "Samosas", "fingerfood", "snack", [
        comp("puff_pastry", 0.06, "kg"), comp("potato", 0.06, "kg"),
        comp("peas", 0.02, "kg"), comp("garam_masala", 0.002, "kg"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.3),
    mk_recipe("falafel", "Falafel", "fingerfood", "snack", [
        comp("chickpeas", 0.1, "kg"), comp("cilantro", 0.003, "kg"),
        comp("cumin", 0.002, "kg"), comp("garlic", 0.003, "kg"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.4),
    mk_recipe("mini_pizzen", "Mini-Pizzen", "fingerfood", "snack", [
        comp("pizza_dough", 0.08, "kg"), comp("tomato_sauce", 0.02), comp("mozzarella", 0.03, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("pizzaschnecken", "Pizzaschnecken", "fingerfood", "snack", [
        comp("puff_pastry", 0.06, "kg"), comp("tomato_sauce", 0.02), comp("cheddar", 0.03, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("blaetterteigschnecken", "Blätterteigschnecken", "fingerfood", "snack", [
        comp("puff_pastry", 0.06, "kg"), comp("ham", 0.02, "kg"), comp("cheddar", 0.02, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("kaesegebaeck", "Käsegebäck", "fingerfood", "snack", [
        comp("puff_pastry", 0.06, "kg"), comp("gouda", 0.03, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("mini_quiche", "Mini-Quiche", "fingerfood", "snack", [
        comp("puff_pastry", 0.05, "kg"), comp("eggs", 0.5, "pcs"), comp("cream", 0.02),
        comp("bacon", 0.02, "kg", optional=True), comp("cheddar", 0.02, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("mini_wraps", "Mini-Wraps", "fingerfood", "snack", [
        comp("tortilla_wrap", 0.5, "pcs"), comp("chicken_breast", 0.04, "kg"),
        comp("lettuce", 0.01, "kg"), comp("burger_sauce", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("sandwiches", "Sandwiches", "fingerfood", "snack", [
        comp("toast_bread", 2, "pcs"), comp("ham", 0.03, "kg"), comp("cheddar", 0.02, "kg"),
        comp("lettuce", 0.01, "kg"), comp("tomato", 0.02, "kg"), comp("mayonnaise", 0.01),
    ], satiety_factor=0.55),
    mk_recipe("club_sandwiches", "Club Sandwiches", "fingerfood", "snack", [
        comp("toast_bread", 3, "pcs"), comp("chicken_breast", 0.06, "kg"), comp("bacon", 0.02, "kg"),
        comp("lettuce", 0.01, "kg"), comp("tomato", 0.02, "kg"), comp("mayonnaise", 0.015),
    ], satiety_factor=0.65),
    mk_recipe("bruschetta", "Bruschetta", "fingerfood", "snack", [
        comp("baguette", 0.06, "kg"), comp("tomato", 0.04, "kg"),
        comp("basil", 0.002, "kg"), comp("garlic", 0.002, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("crostini", "Crostini", "fingerfood", "snack", [
        comp("baguette", 0.05, "kg"), comp("cream_cheese", 0.03, "kg"), comp("dill", 0.002, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("caprese_spiesse", "Caprese-Spieße", "fingerfood", "snack", [
        comp("tomato", 0.04, "kg"), comp("mozzarella", 0.04, "kg"), comp("basil", 0.002, "kg"),
    ], satiety_factor=0.25, is_vegan=False),
    mk_recipe("kaese_trauben_spiesse", "Käse-Trauben-Spieße", "fingerfood", "snack", [
        comp("cheddar", 0.03, "kg"), comp("grape", 0.03, "kg"),
    ], satiety_factor=0.2),
    mk_recipe("antipasti_spiesse", "Antipasti-Spieße", "fingerfood", "snack", [
        comp("olives", 0.02, "kg"), comp("mozzarella", 0.03, "kg"), comp("salami", 0.02, "kg"), comp("tomato", 0.02, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("gemuesesticks_dip", "Gemüsesticks mit Dip", "fingerfood", "snack", [
        comp("carrot", 0.04, "kg"), comp("cucumber", 0.04, "kg"),
        comp("bell_pepper", 0.03, "kg"), comp("hummus", 0.03),
    ], satiety_factor=0.2),
    mk_recipe("datteln_im_speckmantel", "Datteln im Speckmantel", "fingerfood", "snack", [
        comp("dates", 0.06, "kg"), comp("bacon", 0.03, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("jalapeno_poppers", "Jalapeño Poppers", "fingerfood", "snack", [
        comp("jalapeno", 0.06, "kg"), comp("cream_cheese", 0.04, "kg"),
        comp("bacon", 0.02, "kg"), comp("breadcrumbs", 0.01, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("chicken_satay", "Chicken Satay", "fingerfood", "snack", [
        comp("chicken_breast", 0.1, "kg"), comp("peanut_sauce", 0.02),
    ], satiety_factor=0.4),

    # --- Beilagen (§19) ---------------------------------------------------------
    mk_recipe("pommes", "Pommes", "side", "side", [
        comp("potato", 0.2, "kg"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.4, popular=True),
    mk_recipe("suesskartoffelpommes", "Süßkartoffelpommes", "side", "side", [
        comp("sweet_potato", 0.2, "kg"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.4),
    mk_recipe("kartoffelwedges", "Kartoffelwedges", "side", "side", [
        comp("potato", 0.22, "kg"), comp("cooking_oil", 0.02), comp("paprika_powder", 0.002, "kg"),
    ], satiety_factor=0.45),
    mk_recipe("country_potatoes", "Country Potatoes", "side", "side", [
        comp("potato", 0.22, "kg"), comp("cooking_oil", 0.02),
        comp("paprika_powder", 0.002, "kg"), comp("oregano", 0.001, "kg"),
    ], satiety_factor=0.45),
    mk_recipe("bratkartoffeln", "Bratkartoffeln", "side", "side", [
        comp("potato", 0.2, "kg"), comp("bacon", 0.03, "kg", optional=True),
        comp("onion", 0.03, "kg"), comp("cooking_oil", 0.015),
    ], satiety_factor=0.5),
    mk_recipe("kartoffelpueree", "Kartoffelpüree", "side", "side", [
        comp("potato", 0.22, "kg"), comp("milk", 0.04), comp("butter", 0.015, "kg"),
    ], satiety_factor=0.5),
    mk_recipe("reis", "Reis", "side", "side", [
        comp("rice", 0.08, "kg"), comp("vegetable_stock", 0.1, optional=True),
    ], satiety_factor=0.35),
    mk_recipe("basmati_reis", "Basmati-Reis", "side", "side", [
        comp("basmati_rice", 0.08, "kg"), comp("vegetable_stock", 0.1, optional=True),
    ], satiety_factor=0.35),
    mk_recipe("couscous_side", "Couscous", "side", "side", [
        comp("couscous", 0.07, "kg"), comp("vegetable_stock", 0.08), comp("olive_oil", 0.005),
    ], satiety_factor=0.35),
    mk_recipe("bulgur_side", "Bulgur", "side", "side", [
        comp("bulgur", 0.07, "kg"), comp("vegetable_stock", 0.08),
    ], satiety_factor=0.35),
    mk_recipe("quinoa_side", "Quinoa", "side", "side", [
        comp("quinoa", 0.07, "kg"), comp("vegetable_stock", 0.08),
    ], satiety_factor=0.35),
    mk_recipe("ratatouille", "Ratatouille", "side", "side", [
        comp("zucchini", 0.05, "kg"), comp("eggplant", 0.05, "kg"),
        comp("tomato", 0.05, "kg"), comp("bell_pepper", 0.05, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("bohnen", "Bohnen", "side", "side", [
        comp("green_beans", 0.15, "kg"), comp("butter", 0.01, "kg", optional=True),
    ], satiety_factor=0.3),
    mk_recipe("baked_beans", "Baked Beans", "side", "side", [
        comp("kidney_beans", 0.15, "kg"), comp("tomato_sauce", 0.04),
    ], satiety_factor=0.35),
    mk_recipe("knoblauchbrot", "Knoblauchbrot", "side", "side", [
        comp("baguette", 0.1, "kg"), comp("garlic_butter", 0.02, "kg"),
    ], satiety_factor=0.4, popular=True),

    # --- Salate (§20) -------------------------------------------------------
    mk_recipe("kartoffelsalat", "Kartoffelsalat", "salad", "salad", [
        comp("potato", 0.15, "kg"), comp("mayonnaise", 0.03), comp("onion", 0.02, "kg"),
        comp("mustard", 0.005), comp("eggs", 0.3, "pcs", optional=True),
    ], satiety_factor=0.4, popular=True),
    mk_recipe("nudelsalat", "Nudelsalat", "salad", "salad", [
        comp("pasta_penne", 0.1, "kg"), comp("mayonnaise", 0.03), comp("bell_pepper", 0.03, "kg"),
        comp("corn", 0.03, "kg"), comp("onion", 0.02, "kg"),
    ], satiety_factor=0.4, popular=True),
    mk_recipe("gruener_salat", "Grüner Salat", "salad", "salad", [
        comp("lettuce", 0.08, "kg"), comp("vinaigrette", 0.02),
    ], satiety_factor=0.2),
    mk_recipe("gemischter_salat", "Gemischter Salat", "salad", "salad", [
        comp("mixed_greens", 0.08, "kg"), comp("tomato", 0.03, "kg"), comp("cucumber", 0.03, "kg"),
        comp("vinaigrette", 0.02),
    ], satiety_factor=0.25),
    mk_recipe("gurkensalat", "Gurkensalat", "salad", "salad", [
        comp("cucumber", 0.1, "kg"), comp("sour_cream", 0.02), comp("dill", 0.002, "kg"),
    ], satiety_factor=0.2),
    mk_recipe("tomatensalat", "Tomatensalat", "salad", "salad", [
        comp("tomato", 0.1, "kg"), comp("red_onion", 0.02, "kg"), comp("olive_oil", 0.01), comp("basil", 0.002, "kg"),
    ], satiety_factor=0.2),
    mk_recipe("tomate_mozzarella", "Tomate Mozzarella", "salad", "salad", [
        comp("tomato", 0.08, "kg"), comp("mozzarella", 0.06, "kg"), comp("basil", 0.002, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("caprese", "Caprese", "salad", "salad", [
        comp("tomato", 0.08, "kg"), comp("mozzarella", 0.06, "kg"), comp("basil", 0.002, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("coleslaw", "Coleslaw", "salad", "salad", [
        comp("cabbage", 0.1, "kg"), comp("carrot", 0.02, "kg"), comp("mayonnaise", 0.02),
    ], satiety_factor=0.25),
    mk_recipe("krautsalat", "Krautsalat", "salad", "salad", [
        comp("cabbage", 0.1, "kg"), comp("vinaigrette", 0.02),
    ], satiety_factor=0.2),
    mk_recipe("couscoussalat", "Couscoussalat", "salad", "salad", [
        comp("couscous", 0.07, "kg"), comp("tomato", 0.03, "kg"), comp("cucumber", 0.03, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("bulgursalat", "Bulgursalat", "salad", "salad", [
        comp("bulgur", 0.07, "kg"), comp("tomato", 0.03, "kg"), comp("parsley", 0.003, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("taboule", "Taboulé", "salad", "salad", [
        comp("bulgur", 0.05, "kg"), comp("parsley", 0.01, "kg"),
        comp("tomato", 0.04, "kg"), comp("lemon_juice_fresh", 0.01), comp("olive_oil", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("griechischer_salat", "Griechischer Salat", "salad", "salad", [
        comp("cucumber", 0.05, "kg"), comp("tomato", 0.05, "kg"), comp("feta", 0.04, "kg"),
        comp("olives", 0.02, "kg"), comp("red_onion", 0.02, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("caesar_salad", "Caesar Salad", "salad", "salad", [
        comp("romaine_lettuce", 0.08, "kg"), comp("parmesan", 0.02, "kg"), comp("croutons", 0.02, "kg"),
        comp("caesar_dressing", 0.03), comp("chicken_breast", 0.06, "kg", optional=True),
    ], satiety_factor=0.55),
    mk_recipe("rucolasalat", "Rucolasalat", "salad", "salad", [
        comp("arugula", 0.06, "kg"), comp("parmesan", 0.015, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.2),
    mk_recipe("bohnensalat", "Bohnensalat", "salad", "salad", [
        comp("green_beans", 0.1, "kg"), comp("red_onion", 0.02, "kg"), comp("vinaigrette", 0.02),
    ], satiety_factor=0.25),
    mk_recipe("reissalat", "Reissalat", "salad", "salad", [
        comp("rice", 0.06, "kg"), comp("bell_pepper", 0.03, "kg"), comp("corn", 0.03, "kg"), comp("vinaigrette", 0.02),
    ], satiety_factor=0.35),
    mk_recipe("farmersalat", "Farmersalat", "salad", "salad", [
        comp("mixed_greens", 0.06, "kg"), comp("ham", 0.03, "kg"), comp("gouda", 0.03, "kg"),
        comp("eggs", 0.3, "pcs"), comp("corn", 0.02, "kg"),
    ], satiety_factor=0.4),
    mk_recipe("maissalat", "Maissalat", "salad", "salad", [
        comp("corn", 0.1, "kg"), comp("bell_pepper", 0.03, "kg"), comp("red_onion", 0.02, "kg"), comp("mayonnaise", 0.015),
    ], satiety_factor=0.25),
    mk_recipe("linsensalat", "Linsensalat", "salad", "salad", [
        comp("lentils", 0.08, "kg"), comp("red_onion", 0.02, "kg"), comp("vinaigrette", 0.02),
    ], satiety_factor=0.35),
    mk_recipe("kichererbsensalat", "Kichererbsensalat", "salad", "salad", [
        comp("chickpeas", 0.08, "kg"), comp("tomato", 0.03, "kg"), comp("red_onion", 0.02, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("avocadosalat", "Avocadosalat", "salad", "salad", [
        comp("avocado", 0.08, "kg"), comp("tomato", 0.04, "kg"), comp("red_onion", 0.02, "kg"), comp("lime_juice_fresh", 0.01),
    ], satiety_factor=0.3),
    mk_recipe("brotsalat", "Brotsalat", "salad", "salad", [
        comp("ciabatta", 0.06, "kg"), comp("tomato", 0.05, "kg"),
        comp("cucumber", 0.03, "kg"), comp("red_onion", 0.02, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.35),
    mk_recipe("tortellinisalat", "Tortellinisalat", "salad", "salad", [
        comp("tortellini", 0.1, "kg"), comp("tomato", 0.03, "kg"), comp("pesto", 0.02),
    ], satiety_factor=0.4),
    mk_recipe("mediterraner_nudelsalat", "Mediterraner Nudelsalat", "salad", "salad", [
        comp("pasta_penne", 0.1, "kg"), comp("feta", 0.03, "kg"), comp("olives", 0.02, "kg"),
        comp("tomato", 0.03, "kg"), comp("olive_oil", 0.01),
    ], satiety_factor=0.4),

    # --- Desserts (§23) -------------------------------------------------------
    mk_recipe("brownies", "Brownies", "dessert", "dessert", [
        comp("flour", 0.02, "kg"), comp("cocoa_powder", 0.01, "kg"), comp("butter", 0.02, "kg"),
        comp("eggs", 0.3, "pcs"), comp("sugar", 0.02, "kg"), comp("chocolate", 0.015, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("blondies", "Blondies", "dessert", "dessert", [
        comp("flour", 0.02, "kg"), comp("butter", 0.02, "kg"), comp("eggs", 0.3, "pcs"),
        comp("sugar", 0.02, "kg"), comp("vanilla_extract", 0.002),
    ], satiety_factor=0.3),
    mk_recipe("muffins", "Muffins", "dessert", "dessert", [
        comp("flour", 0.02, "kg"), comp("eggs", 0.3, "pcs"), comp("sugar", 0.015, "kg"),
        comp("butter", 0.015, "kg"), comp("milk", 0.02), comp("baking_powder", 0.002, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("schokomuffins", "Schokomuffins", "dessert", "dessert", [
        comp("flour", 0.02, "kg"), comp("eggs", 0.3, "pcs"), comp("sugar", 0.015, "kg"),
        comp("butter", 0.015, "kg"), comp("milk", 0.02), comp("baking_powder", 0.002, "kg"), comp("cocoa_powder", 0.01, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("blaubeermuffins", "Blaubeermuffins", "dessert", "dessert", [
        comp("flour", 0.02, "kg"), comp("eggs", 0.3, "pcs"), comp("sugar", 0.015, "kg"),
        comp("butter", 0.015, "kg"), comp("milk", 0.02), comp("baking_powder", 0.002, "kg"), comp("blueberry", 0.02, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("cookies", "Cookies", "dessert", "dessert", [
        comp("flour", 0.015, "kg"), comp("butter", 0.01, "kg"), comp("sugar", 0.01, "kg"), comp("eggs", 0.2, "pcs"),
    ], satiety_factor=0.2),
    mk_recipe("chocolate_chip_cookies", "Chocolate Chip Cookies", "dessert", "dessert", [
        comp("flour", 0.015, "kg"), comp("butter", 0.01, "kg"), comp("sugar", 0.01, "kg"),
        comp("eggs", 0.2, "pcs"), comp("chocolate", 0.01, "kg"),
    ], satiety_factor=0.2),
    mk_recipe("donuts", "Donuts", "dessert", "dessert", [
        comp("flour", 0.02, "kg"), comp("sugar", 0.01, "kg"), comp("eggs", 0.2, "pcs"),
        comp("milk", 0.02), comp("cooking_oil", 0.02), comp("powdered_sugar", 0.005, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("cupcakes", "Cupcakes", "dessert", "dessert", [
        comp("flour", 0.015, "kg"), comp("eggs", 0.25, "pcs"), comp("sugar", 0.015, "kg"),
        comp("butter", 0.015, "kg"), comp("frosting", 0.015, "kg"),
    ], satiety_factor=0.25),
    mk_recipe("kaesekuchen", "Käsekuchen", "dessert", "dessert", [
        comp("cream_cheese", 0.08, "kg"), comp("biscuit_base", 0.03, "kg"),
        comp("eggs", 0.4, "pcs"), comp("sugar", 0.02, "kg"),
    ], satiety_factor=0.4),
    mk_recipe("schokokuchen", "Schokokuchen", "dessert", "dessert", [
        comp("flour", 0.03, "kg"), comp("cocoa_powder", 0.015, "kg"), comp("eggs", 0.4, "pcs"),
        comp("sugar", 0.03, "kg"), comp("butter", 0.02, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("marmorkuchen", "Marmorkuchen", "dessert", "dessert", [
        comp("flour", 0.03, "kg"), comp("eggs", 0.4, "pcs"), comp("sugar", 0.03, "kg"),
        comp("butter", 0.02, "kg"), comp("cocoa_powder", 0.008, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("apfelkuchen", "Apfelkuchen", "dessert", "dessert", [
        comp("flour", 0.03, "kg"), comp("apple", 0.08, "kg"), comp("eggs", 0.4, "pcs"),
        comp("sugar", 0.02, "kg"), comp("butter", 0.02, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("zitronenkuchen", "Zitronenkuchen", "dessert", "dessert", [
        comp("flour", 0.03, "kg"), comp("lemon", 0.03, "kg"), comp("eggs", 0.4, "pcs"),
        comp("sugar", 0.03, "kg"), comp("butter", 0.02, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("blechkuchen", "Blechkuchen", "dessert", "dessert", [
        comp("flour", 0.03, "kg"), comp("eggs", 0.4, "pcs"), comp("sugar", 0.03, "kg"),
        comp("butter", 0.02, "kg"), comp("mixed_berries", 0.03, "kg"),
    ], satiety_factor=0.35),
    mk_recipe("tiramisu", "Tiramisu", "dessert", "dessert", [
        comp("mascarpone", 0.06, "kg"), comp("biscuit_base", 0.03, "kg"), comp("espresso", 0.02),
        comp("cocoa_powder", 0.005, "kg"), comp("eggs", 0.3, "pcs"), comp("sugar", 0.015, "kg"),
    ], satiety_factor=0.4),
    mk_recipe("panna_cotta", "Panna Cotta", "dessert", "dessert", [
        comp("cream", 0.08), comp("sugar", 0.01, "kg"), comp("gelatin", 0.003, "kg"), comp("vanilla_extract", 0.002),
    ], satiety_factor=0.3),
    mk_recipe("mousse_au_chocolat", "Mousse au Chocolat", "dessert", "dessert", [
        comp("chocolate", 0.04, "kg"), comp("cream", 0.05), comp("eggs", 0.4, "pcs"), comp("sugar", 0.01, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("vanillepudding_dessert", "Vanillepudding", "dessert", "dessert", [
        comp("pudding_vanilla", 0.1, "kg"), comp("milk", 0.08),
    ], satiety_factor=0.25),
    mk_recipe("schokopudding_dessert", "Schokopudding", "dessert", "dessert", [
        comp("pudding_chocolate", 0.1, "kg"), comp("milk", 0.08),
    ], satiety_factor=0.25),
    mk_recipe("obstsalat", "Obstsalat", "dessert", "dessert", [
        comp("apple", 0.04, "kg"), comp("banana", 0.04, "kg"), comp("grape", 0.03, "kg"),
        comp("strawberry", 0.03, "kg"), comp("orange", 0.03, "kg"),
    ], satiety_factor=0.2),
    mk_recipe("obstplatte", "Obstplatte", "dessert", "dessert", [
        comp("watermelon", 0.08, "kg"), comp("grape", 0.03, "kg"),
        comp("strawberry", 0.03, "kg"), comp("pineapple", 0.04, "kg"),
    ], satiety_factor=0.2),
    mk_recipe("cheesecake_im_glas", "Cheesecake im Glas", "dessert", "dessert", [
        comp("cream_cheese", 0.05, "kg"), comp("biscuit_base", 0.02, "kg"), comp("mixed_berries", 0.03, "kg"),
    ], satiety_factor=0.3),
    mk_recipe("dessert_im_glas", "Dessert im Glas", "dessert", "dessert", [
        comp("pudding_vanilla", 0.06, "kg"), comp("biscuit_base", 0.02, "kg"), comp("mixed_berries", 0.03, "kg"),
    ], satiety_factor=0.3),
]

# --- Geo-Kultur-Speisen (Geo-/Kultur-Kontext-Spec §4/§6) ------------------------
# Authentische, gut belegte Gerichte für Indien, Peru, Dänemark, Japan und USA.
# Butter Chicken, Chicken Curry, Chicken Tikka Masala und Samosas existieren
# bereits im Katalog oben (main_dish-Sektion) und werden NICHT erneut angelegt.
FOOD_RAW.extend([
    # --- Indien ---------------------------------------------------------------
    mk_recipe("chicken_biryani", "Chicken Biryani", "main_dish", "main", [
        comp("chicken_thigh", 0.15, "kg"), comp("basmati_rice", 0.08, "kg"), comp("onion", 0.03, "kg"),
        comp("garam_masala", 0.003, "kg"), comp("yogurt", 0.03), comp("cardamom", 0.001, "kg", optional=True),
        comp("cilantro", 0.003, "kg", optional=True),
    ], tags=["main", "rice", "spicy_food", "poultry", "traditional", "festive", "sharing"]),
    mk_recipe("palak_paneer", "Palak Paneer", "main_dish", "main", [
        comp("spinach", 0.15, "kg"), comp("paneer", 0.1, "kg"), comp("cream", 0.02),
        comp("garam_masala", 0.002, "kg"), comp("garlic", 0.003, "kg"), comp("cooking_oil", 0.01),
    ], tags=["main", "vegetarian", "vegetable", "spicy_food", "traditional"]),
    mk_recipe("chana_masala", "Chana Masala", "main_dish", "main", [
        comp("chickpeas", 0.15, "kg"), comp("tomato", 0.06, "kg"), comp("onion", 0.03, "kg"),
        comp("garam_masala", 0.002, "kg"), comp("cumin", 0.002, "kg"), comp("ginger", 0.002, "kg"),
        comp("garlic", 0.002, "kg"), comp("cooking_oil", 0.01),
    ], tags=["main", "vegan", "vegetarian", "spicy_food", "comfort_food"]),
    mk_recipe("naan", "Naan", "side", "side", [
        comp("naan_bread", 1, "pcs"), comp("butter", 0.005, "kg"),
    ], tags=["side", "bread", "vegetarian", "traditional"]),
    mk_recipe("raita", "Raita", "side", "side", [
        comp("yogurt", 0.08), comp("cucumber", 0.04, "kg"), comp("cumin", 0.001, "kg"),
        comp("mint", 0.002, "kg", optional=True),
    ], satiety_factor=0.3, tags=["side", "vegetarian", "dip", "fresh", "traditional"]),
    mk_recipe("vegetable_pakora", "Gemüse-Pakora", "fingerfood", "snack", [
        comp("chickpea_flour", 0.05, "kg"), comp("cauliflower", 0.06, "kg"), comp("onion", 0.03, "kg"),
        comp("cooking_oil", 0.03), comp("chili_flakes", 0.001, "kg"), comp("cumin", 0.001, "kg"),
    ], satiety_factor=0.4, tags=["fingerfood_food", "vegan", "vegetarian", "spicy_food", "fried_food", "shareable"]),
    mk_recipe("gulab_jamun", "Gulab Jamun", "dessert", "dessert", [
        comp("milk", 0.04), comp("flour", 0.02, "kg"), comp("cane_sugar_syrup", 0.04),
        comp("cardamom", 0.001, "kg"), comp("cooking_oil", 0.02),
    ], satiety_factor=0.3, tags=["dessert", "vegetarian", "sweet_food", "traditional", "festive"]),
    mk_recipe("aloo_gobi", "Aloo Gobi", "main_dish", "side", [
        comp("potato", 0.12, "kg"), comp("cauliflower", 0.12, "kg"), comp("cumin", 0.002, "kg"),
        comp("garam_masala", 0.002, "kg"), comp("cooking_oil", 0.015), comp("cilantro", 0.003, "kg", optional=True),
    ], tags=["side", "vegan", "vegetarian", "spicy_food", "vegetable"]),
    mk_recipe("dal_tadka", "Dal Tadka", "main_dish", "side", [
        comp("lentils", 0.12, "kg"), comp("cumin", 0.002, "kg"), comp("garlic", 0.003, "kg"),
        comp("onion", 0.02, "kg"), comp("tomato", 0.03, "kg"), comp("cooking_oil", 0.01),
        comp("garam_masala", 0.001, "kg"),
    ], tags=["side", "vegan", "vegetarian", "spicy_food", "comfort_food"]),

    # --- Peru -------------------------------------------------------------------
    mk_recipe("ceviche", "Ceviche", "main_dish", "main", [
        comp("cod", 0.15, "kg"), comp("lime_juice_fresh", 0.05), comp("red_onion", 0.03, "kg"),
        comp("cilantro", 0.003, "kg"), comp("aji_amarillo", 0.01), comp("sweet_potato", 0.05, "kg", optional=True),
    ], satiety_factor=0.8, tags=["main", "fish", "seafood", "fresh", "spicy_food"]),
    mk_recipe("lomo_saltado", "Lomo Saltado", "main_dish", "main", [
        comp("beef_steak_rump", 0.18, "kg"), comp("red_onion", 0.04, "kg"), comp("tomato", 0.05, "kg"),
        comp("soy_sauce", 0.01), comp("potato", 0.1, "kg"), comp("rice", 0.06, "kg"), comp("cooking_oil", 0.015),
    ], tags=["main", "beef", "meat", "spicy_food", "comfort_food"]),
    mk_recipe("causa_limena", "Causa Limeña", "main_dish", "side", [
        comp("potato", 0.2, "kg"), comp("aji_amarillo", 0.015), comp("lime_juice_fresh", 0.02),
        comp("avocado", 0.06, "kg"), comp("mayonnaise", 0.02),
    ], satiety_factor=0.7, tags=["side", "vegetarian", "fresh", "spicy_food", "traditional"]),
    mk_recipe("anticuchos", "Anticuchos", "grill", "main", [
        comp("beef_steak_rump", 0.15, "kg"), comp("aji_amarillo", 0.015), comp("cumin", 0.002, "kg"),
        comp("garlic", 0.003, "kg"), comp("vinegar", 0.01), comp("cooking_oil", 0.01),
    ], tags=["main", "beef", "meat", "grilled_food", "spicy_food"]),
    mk_recipe("papa_a_la_huancaina", "Papa a la Huancaína", "side", "side", [
        comp("potato", 0.2, "kg"), comp("queso_fresco", 0.06, "kg"), comp("aji_amarillo", 0.015),
        comp("milk", 0.03), comp("olives", 0.01, "kg", optional=True),
    ], satiety_factor=0.5, tags=["side", "vegetarian", "spicy_food", "traditional"]),
    mk_recipe("arroz_con_pollo", "Arroz con Pollo", "main_dish", "main", [
        comp("chicken_thigh", 0.15, "kg"), comp("rice", 0.08, "kg"), comp("cilantro", 0.005, "kg"),
        comp("peas", 0.03, "kg"), comp("bell_pepper", 0.03, "kg"), comp("vegetable_stock", 0.05),
    ], tags=["main", "poultry", "rice", "comfort_food", "traditional"]),
    mk_recipe("picarones", "Picarones", "dessert", "dessert", [
        comp("sweet_potato", 0.08, "kg"), comp("flour", 0.05, "kg"), comp("baking_powder", 0.002, "kg"),
        comp("cooking_oil", 0.03), comp("cane_sugar_syrup", 0.04),
    ], satiety_factor=0.35, tags=["dessert", "vegan", "vegetarian", "sweet_food", "fried_food", "traditional"]),
    mk_recipe("aji_de_gallina", "Ají de Gallina", "main_dish", "main", [
        comp("chicken_breast", 0.15, "kg"), comp("aji_amarillo", 0.02), comp("breadcrumbs", 0.02, "kg"),
        comp("milk", 0.05), comp("queso_fresco", 0.03, "kg"), comp("cashews", 0.01, "kg", optional=True),
    ], tags=["main", "poultry", "spicy_food", "comfort_food", "traditional"]),

    # --- Dänemark ---------------------------------------------------------------
    mk_recipe("smorrebrod_reje", "Smørrebrød mit Krabben", "fingerfood", "snack", [
        comp("rye_bread", 1, "pcs"), comp("butter", 0.005, "kg"), comp("shrimp", 0.06, "kg"),
        comp("mayonnaise", 0.01), comp("dill", 0.002, "kg"), comp("lemon", 0.01, "kg", optional=True),
    ], satiety_factor=0.35, tags=["fingerfood_food", "fish", "seafood", "bread", "traditional"]),
    mk_recipe("smorrebrod_leverpostej", "Smørrebrød mit Leberpastete", "fingerfood", "snack", [
        comp("rye_bread", 1, "pcs"), comp("liver_pate", 0.04, "kg"), comp("pickles", 0.015, "kg"),
        comp("fried_onions", 0.01, "kg"),
    ], satiety_factor=0.35, tags=["fingerfood_food", "pork", "bread", "comfort_food", "traditional"]),
    mk_recipe("smorrebrod_roastbeef", "Smørrebrød mit Roastbeef", "fingerfood", "snack", [
        comp("rye_bread", 1, "pcs"), comp("beef_steak_rump", 0.06, "kg"), comp("remoulade", 0.01),
        comp("fried_onions", 0.01, "kg"), comp("pickles", 0.01, "kg", optional=True),
    ], satiety_factor=0.35, tags=["fingerfood_food", "beef", "bread", "traditional"]),
    mk_recipe("danske_frikadeller", "Danske Frikadeller", "main_dish", "main", [
        comp("ground_pork", 0.15, "kg"), comp("onion", 0.02, "kg"), comp("eggs", 0.2, "pcs"),
        comp("breadcrumbs", 0.02, "kg"), comp("milk", 0.03), comp("flour", 0.01, "kg"),
    ], tags=["main", "pork", "meat", "comfort_food", "traditional"]),
    mk_recipe("flaeskesteg", "Flæskesteg", "main_dish", "main", [
        comp("pork_belly", 0.22, "kg"), comp("red_cabbage", 0.06, "kg", optional=True),
        comp("rosemary", 0.002, "kg", optional=True),
    ], tags=["main", "pork", "meat", "comfort_food", "traditional", "festive"]),
    mk_recipe("rodkal", "Rødkål", "side", "side", [
        comp("red_cabbage", 0.12, "kg"), comp("apple", 0.03, "kg"), comp("vinegar", 0.01),
        comp("sugar", 0.01, "kg"), comp("butter", 0.01, "kg", optional=True),
    ], satiety_factor=0.3, tags=["side", "vegan", "vegetarian", "comfort_food", "traditional"]),
    mk_recipe("karrysild", "Karrysild", "salad", "salad", [
        comp("herring", 0.1, "kg"), comp("curry_paste", 0.015), comp("apple", 0.03, "kg"),
        comp("onion", 0.02, "kg"), comp("mayonnaise", 0.02),
    ], satiety_factor=0.4, tags=["salad", "fish", "comfort_food", "traditional"]),
    mk_recipe("aebleskiver", "Æbleskiver", "dessert", "dessert", [
        comp("flour", 0.04, "kg"), comp("eggs", 0.4, "pcs"), comp("milk", 0.06),
        comp("butter", 0.015, "kg"), comp("baking_powder", 0.002, "kg"), comp("powdered_sugar", 0.01, "kg"),
    ], satiety_factor=0.35, tags=["dessert", "vegetarian", "sweet_food", "traditional", "festive"]),
    mk_recipe("wienerbroed", "Wienerbrød", "dessert", "dessert", [
        comp("puff_pastry", 0.06, "kg"), comp("butter", 0.02, "kg"), comp("sugar", 0.015, "kg"),
        comp("vanilla_extract", 0.002), comp("almonds", 0.01, "kg", optional=True),
    ], satiety_factor=0.3, tags=["dessert", "vegetarian", "sweet_food", "baked_food", "traditional"]),

    # --- Japan --------------------------------------------------------------------
    mk_recipe("chicken_yakitori", "Chicken Yakitori", "grill", "main", [
        comp("chicken_thigh", 0.15, "kg"), comp("soy_sauce", 0.015), comp("mirin", 0.01),
        comp("sugar", 0.005, "kg", optional=True),
    ], tags=["main", "poultry", "grilled_food", "savory", "traditional"]),
    mk_recipe("gyoza", "Gyoza", "fingerfood", "snack", [
        comp("ground_pork", 0.08, "kg"), comp("cabbage", 0.04, "kg"), comp("garlic", 0.002, "kg"),
        comp("ginger", 0.002, "kg"), comp("soy_sauce", 0.01), comp("spring_roll_wrapper", 0.04, "kg"),
        comp("cooking_oil", 0.01),
    ], satiety_factor=0.4, tags=["fingerfood_food", "pork", "fried_food", "savory", "traditional"]),
    mk_recipe("edamame_steamed", "Edamame", "fingerfood", "snack", [
        comp("edamame", 0.1, "kg"), comp("salt", 0.002, "kg", optional=True),
    ], satiety_factor=0.25, tags=["fingerfood_food", "vegan", "vegetarian", "fresh", "light_food"]),
    mk_recipe("onigiri", "Onigiri", "fingerfood", "snack", [
        comp("rice", 0.08, "kg"), comp("nori", 0.002, "kg"), comp("salt", 0.001, "kg", optional=True),
        comp("salmon_fillet", 0.03, "kg", optional=True),
    ], satiety_factor=0.4, tags=["fingerfood_food", "rice", "vegetarian", "light_food", "traditional"]),
    mk_recipe("tempura_vegetable", "Gemüse-Tempura", "fingerfood", "snack", [
        comp("sweet_potato", 0.05, "kg"), comp("bell_pepper", 0.03, "kg"), comp("zucchini", 0.03, "kg"),
        comp("flour", 0.03, "kg"), comp("eggs", 0.2, "pcs"), comp("cooking_oil", 0.03),
    ], satiety_factor=0.4, tags=["fingerfood_food", "vegetarian", "fried_food", "vegetable", "light_food"]),
    mk_recipe("miso_soup", "Miso-Suppe", "side", "side", [
        comp("miso_paste", 0.02), comp("tofu", 0.04, "kg"), comp("vegetable_stock", 0.15),
        comp("scallion", 0.005, "kg", optional=True),
    ], satiety_factor=0.3, tags=["side", "vegan", "vegetarian", "light_food", "traditional"]),
    mk_recipe("salmon_maki", "Lachs-Maki", "fingerfood", "snack", [
        comp("rice", 0.06, "kg"), comp("nori", 0.003, "kg"), comp("salmon_fillet", 0.06, "kg"),
        comp("cucumber", 0.02, "kg"), comp("vinegar", 0.005, "kg", optional=True),
    ], satiety_factor=0.4, tags=["fingerfood_food", "fish", "seafood", "rice", "fresh"]),
    mk_recipe("okonomiyaki", "Okonomiyaki", "main_dish", "main", [
        comp("flour", 0.05, "kg"), comp("cabbage", 0.08, "kg"), comp("eggs", 0.5, "pcs"),
        comp("bacon", 0.02, "kg", optional=True), comp("okonomiyaki_sauce", 0.02),
        comp("mayonnaise", 0.01, optional=True),
    ], tags=["main", "vegetarian", "savory", "comfort_food", "traditional"]),

    # --- USA --------------------------------------------------------------------
    mk_recipe("cornbread", "Cornbread", "side", "side", [
        comp("cornmeal", 0.05, "kg"), comp("flour", 0.02, "kg"), comp("milk", 0.05),
        comp("eggs", 0.3, "pcs"), comp("butter", 0.015, "kg"), comp("sugar", 0.01, "kg"),
        comp("baking_powder", 0.002, "kg"),
    ], satiety_factor=0.4, tags=["side", "bread", "vegetarian", "comfort_food", "traditional"]),
    mk_recipe("smoked_brisket", "Smoked Brisket", "grill", "main", [
        comp("beef_brisket", 0.25, "kg"), comp("bbq_sauce", 0.03, optional=True), comp("paprika_powder", 0.003, "kg"),
    ], tags=["main", "beef", "meat", "bbq", "grilled_food"]),
    mk_recipe("clam_chowder", "Clam Chowder", "main_dish", "main", [
        comp("clams", 0.12, "kg"), comp("potato", 0.08, "kg"), comp("cream", 0.06),
        comp("onion", 0.02, "kg"), comp("celery", 0.02, "kg"), comp("butter", 0.01, "kg"),
    ], satiety_factor=0.6, tags=["main", "fish", "seafood", "comfort_food", "traditional"]),
    mk_recipe("apple_pie", "Apple Pie", "dessert", "dessert", [
        comp("apple", 0.1, "kg"), comp("flour", 0.04, "kg"), comp("butter", 0.025, "kg"),
        comp("sugar", 0.02, "kg"), comp("cinnamon", 0.001, "kg"), comp("eggs", 0.15, "pcs", optional=True),
    ], satiety_factor=0.35, tags=["dessert", "vegetarian", "sweet_food", "baked_food", "traditional"]),
    mk_recipe("pecan_pie", "Pecan Pie", "dessert", "dessert", [
        comp("pecans", 0.05, "kg"), comp("flour", 0.02, "kg"), comp("butter", 0.015, "kg"),
        comp("sugar", 0.03, "kg"), comp("eggs", 0.3, "pcs"), comp("vanilla_extract", 0.002),
    ], satiety_factor=0.35, tags=["dessert", "vegetarian", "sweet_food", "baked_food", "traditional"]),
    mk_recipe("smores", "S'mores", "fingerfood", "snack", [
        comp("graham_crackers", 0.02, "kg"), comp("marshmallow", 0.02, "kg"), comp("chocolate", 0.015, "kg"),
    ], satiety_factor=0.3, tags=["fingerfood_food", "vegetarian", "sweet_food", "nostalgic", "party_classic"]),
    mk_recipe("buffalo_cauliflower", "Buffalo Cauliflower", "fingerfood", "snack", [
        comp("cauliflower", 0.12, "kg"), comp("hot_sauce", 0.02), comp("flour", 0.02, "kg"),
        comp("cooking_oil", 0.02),
    ], satiety_factor=0.35, tags=["fingerfood_food", "vegan", "vegetarian", "spicy_food", "fried_food"]),
    mk_recipe("cobb_salad", "Cobb Salad", "salad", "salad", [
        comp("mixed_greens", 0.08, "kg"), comp("chicken_breast", 0.08, "kg"), comp("bacon", 0.02, "kg"),
        comp("blue_cheese", 0.02, "kg"), comp("eggs", 0.3, "pcs"), comp("avocado", 0.04, "kg"),
        comp("tomato", 0.03, "kg"),
    ], satiety_factor=0.7, tags=["salad", "poultry", "meat", "comfort_food", "fresh"]),
])


# --- SONSTIGE REZEPTE (nicht eindeutig Cocktail/Food, aber Alias-Ziele) --------
# z.B. "Spezi" (Cola/Fanta-Mix), das in §26 als eigenes Alias-Ziel genannt wird.

MISC_RECIPES_RAW: list[dict] = [
    mk_recipe("spezi", "Spezi", "softdrink_mix", "non_alcoholic_beverage", [
        comp("cola", 0.15), comp("fanta_orange", 0.15),
    ], serving_unit="glass", popular=True),
]

# --- Geo-Kultur-Getränke, alkoholfrei (Geo-/Kultur-Kontext-Spec §4/§6) ----------
MISC_RECIPES_RAW.extend([
    # --- Indien -----------------------------------------------------------------
    mk_recipe("masala_chai", "Masala Chai", "tea", "non_alcoholic_beverage", [
        comp("black_tea", 0.005, "kg"), comp("milk", 0.1), comp("cardamom", 0.001, "kg"),
        comp("cinnamon", 0.001, "kg", optional=True), comp("sugar", 0.01, "kg", optional=True),
    ], serving_unit="glass", tags=["hot_drink", "tea", "non_alcoholic", "traditional"]),
    mk_recipe("mango_lassi", "Mango Lassi", "lassi", "non_alcoholic_beverage", [
        comp("yogurt", 0.15), comp("mango_juice", 0.08), comp("sugar", 0.01, "kg", optional=True),
    ], serving_unit="glass", tags=["non_alcoholic", "fruity", "refreshing", "tropical", "traditional"]),
    mk_recipe("salted_lassi", "Salted Lassi", "lassi", "non_alcoholic_beverage", [
        comp("yogurt", 0.18), comp("water", 0.05), comp("cumin", 0.001, "kg"),
        comp("mint", 0.002, "kg", optional=True),
    ], serving_unit="glass", tags=["non_alcoholic", "refreshing", "traditional", "savory"]),
    mk_recipe("nimbu_pani", "Nimbu Pani", "softdrink_mix", "non_alcoholic_beverage", [
        comp("lime_juice_fresh", 0.03), comp("water", 0.15), comp("sugar", 0.015, "kg"),
        comp("mint", 0.002, "kg", optional=True), comp("salt", 0.001, "kg", optional=True),
    ], serving_unit="glass", tags=["non_alcoholic", "refreshing", "citrus", "traditional", "hydrating"]),

    # --- Peru -----------------------------------------------------------------
    mk_recipe("chicha_morada", "Chicha Morada", "softdrink_mix", "non_alcoholic_beverage", [
        comp("purple_corn", 0.06, "kg"), comp("pineapple", 0.03, "kg"), comp("cinnamon", 0.001, "kg"),
        comp("cane_sugar_syrup", 0.03), comp("lime_juice_fresh", 0.01), comp("water", 0.15),
    ], serving_unit="glass", tags=["non_alcoholic", "fruity", "refreshing", "traditional"]),

    # --- Dänemark ---------------------------------------------------------------
    mk_recipe("solbaersaft", "Solbærsaft", "softdrink_mix", "non_alcoholic_beverage", [
        comp("currant_juice", 0.1), comp("water", 0.1), comp("sugar", 0.01, "kg", optional=True),
    ], serving_unit="glass", tags=["non_alcoholic", "refreshing", "fruity", "traditional"]),

    # --- Japan ------------------------------------------------------------------
    mk_recipe("matcha_latte", "Matcha Latte", "tea", "non_alcoholic_beverage", [
        comp("matcha", 0.003, "kg"), comp("milk", 0.12), comp("honey", 0.01, optional=True),
    ], serving_unit="glass", tags=["hot_drink", "tea", "non_alcoholic", "caffeinated", "traditional"]),

    # --- USA --------------------------------------------------------------------
    mk_recipe("arnold_palmer", "Arnold Palmer", "softdrink_mix", "non_alcoholic_beverage", [
        comp("black_tea", 0.003, "kg"), comp("lemonade_lemon", 0.15), comp("water", 0.05, optional=True),
    ], serving_unit="glass", tags=["non_alcoholic", "refreshing", "citrus", "traditional"]),
    mk_recipe("fresh_lemonade", "Fresh Lemonade", "softdrink_mix", "non_alcoholic_beverage", [
        comp("lemon", 0.06, "kg"), comp("sugar", 0.02, "kg"), comp("water", 0.2),
        comp("mint", 0.002, "kg", optional=True),
    ], serving_unit="glass", tags=["non_alcoholic", "refreshing", "citrus", "fresh"]),
    mk_recipe("root_beer_float", "Root Beer Float", "softdrink_mix", "non_alcoholic_beverage", [
        comp("root_beer", 0.2), comp("vanilla_ice_cream", 0.06, "kg"),
    ], serving_unit="glass", tags=["non_alcoholic", "sweet", "creamy", "nostalgic", "party_classic"]),
])

# Alle Rezepte (Cocktails + Food + Sonstige) in einem gemeinsamen Container,
# da PartyCatalog.recipes ein einziges dict ist (keine Trennung nach Herkunft).
ALL_RECIPES_RAW: list[dict] = COCKTAILS_RAW + FOOD_RAW + MISC_RECIPES_RAW
_RECIPE_IDS: set[str] = {r["id"] for r in ALL_RECIPES_RAW}
_DIRECT_CONSUMABLE_IDS: set[str] = {d["id"] for d in DIRECT_CONSUMABLES_RAW}


# --- MODIFIER (Spec §28) --------------------------------------------------------
# Freitext-Zusätze zu einem bereits erkannten Item (Zutat hinzufügen/entfernen,
# Menge skalieren, Markenpräferenz setzen). applies_to referenziert die
# category-Werte der betroffenen Recipes/DirectConsumables (bzw. "*" = alle).


def modifier(mod_id: str, name: str, applies_to: list[str], effect_type: str,
             target_ingredient_id: str = "", amount: float = 0.0, unit: str = "l",
             brand: str = "") -> dict:
    if target_ingredient_id and target_ingredient_id not in INGREDIENTS_BY_ID:
        raise KeyError(f"Unbekannte ingredient_id in Modifier {mod_id!r}: {target_ingredient_id!r}")
    return dict(id=mod_id, name=name, applies_to=applies_to, effect_type=effect_type,
                target_ingredient_id=target_ingredient_id, amount=amount, unit=unit, brand=brand)


MODIFIERS_RAW: list[dict] = [
    # Zutat hinzufügen
    modifier("mod_add_cheddar", "Extra Cheddar", ["burger"], "add_component", "cheddar", 0.02, "kg"),
    modifier("mod_add_bacon", "Extra Bacon", ["burger", "fingerfood", "grill"], "add_component", "bacon", 0.03, "kg"),
    modifier("mod_add_fried_onions", "Extra Röstzwiebeln", ["grill", "burger"], "add_component",
             "fried_onions", 0.02, "kg"),
    modifier("mod_add_herb_butter", "Mit Kräuterbutter", ["grill", "main_dish"], "add_component",
             "herb_butter", 0.02, "l"),
    modifier("mod_add_guacamole_dip", "Mit Guacamole-Dip", ["fingerfood", "main_dish"], "add_component",
             "guacamole", 0.05, "l"),
    modifier("mod_add_avocado", "Extra Avocado", ["burger", "salad"], "add_component", "avocado", 0.03, "kg"),
    modifier("mod_add_jalapeno", "Extra Jalapeños", ["burger", "main_dish", "fingerfood"], "add_component",
             "jalapeno", 0.015, "kg"),
    modifier("mod_add_chili_flakes", "Extra scharf (Chiliflocken)", ["*"], "add_component",
             "chili_flakes", 0.002, "kg"),
    modifier("mod_add_extra_ketchup", "Extra Ketchup", ["burger", "grill", "fingerfood"], "add_component",
             "ketchup", 0.01, "l"),
    modifier("mod_add_cheese_sauce_dip", "Mit Cheese Sauce", ["fingerfood", "main_dish"], "add_component",
             "cheese_sauce", 0.04, "l"),
    modifier("mod_add_bbq_sauce", "Mit BBQ-Sauce", ["grill", "burger"], "add_component", "bbq_sauce", 0.02, "l"),
    modifier("mod_double_patty", "Doppel-Patty", ["burger"], "add_component", "beef_patty", 0.15, "kg"),
    # Zutat entfernen
    modifier("mod_remove_cheese", "Ohne Käse", ["burger"], "remove_component", "cheddar"),
    modifier("mod_remove_onion", "Ohne Zwiebeln", ["burger", "grill"], "remove_component", "onion"),
    modifier("mod_remove_mustard", "Ohne Senf", ["burger", "grill"], "remove_component", "mustard"),
    # Menge skalieren
    modifier("mod_double_portion", "Doppelte Portion", ["*"], "scale", "", 2.0, ""),
    modifier("mod_half_portion", "Halbe Portion", ["*"], "scale", "", 0.5, ""),
    # Markenpräferenz
    modifier("mod_brand_gin_hendricks", "Gin: Hendrick's bevorzugt", ["cocktail_gin"],
             "set_brand_preference", "gin", brand="Hendrick's"),
    modifier("mod_brand_coffee_liqueur_kahlua", "Kaffeelikör: Kahlúa bevorzugt", ["cocktail_vodka"],
             "set_brand_preference", "coffee_liqueur", brand="Kahlúa"),
    modifier("mod_brand_vodka_absolut", "Vodka: Absolut bevorzugt", ["cocktail_vodka", "spirit"],
             "set_brand_preference", "vodka", brand="Absolut"),
    modifier("mod_brand_rum_bacardi", "Rum: Bacardi bevorzugt", ["cocktail_rum"],
             "set_brand_preference", "rum_white", brand="Bacardi"),
    modifier("mod_brand_whiskey_jd", "Whiskey: Jack Daniel's bevorzugt", ["cocktail_whiskey"],
             "set_brand_preference", "tennessee_whiskey", brand="Jack Daniel's"),
]


# --- ALIASE (Spec §26) -----------------------------------------------------------
# Ziel: 500+ Alias-/Schreibvarianten. Aufbau in Schichten:
#   1. Explizite Spec-Beispiele (wörtlich)
#   2. Kuratierte Spitznamen/Tippfehler für populäre Cocktails & Spirituosen
#   3. Markenpräferenz-Aliase für bekannte Spirituosenmarken
#   4. Programmatisch generierte Kleinschreibungs- und Umlaut-Varianten für
#      JEDEN Cocktail, JEDES Gericht und JEDEN Direktkonsum-Artikel


def alias(alias_text: str, target_type: str, target_id: str,
          confidence: float = 1.0, brand: str = "") -> dict:
    return dict(alias_text=alias_text, target_type=target_type, target_id=target_id,
                confidence=confidence, brand=brand)


ALIASES_RAW: list[dict] = []

# 1. Explizite Beispiele aus Spec §26 (wörtlich, auf tatsächliche Katalog-IDs gemappt)
_EXPLICIT_ALIASES: list[tuple] = [
    ("wodka", "direct_consumable", "vodka", 1.0, ""),
    ("voddi", "direct_consumable", "vodka", 0.9, ""),
    ("redbull", "direct_consumable", "energy_drink_generic", 0.95, "Red Bull"),
    ("red bull", "direct_consumable", "energy_drink_generic", 0.95, "Red Bull"),
    ("vodka bull", "recipe", "vodka_red_bull", 0.9, ""),
    ("wodka bull", "recipe", "vodka_red_bull", 0.85, ""),
    ("jacky cola", "recipe", "whiskey_cola", 0.9, "Jack Daniel's"),
    ("bacardi cola", "recipe", "rum_cola", 0.9, "Bacardi"),
    ("gin t", "recipe", "gin_tonic", 0.85, ""),
    ("g&t", "recipe", "gin_tonic", 0.9, ""),
    ("gt", "recipe", "gin_tonic", 0.78, ""),
    ("aperol", "recipe", "aperol_spritz", 0.6, ""),
    ("aperol spritz", "recipe", "aperol_spritz", 1.0, ""),
    ("hugo", "recipe", "hugo", 1.0, ""),
    ("caipi", "recipe", "caipirinha", 0.9, ""),
    ("pina colada", "recipe", "pina_colada", 1.0, ""),
    ("pina", "recipe", "pina_colada", 0.8, ""),
    ("long island", "recipe", "long_island_iced_tea", 0.9, ""),
    ("long island ice tea", "recipe", "long_island_iced_tea", 0.92, ""),
    ("espresso martini", "recipe", "espresso_martini", 1.0, ""),
    ("pornstar", "recipe", "porn_star_martini", 0.9, ""),
    ("pornstar martini", "recipe", "porn_star_martini", 0.95, ""),
    ("spezi", "recipe", "spezi", 1.0, ""),
    ("coke", "direct_consumable", "cola", 0.9, ""),
    ("coca cola", "direct_consumable", "cola", 0.95, "Coca-Cola"),
    ("cola light", "direct_consumable", "cola_light", 0.85, ""),
    ("würstchen", "recipe", "bratwurst", 0.65, ""),
    ("wuerstchen", "recipe", "bratwurst", 0.65, ""),
    ("grillwurst", "recipe", "bratwurst", 0.85, ""),
    ("nacken", "recipe", "nackensteak", 0.85, ""),
    ("knobibrot", "recipe", "knoblauchbrot", 0.85, ""),
    ("guac", "direct_consumable", "guacamole", 0.9, ""),
    ("veggie würstchen", "recipe", "veggie_bratwurst", 0.85, ""),
    ("veggie wuerstchen", "recipe", "veggie_bratwurst", 0.85, ""),
    ("vegane wurst", "recipe", "vegane_bratwurst", 0.85, ""),
    ("kartoffelsalat", "recipe", "kartoffelsalat", 1.0, ""),
    ("nudelsalat", "recipe", "nudelsalat", 1.0, ""),
    ("pommes", "recipe", "pommes", 1.0, ""),
    ("süßkartoffelpommes", "recipe", "suesskartoffelpommes", 1.0, ""),
    ("suesskartoffelpommes", "recipe", "suesskartoffelpommes", 1.0, ""),
    ("majo", "direct_consumable", "mayonnaise", 0.9, ""),
    ("mayo", "direct_consumable", "mayonnaise", 0.95, ""),
]
ALIASES_RAW.extend(alias(*a) for a in _EXPLICIT_ALIASES)

# 2. Kuratierte Spitznamen/Tippfehler für populäre Cocktails
_CURATED_COCKTAIL_ALIASES: list[tuple] = [
    ("gin tonic", "recipe", "gin_tonic", 1.0, ""),
    ("gin und tonic", "recipe", "gin_tonic", 0.9, ""),
    ("wodka lemon", "recipe", "vodka_lemon", 0.85, ""),
    ("cuba libre", "recipe", "cuba_libre", 1.0, ""),
    ("rum cola", "recipe", "rum_cola", 1.0, ""),
    ("whiskey cola", "recipe", "whiskey_cola", 1.0, ""),
    ("whisky cola", "recipe", "whiskey_cola", 0.9, ""),
    ("jack and cola", "recipe", "whiskey_cola", 0.85, "Jack Daniel's"),
    ("mule", "recipe", "moscow_mule", 0.75, ""),
    ("moscow mule", "recipe", "moscow_mule", 1.0, ""),
    ("cosmo", "recipe", "cosmopolitan", 0.85, ""),
    ("bloody mary", "recipe", "bloody_mary", 1.0, ""),
    ("caipirinha", "recipe", "caipirinha", 1.0, ""),
    ("mojito", "recipe", "mojito", 1.0, ""),
    ("mohito", "recipe", "mojito", 0.8, ""),
    ("daiquiri", "recipe", "daiquiri", 1.0, ""),
    ("old fashioned", "recipe", "old_fashioned", 1.0, ""),
    ("manhattan", "recipe", "manhattan", 1.0, ""),
    ("margarita", "recipe", "margarita", 1.0, ""),
    ("margherita", "recipe", "margarita", 0.75, ""),
    ("negroni", "recipe", "negroni", 1.0, ""),
    ("americano", "recipe", "americano", 1.0, ""),
    ("sidecar", "recipe", "sidecar", 1.0, ""),
    ("aviation", "recipe", "aviation", 1.0, ""),
    ("french 75", "recipe", "french_75", 1.0, ""),
    ("french seventy five", "recipe", "french_75", 0.8, ""),
    ("tom collins", "recipe", "tom_collins", 1.0, ""),
    ("whiskey sour", "recipe", "whiskey_sour", 1.0, ""),
    ("whisky sour", "recipe", "whiskey_sour", 0.9, ""),
    ("amaretto sour", "recipe", "amaretto_sour", 1.0, ""),
    ("pisco sour", "recipe", "pisco_sour", 1.0, ""),
    ("mai tai", "recipe", "mai_tai", 1.0, ""),
    ("dark and stormy", "recipe", "dark_n_stormy", 0.9, ""),
    ("zombie", "recipe", "zombie", 1.0, ""),
    ("hurricane", "recipe", "hurricane", 1.0, ""),
    ("painkiller", "recipe", "painkiller", 1.0, ""),
    ("sazerac", "recipe", "sazerac", 1.0, ""),
    ("boulevardier", "recipe", "boulevardier", 1.0, ""),
    ("penicillin", "recipe", "penicillin", 1.0, ""),
    ("irish coffee", "recipe", "irish_coffee", 1.0, ""),
    ("white russian", "recipe", "white_russian", 1.0, ""),
    ("black russian", "recipe", "black_russian", 1.0, ""),
    ("sex on the beach", "recipe", "sex_on_the_beach", 1.0, ""),
    ("sexonthebeach", "recipe", "sex_on_the_beach", 0.85, ""),
    ("screwdriver", "recipe", "screwdriver", 1.0, ""),
    ("bellini", "recipe", "bellini", 1.0, ""),
    ("mimosa", "recipe", "mimosa", 1.0, ""),
    ("kir royal", "recipe", "kir_royal", 1.0, ""),
    ("sangria", "recipe", "sangria_rot", 0.8, ""),
    ("weiße sangria", "recipe", "sangria_weiss", 0.85, ""),
    ("weisse sangria", "recipe", "sangria_weiss", 0.85, ""),
    ("tequila sunrise", "recipe", "tequila_sunrise", 1.0, ""),
    ("paloma", "recipe", "paloma", 1.0, ""),
    ("jägerbomb", "recipe", "jaegerbomb", 0.9, ""),
    ("jaegerbomb", "recipe", "jaegerbomb", 1.0, ""),
    ("jager bomb", "recipe", "jaegerbomb", 0.85, ""),
    ("jäger bomb", "recipe", "jaegerbomb", 0.85, ""),
]
ALIASES_RAW.extend(alias(*a) for a in _CURATED_COCKTAIL_ALIASES)

# 3. Markenpräferenz-Aliase für bekannte Spirituosenmarken
_BRAND_ALIASES: list[tuple] = [
    ("absolut", "direct_consumable", "vodka", 0.9, "Absolut"),
    ("belvedere", "direct_consumable", "vodka", 0.9, "Belvedere"),
    ("grey goose", "direct_consumable", "vodka", 0.9, "Grey Goose"),
    ("smirnoff", "direct_consumable", "vodka", 0.9, "Smirnoff"),
    ("hendricks", "direct_consumable", "gin", 0.85, "Hendrick's"),
    ("hendrick's", "direct_consumable", "gin", 0.9, "Hendrick's"),
    ("bombay sapphire", "direct_consumable", "gin", 0.9, "Bombay Sapphire"),
    ("tanqueray", "direct_consumable", "gin", 0.9, "Tanqueray"),
    ("bacardi", "direct_consumable", "rum_white", 0.85, "Bacardi"),
    ("captain morgan", "direct_consumable", "rum_spiced", 0.9, "Captain Morgan"),
    ("jim beam", "direct_consumable", "bourbon", 0.9, "Jim Beam"),
    ("jack daniels", "direct_consumable", "tennessee_whiskey", 0.9, "Jack Daniel's"),
    ("jack daniel's", "direct_consumable", "tennessee_whiskey", 0.95, "Jack Daniel's"),
    ("jameson", "direct_consumable", "irish_whiskey", 0.9, "Jameson"),
    ("chivas regal", "direct_consumable", "scotch_whisky", 0.9, "Chivas Regal"),
    ("jose cuervo", "direct_consumable", "tequila_blanco", 0.85, "Jose Cuervo"),
    ("patron", "direct_consumable", "tequila_blanco", 0.85, "Patrón"),
    ("kahlua", "direct_consumable", "coffee_liqueur", 0.9, "Kahlúa"),
    ("kahlúa", "direct_consumable", "coffee_liqueur", 0.95, "Kahlúa"),
    ("baileys irish cream", "direct_consumable", "baileys", 0.95, "Baileys"),
    ("aperol pur", "direct_consumable", "aperol", 0.9, "Aperol"),
    ("campari", "direct_consumable", "campari", 1.0, "Campari"),
    ("martini bianco", "direct_consumable", "sweet_vermouth", 0.8, "Martini"),
    ("jägermeister", "direct_consumable", "jaegermeister", 1.0, "Jägermeister"),
    ("jagermeister", "direct_consumable", "jaegermeister", 0.9, "Jägermeister"),
]
ALIASES_RAW.extend(alias(*a) for a in _BRAND_ALIASES)


def _asciify(text: str) -> str:
    """Grobe Umlaut-freie Schreibvariante (z.B. für Tippen ohne deutsche Tastatur)."""
    return (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss"))


def _generate_name_aliases(items: list[dict], target_type: str) -> list[dict]:
    """Erzeugt für jedes Item eine kleingeschriebene Alias-Variante des Namens
    sowie (falls abweichend) eine Umlaut-freie ASCII-Variante."""
    out: list[dict] = []
    for it in items:
        lower = it["name"].lower()
        out.append(alias(lower, target_type, it["id"], 1.0))
        ascii_variant = _asciify(lower)
        if ascii_variant != lower:
            out.append(alias(ascii_variant, target_type, it["id"], 0.9))
    return out


# 4. Programmatisch generierte Name-Varianten für ALLE Cocktails, Food-Rezepte
#    und Direktkonsum-Artikel (Klein-/Umlautschreibung als zusätzliche Alias-Ebene)
ALIASES_RAW.extend(_generate_name_aliases(COCKTAILS_RAW, "recipe"))
ALIASES_RAW.extend(_generate_name_aliases(FOOD_RAW, "recipe"))
ALIASES_RAW.extend(_generate_name_aliases(MISC_RECIPES_RAW, "recipe"))
ALIASES_RAW.extend(_generate_name_aliases(DIRECT_CONSUMABLES_RAW, "direct_consumable"))

# Duplikate entfernen (gleicher Text + gleiches Ziel), Reihenfolge bleibt stabil.
_seen_alias_keys: set[tuple] = set()
_deduped_aliases: list[dict] = []
for _a in ALIASES_RAW:
    _key = (_a["alias_text"], _a["target_type"], _a["target_id"])
    if _key in _seen_alias_keys:
        continue
    _seen_alias_keys.add(_key)
    _deduped_aliases.append(_a)
ALIASES_RAW = _deduped_aliases


# --- SUBSTITUTION RULES (Spec §33) ----------------------------------------------
# Hierarchisch/asymmetrisch: Ernährungsinkompatible Substitutionen sind hier
# grundsätzlich ausgeschlossen (z.B. Fleisch ersetzt niemals vegan/vegetarisch).
# direction="one_way" bedeutet: from_id darf to_id ersetzen, nicht umgekehrt
# (z.B. Alkohol -> alkoholfrei als Overflow, niemals umgekehrt).


def substitution(from_id: str, to_id: str, compatibility: float,
                  direction: str = "bidirectional", note: str = "") -> dict:
    return dict(from_id=from_id, to_id=to_id, compatibility=compatibility,
                direction=direction, note=note)


SUBSTITUTION_RULES_RAW: list[dict] = [
    # Softdrinks
    substitution("cola", "cola_zero", 0.95, note="Cola <-> Cola Zero: hohe Kompatibilität"),
    substitution("cola", "cola_light", 0.9, note="Cola <-> Cola Light: hohe Kompatibilität"),
    substitution("cola_zero", "cola_light", 0.9),
    substitution("cola", "fanta_orange", 0.6, note="Cola <-> Fanta: mittlere Kompatibilität"),
    substitution("fanta_orange", "fanta_lemon", 0.7),
    substitution("sprite", "seven_up", 0.9),
    substitution("lemonade_orange", "lemonade_lemon", 0.6),
    # Wein / Sekt
    substitution("prosecco", "sekt", 0.9, note="Prosecco <-> Sekt: hohe Kompatibilität"),
    substitution("prosecco", "cava", 0.85),
    substitution("sekt", "cremant", 0.8),
    substitution("red_wine", "rose_wine", 0.5),
    substitution("white_wine", "rose_wine", 0.5),
    # Bier-Stile (Auswahl)
    substitution("beer_pils", "beer_lager", 0.85),
    substitution("beer_helles", "beer_export", 0.8),
    substitution("beer_hefeweizen", "beer_kristallweizen", 0.8),
    substitution("beer_hefeweizen", "beer_dunkelweizen", 0.6),
    # Essen
    substitution("classic_burger", "cheeseburger", 0.9, note="Burger <-> Cheeseburger: hohe Kompatibilität"),
    substitution("classic_burger", "bacon_burger", 0.85),
    substitution("classic_burger", "hotdog", 0.6, note="Burger <-> Hotdog: mittlere Kompatibilität"),
    substitution("kartoffelsalat", "nudelsalat", 0.75, note="Kartoffelsalat <-> Nudelsalat"),
    substitution("baguette", "ciabatta", 0.95, note="Baguette <-> Ciabatta: sehr hohe Kompatibilität"),
    substitution("bratkartoffeln", "kartoffelwedges", 0.7),
    substitution("pommes", "kartoffelwedges", 0.6),
    substitution("reis", "basmati_reis", 0.9),
    substitution("couscous_side", "bulgur_side", 0.7),
    substitution("gruener_salat", "gemischter_salat", 0.85),
    substitution("caesar_salad", "gruener_salat", 0.6),
    substitution("brownies", "blondies", 0.8),
    substitution("muffins", "cupcakes", 0.8),
    substitution("tiramisu", "panna_cotta", 0.5),
    substitution("vanillepudding_dessert", "schokopudding_dessert", 0.8),
    # Vegan darf vegetarische Nachfrage substituieren (nicht umgekehrt)
    substitution("vegan_burger", "veggie_burger", 0.8, direction="one_way",
                 note="Vegane Portion darf vegetarische Nachfrage substituieren, nicht umgekehrt"),
    substitution("vegane_bratwurst", "veggie_bratwurst", 0.8, direction="one_way",
                 note="Vegane Portion darf vegetarische Nachfrage substituieren, nicht umgekehrt"),
    # Alkohol -> alkoholfrei: Overflow erlaubt, niemals umgekehrt
    substitution("red_wine", "wine_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("white_wine", "wine_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("prosecco", "sparkling_wine_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("sekt", "sparkling_wine_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("beer_pils", "beer_pils_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("beer_helles", "beer_helles_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("beer_hefeweizen", "beer_weizen_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("beer_dunkelweizen", "beer_weizen_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
    substitution("beer_kristallweizen", "beer_weizen_alcohol_free", 0.6, direction="one_way",
                 note="Overflow: Alkohol -> alkoholfrei erlaubt, niemals umgekehrt"),
]


# --- PRODUCTION RULES (Spec §34) -------------------------------------------------
# output_ingredient_id wird aus inputs "produziert" statt direkt eingekauft
# (siehe Ingredient.purchasable). "ratio" = benötigte Menge je 1 Einheit Output.


def production_rule(output_ingredient_id: str, inputs: list[tuple], note: str = "") -> dict:
    if output_ingredient_id not in INGREDIENTS_BY_ID:
        raise KeyError(f"Unbekannte output_ingredient_id in ProductionRule: {output_ingredient_id!r}")
    resolved_inputs = []
    for ingredient_id, ratio in inputs:
        if ingredient_id not in INGREDIENTS_BY_ID:
            raise KeyError(f"Unbekannte input ingredient_id in ProductionRule: {ingredient_id!r}")
        resolved_inputs.append({"ingredient_id": ingredient_id, "ratio": ratio})
    return dict(output_ingredient_id=output_ingredient_id, inputs=resolved_inputs, note=note)


PRODUCTION_RULES_RAW: list[dict] = [
    production_rule("lime_juice_fresh", [("lime", 2.9)],
                     note="ca. 2,9 kg Limetten ergeben 1 L frisch gepressten Saft"),
    production_rule("lemon_juice_fresh", [("lemon", 2.5)],
                     note="ca. 2,5 kg Zitronen ergeben 1 L frisch gepressten Saft"),
    production_rule("orange_juice", [("orange", 2.0)],
                     note="Optional: Orangensaft wird normalerweise direkt eingekauft; "
                          "ca. 2 kg Orangen ergeben 1 L frisch gepressten Saft"),
    production_rule("espresso", [("coffee_beans", 1.2)],
                     note="Espresso wird aus Kaffeebohnen gebrüht (Espresso-Shots)"),
    production_rule("simple_syrup", [("sugar", 0.5), ("water", 0.5)],
                     note="Simple Syrup: Zucker + Wasser (vereinfacht 1:1)"),
    production_rule("cane_sugar_syrup", [("sugar", 0.5), ("water", 0.5)],
                     note="Rohrzuckersirup: Zucker + Wasser (vereinfacht 1:1)"),
    production_rule("honey_syrup", [("honey", 0.6), ("water", 0.4)],
                     note="Honey Syrup: Honig + Wasser"),
    production_rule("guacamole", [("avocado", 0.6), ("lime_juice_fresh", 0.05),
                                   ("onion", 0.1), ("cilantro", 0.02), ("salt", 0.01)],
                     note="Optional: Guacamole kann auch fertig eingekauft werden"),
    production_rule("tzatziki", [("yogurt", 0.7), ("cucumber", 0.25), ("garlic", 0.02)],
                     note="Optional: Tzatziki kann auch fertig eingekauft werden"),
    production_rule("salsa_mild", [("tomato", 0.7), ("onion", 0.15),
                                    ("cilantro", 0.02), ("lime_juice_fresh", 0.03)],
                     note="Optional: Salsa kann auch fertig eingekauft werden"),
    production_rule("hummus", [("chickpeas", 0.6), ("garlic", 0.02), ("olive_oil", 0.1)],
                     note="Optional: Hummus kann auch fertig eingekauft werden"),
]


# --- PURCHASE SKUS (Spec §35) ----------------------------------------------------
# Typische Einkaufsgebinde je Ingredient-Familie, mit gezielten Overrides für
# einzelne Ingredients (z.B. Burger Buns im 4er/6er Pack statt Familien-Default).

_FAMILY_SKU_TEMPLATES: dict[str, list[tuple]] = {
    "spirit": [(0.7, "l", "Flasche 0,7L", 1), (1.0, "l", "Flasche 1L", 1)],
    "liqueur": [(0.7, "l", "Flasche 0,7L", 1), (1.0, "l", "Flasche 1L", 1)],
    "fortified_wine": [(0.7, "l", "Flasche 0,7L", 1), (0.75, "l", "Flasche 0,75L", 1)],
    "wine": [(0.75, "l", "Flasche 0,75L", 1)],
    "sake": [(0.72, "l", "Flasche 0,72L", 1)],
    "sparkling_wine": [(0.75, "l", "Flasche 0,75L", 1)],
    "beer": [(0.33, "l", "Flasche 0,33L", 1), (0.5, "l", "Flasche 0,5L", 1),
             (0.5, "l", "Kasten (20x0,5L)", 20)],
    "softdrink": [(0.5, "l", "Flasche 0,5L", 1), (1.0, "l", "Flasche 1L", 1),
                  (1.25, "l", "Flasche 1,25L", 1), (1.5, "l", "Flasche 1,5L", 1),
                  (2.0, "l", "Flasche 2L", 1)],
    "energy": [(0.25, "l", "Dose 0,25L", 1), (0.33, "l", "Dose 0,33L", 1), (0.5, "l", "Dose 0,5L", 1)],
    "juice": [(1.0, "l", "Flasche 1L", 1), (1.5, "l", "Flasche 1,5L", 1)],
    "syrup": [(0.7, "l", "Flasche 0,7L", 1)],
    "coffee": [(1.0, "l", "Packung", 1)],
    "dairy": [(0.5, "l", "Packung 0,5L", 1), (1.0, "l", "Packung 1L", 1)],
    "fruit": [(1.0, "kg", "Netz 1kg", 1)],
    "citrus": [(1.0, "kg", "Netz 1kg", 1)],
    "herb": [(0.05, "kg", "Bund/Topf", 1)],
    "meat_beef": [(0.5, "kg", "Packung 500g", 1), (1.0, "kg", "Packung 1kg", 1)],
    "meat_pork": [(0.5, "kg", "Packung 500g", 1), (1.0, "kg", "Packung 1kg", 1)],
    "meat_lamb": [(0.5, "kg", "Packung 500g", 1), (1.0, "kg", "Packung 1kg", 1)],
    "poultry": [(0.5, "kg", "Packung 500g", 1), (1.0, "kg", "Packung 1kg", 1)],
    "fish": [(0.3, "kg", "Packung 300g", 1), (0.5, "kg", "Packung 500g", 1)],
    "veg_protein": [(0.4, "kg", "Packung 400g", 1)],
    "vegan_protein": [(0.25, "kg", "Packung 250g", 1)],
    "bread": [(1, "pcs", "Stück", 1), (1, "pcs", "4er Pack", 4), (1, "pcs", "6er Pack", 6)],
    "potato": [(1.0, "kg", "Netz 1kg", 1), (2.5, "kg", "Netz 2,5kg", 1), (5.0, "kg", "Netz 5kg", 1)],
    "pasta": [(0.5, "kg", "Packung 500g", 1), (1.0, "kg", "Packung 1kg", 1)],
    "grain": [(0.5, "kg", "Packung 500g", 1), (1.0, "kg", "Packung 1kg", 1)],
    "salad_green": [(0.2, "kg", "Kopf/Beutel", 1)],
    "vegetable": [(1.0, "kg", "Netz 1kg", 1)],
    "cheese": [(0.2, "kg", "Packung 200g", 1), (1.0, "kg", "Block 1kg", 1)],
    "sauce": [(0.25, "l", "Flasche 0,25L", 1), (0.5, "l", "Flasche 0,5L", 1)],
    "spice": [(0.05, "kg", "Streuer/Tüte", 1)],
    "snack": [(0.1, "kg", "Tüte 100g", 1), (0.15, "kg", "Tüte 150g", 1), (0.2, "kg", "Tüte 200g", 1)],
    "dessert_ing": [(0.5, "kg", "Packung 500g", 1)],
    "ice": [(2.0, "kg", "Beutel 2kg", 1)],
    "water": [(0.5, "l", "Flasche 0,5L", 1), (1.5, "l", "Flasche 1,5L", 1),
              (1.5, "l", "Kasten (6x1,5L)", 6)],
    "oil": [(0.5, "l", "Flasche 0,5L", 1), (1.0, "l", "Flasche 1L", 1)],
    "bitters": [(0.2, "l", "Flasche 0,2L", 1)],
    "bar_misc": [(0.7, "l", "Flasche 0,7L", 1)],
    "plant_milk": [(1.0, "l", "Packung 1L", 1)],
}

# Gezielte Overrides für einzelne Ingredients (ersetzen den Familien-Default vollständig)
_PURCHASE_SKU_OVERRIDES: dict[str, list[tuple]] = {
    "burger_bun": [(1, "pcs", "4er Pack", 4), (1, "pcs", "6er Pack", 6)],
    "hotdog_bun": [(1, "pcs", "4er Pack", 4), (1, "pcs", "6er Pack", 6)],
    "pork_sausage_bratwurst": [(0.4, "kg", "4er Pack", 4), (0.5, "kg", "5er Pack", 5),
                                (1.0, "kg", "10er Pack", 10)],
    "pork_sausage_currywurst": [(0.4, "kg", "4er Pack", 4), (0.5, "kg", "5er Pack", 5),
                                 (1.0, "kg", "10er Pack", 10)],
    "pork_sausage_nuernberger": [(0.4, "kg", "8er Pack", 8), (1.0, "kg", "20er Pack", 20)],
    "pork_sausage_thueringer": [(0.4, "kg", "4er Pack", 4), (0.5, "kg", "5er Pack", 5),
                                 (1.0, "kg", "10er Pack", 10)],
    "pork_sausage_krakauer": [(0.3, "kg", "2er Pack", 2), (0.6, "kg", "4er Pack", 4)],
    "beef_sausage": [(0.4, "kg", "4er Pack", 4), (1.0, "kg", "10er Pack", 10)],
}


def _generate_purchase_skus() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for iid, ing in INGREDIENTS_BY_ID.items():
        if not ing["purchasable"]:
            continue
        entries = _PURCHASE_SKU_OVERRIDES.get(iid) or _FAMILY_SKU_TEMPLATES.get(ing["family"])
        if not entries:
            continue
        result[iid] = [dict(size=size, unit=unit, pack_label=label, pack_count=count)
                        for size, unit, label, count in entries]
    return result


PURCHASE_SKUS_RAW: dict[str, list[dict]] = _generate_purchase_skus()

# Zusätzliche Catering-Gebinde für stark genutzte Saucen
PURCHASE_SKUS_RAW["ketchup"].append(
    dict(size=0.875, unit="l", pack_label="Catering-Flasche 875ml", pack_count=1))
PURCHASE_SKUS_RAW["mayonnaise"].append(
    dict(size=0.875, unit="l", pack_label="Catering-Flasche 875ml", pack_count=1))


# --- VALIDIERUNG & WRITER --------------------------------------------------------


def build_catalog() -> dict:
    return dict(
        ingredients=INGREDIENTS_BY_ID,
        direct_consumables={d["id"]: d for d in DIRECT_CONSUMABLES_RAW},
        recipes={r["id"]: r for r in ALL_RECIPES_RAW},
        modifiers={m["id"]: m for m in MODIFIERS_RAW},
        aliases=ALIASES_RAW,
        substitution_rules=SUBSTITUTION_RULES_RAW,
        production_rules=PRODUCTION_RULES_RAW,
        purchase_skus=PURCHASE_SKUS_RAW,
    )


def _serialize_recommendation(meta) -> dict:
    """Wandelt ein RecommendationMetadata-Objekt in ein JSON-taugliches dict um
    (tags: set -> sortierte Liste, restliche Felder sind bereits JSON-safe)."""
    d = asdict(meta)
    d["tags"] = sorted(meta.tags)
    return d


def _apply_recommendations(cat: dict) -> None:
    """Reichert jedes Ingredient/DirectConsumable/Recipe um ein
    ``recommendation``-Feld an (§4/§81 der Recommendation-Spec). Rein additiv:
    schreibt ausschließlich den neuen "recommendation"-Key in die bereits
    gebauten Rohdicts, rührt keine demand-relevanten Felder an.

    Ingredients zuerst (unabhängig), danach DirectConsumables/Recipes, die für
    die Ableitung ein (partielles) PartyCatalog mit den fertigen Ingredient-
    Objekten benötigen (§81: Vererbung über Ingredient-Family/-Eigenschaften).
    """
    ingredient_objs = {iid: Ingredient(**row) for iid, row in cat["ingredients"].items()}
    partial_catalog = PartyCatalog(ingredients=ingredient_objs)

    for iid, ing_obj in ingredient_objs.items():
        meta = apply_recommendation_metadata(ing_obj, partial_catalog)
        cat["ingredients"][iid]["recommendation"] = _serialize_recommendation(meta)

    for did, row in cat["direct_consumables"].items():
        dc_obj = DirectConsumable(**row)
        meta = apply_recommendation_metadata(dc_obj, partial_catalog)
        cat["direct_consumables"][did]["recommendation"] = _serialize_recommendation(meta)

    for rid, row in cat["recipes"].items():
        row_copy = dict(row)
        components_raw = row_copy.pop("components", [])
        components = [RecipeComponent(**c) for c in components_raw]
        recipe_obj = Recipe(components=components, **row_copy)
        meta = apply_recommendation_metadata(recipe_obj, partial_catalog)
        cat["recipes"][rid]["recommendation"] = _serialize_recommendation(meta)


def _validate_catalog(cat: dict) -> None:
    """Prüft referenzielle Integrität über alle Katalogteile hinweg."""
    ing_ids = set(cat["ingredients"].keys())
    dc_ids = set(cat["direct_consumables"].keys())
    recipe_ids = set(cat["recipes"].keys())
    modifier_ids = set(cat["modifiers"].keys())
    all_item_ids = ing_ids | dc_ids | recipe_ids

    for a in cat["aliases"]:
        tt, tid = a["target_type"], a["target_id"]
        if tt == "ingredient":
            assert tid in ing_ids, f"Alias {a['alias_text']!r}: unbekanntes ingredient {tid!r}"
        elif tt == "direct_consumable":
            assert tid in dc_ids, f"Alias {a['alias_text']!r}: unbekannter direct_consumable {tid!r}"
        elif tt == "recipe":
            assert tid in recipe_ids, f"Alias {a['alias_text']!r}: unbekanntes recipe {tid!r}"
        elif tt == "modifier":
            assert tid in modifier_ids, f"Alias {a['alias_text']!r}: unbekannter modifier {tid!r}"
        else:
            raise AssertionError(f"Alias {a['alias_text']!r}: unbekannter target_type {tt!r}")

    for s in cat["substitution_rules"]:
        assert s["from_id"] in all_item_ids, f"SubstitutionRule: unbekannte from_id {s['from_id']!r}"
        assert s["to_id"] in all_item_ids, f"SubstitutionRule: unbekannte to_id {s['to_id']!r}"

    for p in cat["production_rules"]:
        assert p["output_ingredient_id"] in ing_ids, \
            f"ProductionRule: unbekannte output_ingredient_id {p['output_ingredient_id']!r}"
        for inp in p["inputs"]:
            assert inp["ingredient_id"] in ing_ids, \
                f"ProductionRule: unbekannte input ingredient_id {inp['ingredient_id']!r}"

    for m in cat["modifiers"].values():
        if m["target_ingredient_id"]:
            assert m["target_ingredient_id"] in ing_ids, \
                f"Modifier {m['id']!r}: unbekannte target_ingredient_id {m['target_ingredient_id']!r}"

    for iid in cat["purchase_skus"]:
        assert iid in ing_ids, f"PurchaseSKU: unbekannte ingredient_id {iid!r}"

    # §70: Jedes direkt wählbare Item (DirectConsumable/Recipe) braucht
    # mindestens 2 Recommendation-Tags, ausschließlich aus tags.ALL_TAGS.
    offenders = []
    for group in ("direct_consumables", "recipes"):
        for iid, row in cat[group].items():
            rec = row.get("recommendation") or {}
            item_tags = rec.get("tags", [])
            invalid = validate_tags(item_tags)
            if len(item_tags) < 2 or invalid:
                offenders.append((group, iid, len(item_tags), invalid))
    if offenders:
        preview = offenders[:20]
        detail = "\n".join(
            f"  - {group}/{iid}: {n_tags} tag(s), invalid={invalid}"
            for group, iid, n_tags, invalid in preview
        )
        raise AssertionError(
            f"§70 Recommendation-Tag-Coverage verletzt für {len(offenders)} Item(e) "
            f"(mind. 2 Tags aus tags.ALL_TAGS erforderlich). Erste {len(preview)}:\n{detail}"
        )


def write_catalog(cat: dict) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "ingredients.json": cat["ingredients"],
        "direct_consumables.json": cat["direct_consumables"],
        "recipes.json": cat["recipes"],
        "modifiers.json": cat["modifiers"],
        "aliases.json": cat["aliases"],
        "substitution_rules.json": cat["substitution_rules"],
        "production_rules.json": cat["production_rules"],
        "purchase_skus.json": cat["purchase_skus"],
    }
    for filename, payload in files.items():
        with open(CATALOG_DIR / filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    catalog = build_catalog()
    _apply_recommendations(catalog)
    _validate_catalog(catalog)
    write_catalog(catalog)

    print("=== Katalog-Generierung abgeschlossen ===")
    print(f"Ingredients:            {len(catalog['ingredients'])}")
    print(f"Direct Consumables:     {len(catalog['direct_consumables'])}")
    print(f"Recipes (gesamt):       {len(catalog['recipes'])}")
    print(f"  davon Cocktails:      {len(COCKTAILS_RAW)}")
    print(f"  davon Food:           {len(FOOD_RAW)}")
    print(f"  davon Sonstige:       {len(MISC_RECIPES_RAW)}")
    print(f"Modifiers:              {len(catalog['modifiers'])}")
    print(f"Aliases:                {len(catalog['aliases'])}")
    print(f"Substitution Rules:     {len(catalog['substitution_rules'])}")
    print(f"Production Rules:       {len(catalog['production_rules'])}")
    print(f"Purchase SKUs (# Ingredients mit Gebinde): {len(catalog['purchase_skus'])}")
    print(f"Catalog-Dateien geschrieben nach: {CATALOG_DIR}")
