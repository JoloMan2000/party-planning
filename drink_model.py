"""
Gruppenbasiertes Getränke-Demand-Allocation-Modell
====================================================

Ersetzt die naive "1 Auswahl = 1 volle Portion pro Person"-Rechnung durch ein
Modell, in dem eine Getränke-Stimme eine PRÄFERENZ ist, die sich mit den
übrigen Präferenzen desselben Gastes ein festes "Choice-Budget" teilt.

Alle Zahlen-Parameter sind hier zentral als Konstanten definiert (siehe
Abschnitt "KONFIGURATION") und werden nirgends in der Berechnungslogik
hardcodiert.

Designentscheidungen, die die Spezifikation offen ließ, sind jeweils mit
"Designentscheidung:" kommentiert.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# ============================================================================
# KONFIGURATION (zentral, änderbar, nicht in der Logik hardcodiert)
# ============================================================================

WATER_L_PER_GUEST = 1.5
CHOICE_UNITS_PER_GUEST = 3.5
MAX_ALCOHOL_CHOICE_UNITS_PER_GUEST = 2.0
MAX_ENERGY_CHOICE_UNITS_PER_GUEST = 1.0

# Gewichtung von Präferenzquellen (Choice-Budget-Konkurrenz, NICHT Confidence)
WEIGHT_SELECTION = 1.0
WEIGHT_FREETEXT_RECOGNIZED = 1.25
WEIGHT_FREETEXT_SPECIFIC = 1.35

# Confidence-Schwellen für die Freitext-Zuordnung
CONFIDENCE_AUTO = 0.90
CONFIDENCE_REVIEW_LOW = 0.75

# Designentscheidung: Substitutionsstärke zwischen Getränkefamilien/-varianten
# steuert die PRIORITÄT bei der Overflow-Umverteilung (Schritt 8), nicht die
# Grundallokation. Werte: strong=1.0, medium=0.6, partial=0.5, weak=0.3.
SUBSTITUTION_STRENGTH: dict[frozenset, float] = {
    frozenset({"Rotwein", "Weißwein"}): 1.0,
    frozenset({"Cola", "Cola Zero"}): 1.0,
    frozenset({"Cola", "Fanta"}): 0.6,
    frozenset({"Cola", "Sprite"}): 0.6,
    frozenset({"Fanta", "Sprite"}): 0.6,
    frozenset({"Bier", "Alkoholfreies Bier"}): 0.5,
    frozenset({"Bier", "Rotwein"}): 0.3,
    frozenset({"Bier", "Weißwein"}): 0.3,
}
SUBSTITUTION_DEFAULT_SAME_FAMILY = 0.4
SUBSTITUTION_DEFAULT_CROSS_FAMILY = 0.15

# Reserven (werden erst NACH der Gruppen-Summierung angewendet)
RESERVE_PCT: dict[str, float] = {
    "water": 0.15,
    "softdrink": 0.10,
    "juice_schorle": 0.10,
    "alcohol_free_beer": 0.10,
    "beer": 0.05,
    "wine": 0.05,
    "sparkling_wine": 0.05,
    "spirits": 0.05,
    "energy": 0.05,
    "mixer": 0.10,
}
DEFAULT_RESERVE_PCT = 0.10


@dataclass(frozen=True)
class CanonicalDrink:
    canonical_name: str
    family: str
    portion_l: float  # Choice-Portionsgröße in Litern (Konsumeinheit)
    alcoholic: bool
    is_energy: bool = False
    purchase_unit_l: float = 1.0  # Größe eines Einkaufsgebindes in Litern
    purchase_unit_label: str = "Liter"


# ----------------------------------------------------------------------------
# Kanonische Getränke-Registrierung
#
# Deckt sowohl die Multiselect-Optionen der App als auch alle per Freitext
# erreichbaren Getränke (inkl. Composite-Zutaten) ab.
# ----------------------------------------------------------------------------
CANONICAL_DRINKS: dict[str, CanonicalDrink] = {
    "Bier": CanonicalDrink("Bier", "beer", 0.50, alcoholic=True,
                            purchase_unit_l=10.0, purchase_unit_label="Kasten (20x0,5l)"),
    "Alkoholfreies Bier": CanonicalDrink("Alkoholfreies Bier", "beer", 0.50, alcoholic=False,
                                          purchase_unit_l=10.0, purchase_unit_label="Kasten (20x0,5l)"),
    "Rotwein": CanonicalDrink("Rotwein", "wine", 0.15, alcoholic=True,
                               purchase_unit_l=0.75, purchase_unit_label="Flasche (0,75l)"),
    "Weißwein": CanonicalDrink("Weißwein", "wine", 0.15, alcoholic=True,
                                purchase_unit_l=0.75, purchase_unit_label="Flasche (0,75l)"),
    "Sekt": CanonicalDrink("Sekt", "sparkling_wine", 0.15, alcoholic=True,
                            purchase_unit_l=0.75, purchase_unit_label="Flasche (0,75l)"),
    "Cola": CanonicalDrink("Cola", "softdrink", 0.33, alcoholic=False,
                            purchase_unit_l=1.5, purchase_unit_label="Flasche (1,5l)"),
    "Cola Zero": CanonicalDrink("Cola Zero", "softdrink", 0.33, alcoholic=False,
                                 purchase_unit_l=1.5, purchase_unit_label="Flasche (1,5l)"),
    "Fanta": CanonicalDrink("Fanta", "softdrink", 0.33, alcoholic=False,
                             purchase_unit_l=1.5, purchase_unit_label="Flasche (1,5l)"),
    "Sprite": CanonicalDrink("Sprite", "softdrink", 0.33, alcoholic=False,
                              purchase_unit_l=1.5, purchase_unit_label="Flasche (1,5l)"),
    "Spezi": CanonicalDrink("Spezi", "softdrink", 0.33, alcoholic=False,
                             purchase_unit_l=1.5, purchase_unit_label="Flasche (1,5l)"),
    "Apfelschorle": CanonicalDrink("Apfelschorle", "juice_schorle", 0.33, alcoholic=False,
                                    purchase_unit_l=1.0, purchase_unit_label="Flasche (1,0l)"),
    "Saftschorle": CanonicalDrink("Saftschorle", "juice_schorle", 0.33, alcoholic=False,
                                   purchase_unit_l=1.0, purchase_unit_label="Flasche (1,0l)"),
    "Saft": CanonicalDrink("Saft", "juice_schorle", 0.33, alcoholic=False,
                            purchase_unit_l=1.0, purchase_unit_label="Flasche (1,0l)"),
    "Red Bull": CanonicalDrink("Red Bull", "energy", 0.25, alcoholic=False, is_energy=True,
                                purchase_unit_l=0.25, purchase_unit_label="Dose (0,25l)"),
    "Gin": CanonicalDrink("Gin", "spirits", 0.04, alcoholic=True,
                           purchase_unit_l=0.70, purchase_unit_label="Flasche (0,7l)"),
    "Vodka": CanonicalDrink("Vodka", "spirits", 0.04, alcoholic=True,
                             purchase_unit_l=0.70, purchase_unit_label="Flasche (0,7l)"),
    "Aperol": CanonicalDrink("Aperol", "spirits", 0.09, alcoholic=True,
                              purchase_unit_l=0.70, purchase_unit_label="Flasche (0,7l)"),
    "Tonic Water": CanonicalDrink("Tonic Water", "mixer", 0.15, alcoholic=False,
                                   purchase_unit_l=1.0, purchase_unit_label="Flasche (1,0l)"),
    "Soda": CanonicalDrink("Soda", "mixer", 0.03, alcoholic=False,
                            purchase_unit_l=1.0, purchase_unit_label="Flasche (1,0l)"),
}

# Getränke, die im Choice-Budget mitkonkurrieren (Wasser ausgenommen, s.u.)
WATER_CANONICAL_NAME = "Wasser"

# ----------------------------------------------------------------------------
# Composite-Drink-Rezepte: 1 Serving -> Liter je Zutat (kanonischer Name)
#
# Designentscheidung: realistische Standard-Rezeptmengen, zentral konfigurierbar.
# ----------------------------------------------------------------------------
COMPOSITE_RECIPES: dict[str, dict[str, float]] = {
    "Gin Tonic": {"Gin": 0.04, "Tonic Water": 0.15},
    "Vodka Red Bull": {"Vodka": 0.04, "Red Bull": 0.25},
    "Aperol Spritz": {"Aperol": 0.09, "Sekt": 0.09, "Soda": 0.03},
}
COMPOSITE_FAMILY = "composite_cocktail"
COMPOSITE_ALCOHOLIC = {"Gin Tonic": True, "Vodka Red Bull": True, "Aperol Spritz": True}
COMPOSITE_IS_ENERGY = {"Gin Tonic": False, "Vodka Red Bull": True, "Aperol Spritz": False}


# ============================================================================
# FREITEXT-NORMALISIERUNG
# ============================================================================


def _normalize_text(raw: str) -> str:
    """Schritt 1 der Pipeline: trim/lowercase + Diakritika-tolerante Form."""
    text = raw.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


@dataclass(frozen=True)
class AliasResult:
    canonical_name: str | None  # None nur für vollständig unbekannte Angaben
    family: str | None
    confidence: float
    specific: bool  # steuert Choice-Gewicht 1.25 vs 1.35
    is_composite: bool = False
    composite_incomplete: bool = False  # z.B. "Gin" ohne Mixer


# Alias -> (canonical_name, confidence, specific)
# Designentscheidung: deterministische Alias-Tabelle statt Fuzzy-Matching,
# da für einen privaten Fragebogen ausreichend und deterministisch testbar.
_ALIASES: list[tuple[re.Pattern, str, float, bool]] = [
    (re.compile(r"\b(coke|coca[- ]?cola|cola)\b"), "Cola", 0.95, True),
    (re.compile(r"\bcola[- ]?zero\b|\bcola[- ]?light\b"), "Cola Zero", 0.95, True),
    (re.compile(r"\bfanta\b"), "Fanta", 0.95, True),
    (re.compile(r"\bsprite\b"), "Sprite", 0.95, True),
    (re.compile(r"\bspezi\b"), "Spezi", 0.95, True),
    (re.compile(r"\bapfelschorle\b"), "Apfelschorle", 0.95, True),
    (re.compile(r"\b\w+schorle\b"), "Saftschorle", 0.90, True),
    (re.compile(r"\bschorle\b"), "Saftschorle", 0.80, False),
    (re.compile(r"\b(saft|orangensaft|o-saft|apfelsaft)\b"), "Saft", 0.85, False),
    (re.compile(r"\b(radler)\b"), "Bier", 0.95, True),
    (re.compile(r"\balkoholfreies?\s*bier\b|\bbier\s*alkoholfrei\b"), "Alkoholfreies Bier", 0.95, True),
    (re.compile(r"\bbier\b"), "Bier", 0.90, False),
    (re.compile(r"\b(rotwein|red\s*wine)\b"), "Rotwein", 0.95, True),
    (re.compile(r"\b(weißwein|weisswein|white\s*wine)\b"), "Weißwein", 0.95, True),
    (re.compile(r"\bwein\b"), "Rotwein", 0.80, False),
    (re.compile(r"\b(prosecco|sekt)\b"), "Sekt", 0.95, True),
    (re.compile(r"\b(red\s*bull|redbull)\b"), "Red Bull", 0.95, True),
    (re.compile(r"\bwasser\b"), WATER_CANONICAL_NAME, 0.95, True),
    (re.compile(r"\btonic(\s*water)?\b"), "Tonic Water", 0.90, True),
    (re.compile(r"\bsoda\b"), "Soda", 0.85, True),
    (re.compile(r"\baperol\b"), "Aperol", 0.85, True),
    (re.compile(r"\bvodka\b"), "Vodka", 0.80, False),
    (re.compile(r"\bgin\b"), "Gin", 0.80, False),
]

_COMPOSITE_ALIASES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\bgin[\s-]*tonic\b"), "Gin Tonic", 0.95),
    (re.compile(r"\bvodka[\s-]*red\s*bull\b"), "Vodka Red Bull", 0.95),
    (re.compile(r"\baperol[\s-]*spritz\b"), "Aperol Spritz", 0.95),
]


def resolve_freetext_item(raw_text: str) -> AliasResult:
    """
    Führt Schritte 1-6 der Freitext-Pipeline für EIN einzelnes, bereits durch
    Komma getrenntes Freitext-Item aus.
    """
    text = _normalize_text(raw_text)
    if not text:
        return AliasResult(None, None, 0.0, False)

    # Composite-Erkennung zuerst (Schritt 5), da spezifischer als Einzelbegriffe
    for pattern, composite_name, confidence in _COMPOSITE_ALIASES:
        if pattern.search(text):
            return AliasResult(
                canonical_name=composite_name,
                family=COMPOSITE_FAMILY,
                confidence=confidence,
                specific=True,
                is_composite=True,
            )

    # Einzel-Alias-Erkennung (Schritte 2-4)
    for pattern, canonical_name, confidence, specific in _ALIASES:
        if pattern.search(text):
            drink = CANONICAL_DRINKS.get(canonical_name)
            family = drink.family if drink else ("water" if canonical_name == WATER_CANONICAL_NAME else None)
            # "Gin"/"Vodka" allein = unvollständiger Composite-Wunsch (kein Mixer erfinden)
            composite_incomplete = canonical_name in ("Gin", "Vodka") and not any(
                p.search(text) for p, _, _ in _COMPOSITE_ALIASES
            )
            return AliasResult(
                canonical_name=canonical_name,
                family=family,
                confidence=confidence,
                specific=specific,
                composite_incomplete=composite_incomplete,
            )

    # Schritt 7: unbekannte Angaben NIEMALS verwerfen -> als unresolved markieren
    return AliasResult(None, None, 0.55, False)


def parse_freetext_field(freetext: str) -> list[tuple[str, AliasResult]]:
    """Zerlegt ein kommagetrenntes Freitextfeld und löst jedes Item auf."""
    if not freetext:
        return []
    results = []
    for raw_item in freetext.split(","):
        raw_item = raw_item.strip()
        if not raw_item:
            continue
        results.append((raw_item, resolve_freetext_item(raw_item)))
    return results


# ============================================================================
# HILFSFUNKTIONEN: Portionsgrößen, Alkohol/Energy-Flags, Substitution
# ============================================================================


def get_portion_liters(name: str) -> float:
    drink = CANONICAL_DRINKS.get(name)
    if drink is not None:
        return drink.portion_l
    if name in COMPOSITE_RECIPES:
        return sum(COMPOSITE_RECIPES[name].values())
    return 1.0


def _is_alcoholic(name: str) -> bool:
    if name in COMPOSITE_RECIPES:
        return COMPOSITE_ALCOHOLIC.get(name, False)
    drink = CANONICAL_DRINKS.get(name)
    return drink.alcoholic if drink else False


def _is_energy(name: str) -> bool:
    if name in COMPOSITE_RECIPES:
        return COMPOSITE_IS_ENERGY.get(name, False)
    drink = CANONICAL_DRINKS.get(name)
    return drink.is_energy if drink else False


def _family_of(name: str) -> str:
    if name in COMPOSITE_RECIPES:
        return COMPOSITE_FAMILY
    drink = CANONICAL_DRINKS.get(name)
    return drink.family if drink else "unknown"


def _substitution_strength(name_a: str, family_a: str, name_b: str, family_b: str) -> float:
    key = frozenset({name_a, name_b})
    if key in SUBSTITUTION_STRENGTH:
        return SUBSTITUTION_STRENGTH[key]
    if family_a == family_b:
        return SUBSTITUTION_DEFAULT_SAME_FAMILY
    return SUBSTITUTION_DEFAULT_CROSS_FAMILY


def _purchase_unit(name: str) -> tuple[float, str]:
    if name == WATER_CANONICAL_NAME:
        return WATER_PURCHASE_UNIT_L, WATER_PURCHASE_UNIT_LABEL
    drink = CANONICAL_DRINKS.get(name)
    if drink:
        return drink.purchase_unit_l, drink.purchase_unit_label
    return 1.0, "Liter"


WATER_PURCHASE_UNIT_L = 9.0
WATER_PURCHASE_UNIT_LABEL = "6er-Pack (1,5l)"


# ============================================================================
# PRÄFERENZ-MODELL PRO GAST (Schritte 1-3 der Freitext-Vereinheitlichung)
# ============================================================================


@dataclass
class Preference:
    canonical_name: str
    family: str
    weight: float
    source: str  # "selection" | "freetext" | "both"
    confidence: float
    needs_review: bool
    alcoholic: bool
    is_energy: bool
    is_composite: bool = False


@dataclass
class UnresolvedFreetext:
    guest_name: str
    raw_text: str


def build_guest_preferences(
    guest_name: str,
    selected_options: list[str],
    freetext: str,
    unresolved_out: list[UnresolvedFreetext],
    hints_out: list[str],
) -> list[Preference]:
    """Schritte 1-3: Multiselect + Freitext vereinheitlichen, deduplizieren,
    Gewichte anwenden."""
    prefs_by_name: dict[str, Preference] = {}

    def add(canonical_name, family, weight, source, confidence, needs_review, alcoholic, energy, is_composite):
        existing = prefs_by_name.get(canonical_name)
        if existing is None:
            prefs_by_name[canonical_name] = Preference(
                canonical_name, family, weight, source, confidence, needs_review, alcoholic, energy, is_composite
            )
        elif weight > existing.weight:
            new_source = "both" if existing.source != source else source
            prefs_by_name[canonical_name] = Preference(
                canonical_name, family, weight, new_source, confidence, needs_review, alcoholic, energy, is_composite
            )
        elif existing.source != source:
            existing.source = "both"

    for option in selected_options:
        drink = CANONICAL_DRINKS.get(option)
        if drink is None:
            continue  # z.B. "Wasser": Grundversorgung, nicht Teil des Choice-Budgets
        add(option, drink.family, WEIGHT_SELECTION, "selection", 1.0, False, drink.alcoholic, drink.is_energy, False)

    for raw_text, result in parse_freetext_field(freetext):
        if result.canonical_name is None:
            unresolved_out.append(UnresolvedFreetext(guest_name, raw_text))
            continue
        weight = WEIGHT_FREETEXT_SPECIFIC if result.specific else WEIGHT_FREETEXT_RECOGNIZED
        needs_review = result.confidence < CONFIDENCE_AUTO
        if needs_review:
            hints_out.append(
                f'"{raw_text}" ({guest_name}) wurde als "{result.canonical_name}" interpretiert '
                f"(Confidence {result.confidence:.2f}) – bitte prüfen."
            )
        add(
            result.canonical_name,
            result.family or _family_of(result.canonical_name),
            weight,
            "freetext",
            result.confidence,
            needs_review,
            _is_alcoholic(result.canonical_name),
            _is_energy(result.canonical_name),
            result.is_composite,
        )

    return list(prefs_by_name.values())


# ============================================================================
# ALLOKATIONS-ALGORITHMUS PRO GAST (Schritte 4-11)
# ============================================================================


def allocate_guest(preferences: list[Preference]) -> tuple[dict[str, float], float, dict[str, dict]]:
    """
    Verteilt das Choice-Budget eines Gasts auf seine Präferenzen und löst
    Composite-Drinks in Einkaufszutaten auf.

    Rückgabe:
        drink_liters:  kanonischer Name (einkaufbares Produkt) -> Liter
        water_liters:  Wasserbedarf dieses Gasts in Litern (Basis + ggf. Overflow)
        meta:          kanonischer Name -> {"sources", "confidence", "needs_review"}
    """
    water_liters = WATER_L_PER_GUEST  # Schritt 4: Grundversorgung, unabhängig von Auswahl
    drink_liters: dict[str, float] = {}
    meta: dict[str, dict] = {}

    def record_meta(name: str, pref: Preference) -> None:
        m = meta.setdefault(name, {"sources": set(), "confidence": 1.0, "needs_review": False})
        if pref.source == "both":
            m["sources"].update({"selection", "freetext"})
        else:
            m["sources"].add(pref.source)
        m["confidence"] = min(m["confidence"], pref.confidence)
        m["needs_review"] = m["needs_review"] or pref.needs_review

    # Wasser nimmt nicht am Choice-Budget teil (siehe WICHTIG in der Spezifikation)
    non_water = [p for p in preferences if p.canonical_name != WATER_CANONICAL_NAME]
    if not non_water:
        return drink_liters, water_liters, meta

    pref_by_name = {p.canonical_name: p for p in non_water}

    # Schritte 5-6: Gewichte normalisieren, auf 3.5 Choice Units verteilen
    total_weight = sum(p.weight for p in non_water)
    choice_units = {p.canonical_name: (p.weight / total_weight) * CHOICE_UNITS_PER_GUEST for p in non_water}
    for name, pref in pref_by_name.items():
        record_meta(name, pref)

    # Schritt 7: Kategorie-Constraints (Alkohol, Energy) anwenden
    def cap_category(member_filter, max_units: float) -> dict[str, float]:
        members = [n for n in choice_units if member_filter(n)]
        total = sum(choice_units[n] for n in members)
        if total <= max_units or total <= 0:
            return {}
        scale = max_units / total
        overflow = {}
        for n in members:
            original = choice_units[n]
            reduced = original * scale
            overflow[n] = original - reduced
            choice_units[n] = reduced
        return overflow

    alcohol_overflow = cap_category(lambda n: pref_by_name[n].alcoholic, MAX_ALCOHOL_CHOICE_UNITS_PER_GUEST)
    energy_overflow = cap_category(lambda n: pref_by_name[n].is_energy, MAX_ENERGY_CHOICE_UNITS_PER_GUEST)

    # Schritte 8-10: Überschuss auf gewählte alkoholfreie Alternativen umverteilen,
    # sonst dem Wasserbedarf zuschlagen. Nie alkoholfrei -> Alkohol.
    def redistribute(overflow: dict[str, float], exclude_energy: bool) -> None:
        nonlocal water_liters
        for source_name, over_units in overflow.items():
            if over_units <= 0:
                continue
            vol = over_units * get_portion_liters(source_name)
            candidates = [
                n
                for n, p in pref_by_name.items()
                if not p.alcoholic and n != source_name and (not exclude_energy or not p.is_energy)
            ]
            if not candidates:
                water_liters += vol  # Schritt 9: keine passende Alternative -> Wasser
                continue
            source_family = pref_by_name[source_name].family
            weights = {
                c: max(choice_units.get(c, 0.0), 1e-6)
                * _substitution_strength(source_name, source_family, c, pref_by_name[c].family)
                for c in candidates
            }
            total_w = sum(weights.values()) or 1.0
            for c in candidates:
                extra_liters = vol * (weights[c] / total_w)
                choice_units[c] = choice_units.get(c, 0.0) + extra_liters / get_portion_liters(c)

    redistribute(alcohol_overflow, exclude_energy=False)
    redistribute(energy_overflow, exclude_energy=True)

    # Schritt 11 (Vorbereitung): Choice Units in Liter umrechnen, Composites auflösen
    for name, units in choice_units.items():
        if units <= 0:
            continue
        if name in COMPOSITE_RECIPES:
            for ingredient, per_serving_l in COMPOSITE_RECIPES[name].items():
                drink_liters[ingredient] = drink_liters.get(ingredient, 0.0) + units * per_serving_l
                record_meta(ingredient, pref_by_name[name])
        else:
            drink_liters[name] = drink_liters.get(name, 0.0) + units * get_portion_liters(name)

    return drink_liters, water_liters, meta


# ============================================================================
# GRUPPEN-AGGREGATION, RESERVEN, EINKAUFS-RUNDUNG, OUTPUT (Schritte 12-15)
# ============================================================================


@dataclass
class DrinkResult:
    canonical_name: str
    family: str
    number_of_supporting_guests: int
    weighted_preference_score: float
    calculated_quantity_l: float
    reserve_percentage: float
    quantity_after_reserve_l: float
    purchase_unit: str
    purchase_count: int
    actual_purchase_quantity_l: float
    source: str  # "selection" | "freetext" | "both"
    confidence: float
    needs_review: bool
    explanation: str


@dataclass
class ShoppingListResult:
    guest_count: int
    water: DrinkResult
    drinks: list[DrinkResult]
    unresolved_freetext: list[UnresolvedFreetext]
    admin_hints: list[str]


def _aggregate_source(sources: set) -> str:
    if len(sources) >= 2:
        return "both"
    return next(iter(sources)) if sources else "selection"


def _build_drink_result(
    name: str,
    family: str,
    supporting_guests: int,
    liters: float,
    agg_meta: dict,
) -> DrinkResult:
    portion_l = get_portion_liters(name)
    weighted_score = liters / portion_l if portion_l else 0.0

    reserve_pct = RESERVE_PCT.get(family, DEFAULT_RESERVE_PCT)
    after_reserve = liters * (1 + reserve_pct)

    unit_l, unit_label = _purchase_unit(name)
    purchase_count = max(1, math.ceil(after_reserve / unit_l)) if after_reserve > 0 else 0
    actual = purchase_count * unit_l

    source = _aggregate_source(agg_meta["sources"])
    confidence = agg_meta["confidence"]
    needs_review = agg_meta["needs_review"]

    explanation = (
        f"{supporting_guests} Gast/Gäste möchten {name}. "
        f"Roh-Bedarf {liters:.2f} l, +{reserve_pct * 100:.0f}% Reserve = {after_reserve:.2f} l, "
        f"aufgerundet auf {purchase_count} × {unit_label} = {actual:.2f} l."
    )

    return DrinkResult(
        canonical_name=name,
        family=family,
        number_of_supporting_guests=supporting_guests,
        weighted_preference_score=round(weighted_score, 2),
        calculated_quantity_l=round(liters, 2),
        reserve_percentage=reserve_pct,
        quantity_after_reserve_l=round(after_reserve, 2),
        purchase_unit=unit_label,
        purchase_count=purchase_count,
        actual_purchase_quantity_l=round(actual, 2),
        source=source,
        confidence=round(confidence, 2),
        needs_review=needs_review,
        explanation=explanation,
    )


def compute_drink_shopping_list(guests: list[dict]) -> ShoppingListResult:
    """
    Top-Level-Einstiegspunkt: erwartet eine Liste von Gast-Dicts mit den
    Feldern "name" (str), "drinks" (list[str], Multiselect) und
    "drinks_freetext" (str).

    Führt für jeden Gast Schritte 1-11 aus und aggregiert danach
    gruppenweise (Schritte 12-15: Summierung, Reserve, Einkaufsrundung).
    """
    unresolved: list[UnresolvedFreetext] = []
    hints: list[str] = []

    total_water_l = 0.0
    totals: dict[str, float] = {}
    supporters: dict[str, set] = {}
    meta_agg: dict[str, dict] = {}

    guest_count = len(guests)

    for guest in guests:
        guest_name = guest.get("name", "Unbekannt")
        selected_options = guest.get("drinks") or []
        freetext = guest.get("drinks_freetext") or ""

        prefs = build_guest_preferences(guest_name, selected_options, freetext, unresolved, hints)
        drink_liters, water_liters, meta = allocate_guest(prefs)

        total_water_l += water_liters

        for name, liters in drink_liters.items():
            if liters <= 0:
                continue
            totals[name] = totals.get(name, 0.0) + liters
            supporters.setdefault(name, set()).add(guest_name)

            agg = meta_agg.setdefault(name, {"sources": set(), "confidence": 1.0, "needs_review": False})
            m = meta.get(name, {"sources": {"selection"}, "confidence": 1.0, "needs_review": False})
            agg["sources"].update(m["sources"])
            agg["confidence"] = min(agg["confidence"], m["confidence"])
            agg["needs_review"] = agg["needs_review"] or m["needs_review"]

    water_result = _build_drink_result(
        WATER_CANONICAL_NAME,
        "water",
        guest_count,
        total_water_l,
        {"sources": {"selection"}, "confidence": 1.0, "needs_review": False},
    )

    drink_results = [
        _build_drink_result(
            name,
            _family_of(name),
            len(supporters[name]),
            liters,
            meta_agg[name],
        )
        for name, liters in totals.items()
    ]
    drink_results.sort(key=lambda r: r.canonical_name)

    return ShoppingListResult(
        guest_count=guest_count,
        water=water_result,
        drinks=drink_results,
        unresolved_freetext=unresolved,
        admin_hints=hints,
    )
