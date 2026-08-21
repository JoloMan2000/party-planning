"""
Legacy-Adapter (AUFGABE §42)
============================

Konvertiert bestehende SQLite ``responses``-Zeilen in das neue
``GuestResponse``-Domain-Modell.

Hintergrund: VOR dieser Änderung speicherte "Party Planning.py" in den
Spalten ``drinks``/``food`` JSON-Listen der alten, fest codierten
Options-Strings (``DRINK_OPTIONS``/``FOOD_OPTIONS``, siehe unten als
``LEGACY_DRINK_OPTIONS``/``LEGACY_FOOD_OPTIONS`` eingefroren). AB dieser
Änderung speichert exakt dieselbe Spalte (kein Schema-Wechsel, weiterhin
JSON-Listen von Strings) direkt Katalog-IDs (z.B. ``"beer_pils"`` statt
``"Bier"``).

Dieses Modul bleibt bewusst Streamlit-frei (siehe party_engine/-Constraint) -
es enthält reine Konvertierungslogik und wird von "Party Planning.py"
importiert.

Designentscheidung (Mapping alte Kategorie -> repräsentative Katalog-ID):
Die alten Freitext-Kategorien "Grillfleisch" / "Vegetarisch/Vegan" / "Salate"
/ "Snacks/Chips" waren bewusst grob und lassen sich NICHT verlustfrei in ein
historisch "korrektes" Einzelgericht zurückrechnen (wir wissen nicht, welches
konkrete Gericht ein Gast vor dieser Änderung tatsächlich meinte). Es wird
daher je Kategorie EIN sinnvoller, im Katalog tatsächlich existierender
Vertreter gewählt (siehe ``LEGACY_FOOD_TO_CATALOG_ID``/``LEGACY_DRINK_TO_
CATALOG_ID`` unten - jede ID wurde vor Verwendung gegen
``catalog/direct_consumables.json``/``catalog/recipes.json`` geprüft).

Designentscheidung (Red Bull ohne Markenpräferenz): Das Domain-Modell
transportiert eine Markenpräferenz (``brand``) nur über ``ResolutionResult``
(Freitext-Pfad), NICHT über einfache Katalog-ID-Selektionen
(``GuestResponse.drink_selections`` ist eine reine ID-Liste). Da die alte
Multiselect-Auswahl "Red Bull" eine reine Selektion (kein Freitext) war, wird
sie auf ``energy_drink_generic`` ohne Markenpräferenz abgebildet - eine exakte
Marken-Rekonstruktion ist über den Selektions-Pfad architektonisch nicht
vorgesehen und für eine Mengen-/Einkaufsberechnung auch nicht notwendig.
"""

from __future__ import annotations

import json

from party_engine.domain import DietaryProfile, GuestResponse, PartyCatalog

# --- Eingefrorene alte Optionslisten (siehe historische "Party Planning.py") ---

LEGACY_DRINK_OPTIONS: list[str] = [
    "Bier",
    "Rotwein",
    "Weißwein",
    "Cola",
    "Cola Zero",
    "Fanta",
    "Sprite",
    "Red Bull",
    "Alkoholfreies Bier",
    "Wasser",
]

LEGACY_FOOD_OPTIONS: list[str] = [
    "Grillfleisch",
    "Vegetarisch/Vegan",
    "Salate",
    "Snacks/Chips",
]

_LEGACY_OPTION_SET: set[str] = set(LEGACY_DRINK_OPTIONS) | set(LEGACY_FOOD_OPTIONS)

# --- Mapping: alter Options-String -> repräsentative Katalog-ID ---------------
# (jede ID wurde gegen catalog/direct_consumables.json bzw. catalog/recipes.json
# geprüft, siehe Modul-Docstring)

LEGACY_DRINK_TO_CATALOG_ID: dict[str, str] = {
    "Bier": "beer_pils",  # populärstes/repräsentativstes Bier-DirectConsumable
    "Rotwein": "red_wine",
    "Weißwein": "white_wine",
    "Cola": "cola",
    "Cola Zero": "cola_zero",
    "Fanta": "fanta_orange",
    "Sprite": "sprite",
    "Red Bull": "energy_drink_generic",  # siehe Designentscheidung oben (keine Brand-Selektion möglich)
    "Alkoholfreies Bier": "beer_pils_alcohol_free",
    "Wasser": "water",
}

LEGACY_FOOD_TO_CATALOG_ID: dict[str, str] = {
    "Grillfleisch": "bratwurst",  # populäres Grill-Rezept als Vertreter der breiten Kategorie
    "Vegetarisch/Vegan": "veggie_burger",
    "Salate": "kartoffelsalat",
    "Snacks/Chips": "potato_chips",
}


# --- Hilfsfunktionen -----------------------------------------------------------


def _parse_list(value) -> list[str]:
    """Robust gegenüber rohem SQLite-Zeileninhalt (JSON-String) UND bereits
    dekodierten Listen (z.B. wenn ein Aufrufer schon ``json.loads`` gemacht
    hat)."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return list(parsed) if isinstance(parsed, list) else []
    if isinstance(value, list):
        return list(value)
    return []


def _parse_songs(value) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    elif isinstance(value, list):
        parsed = value
    else:
        return []
    return [s for s in parsed if isinstance(s, dict)]


def is_legacy_row(row: dict) -> bool:
    """Heuristik: eine Zeile gilt als "legacy" (altes Format), wenn ihre
    ``drinks``/``food``-Werte eine (nichtleere) Teilmenge der alten fest
    codierten Options-Strings sind. Neue Zeilen speichern Katalog-IDs
    (snake_case, z.B. ``"beer_pils"``), die niemals mit den alten,
    grossgeschriebenen Anzeige-Strings (z.B. ``"Bier"``) kollidieren.

    Eine Zeile ohne jegliche Auswahl (leere Listen, nur Freitext) liefert
    keine Evidenz für "alt" vs. "neu" - wird hier als NICHT-legacy behandelt,
    da für den direkten ID-Pfad in diesem Fall ohnehin nichts zu mappen ist
    (Ergebnis ist in beiden Fällen identisch: eine leere Selektionsliste)."""
    combined = set(_parse_list(row.get("drinks"))) | set(_parse_list(row.get("food")))
    if not combined:
        return False
    return combined <= _LEGACY_OPTION_SET


def guest_response_from_legacy_row(row: dict, catalog: PartyCatalog) -> GuestResponse:
    """Konvertiert eine SQLite-Zeile im ALTEN Format (``drinks``/``food`` =
    JSON-Listen der alten fest codierten Options-Strings) in ein
    ``GuestResponse``. Unbekannte/nicht gemappte alte Strings werden
    stillschweigend ignoriert (können bei sauberer alter UI nicht auftreten,
    da die Multiselects auf ``LEGACY_DRINK_OPTIONS``/``LEGACY_FOOD_OPTIONS``
    beschränkt waren)."""
    drink_ids = [
        LEGACY_DRINK_TO_CATALOG_ID[d] for d in _parse_list(row.get("drinks")) if d in LEGACY_DRINK_TO_CATALOG_ID
    ]
    food_ids = [
        LEGACY_FOOD_TO_CATALOG_ID[f] for f in _parse_list(row.get("food")) if f in LEGACY_FOOD_TO_CATALOG_ID
    ]

    # Designentscheidung: drinks_freetext/food_freetext werden hier UNVERÄNDERT
    # (roh) durchgereicht, genau wie bei neuen Zeilen. Die eigentliche
    # Freitext-Auflösung über den Resolver (party_engine/resolver.py) passiert
    # NICHT hier, sondern zentral und einheitlich innerhalb der Pipeline
    # (siehe party_engine.allocation.resolve_guest_preferences, welches von
    # party_engine.engine.compute_party_demand für JEDE GuestResponse -
    # egal ob legacy-konvertiert oder neu - aufgerufen wird). Eine
    # Vorab-Auflösung hier wäre redundant und würde die Pipeline-Reihenfolge
    # aus AUFGABE §2 verletzen (Normalization passiert dort, nicht im Adapter).
    return GuestResponse(
        guest_name=row.get("name", ""),
        start_time=row.get("start_time", ""),
        drink_selections=drink_ids,
        drinks_freetext=row.get("drinks_freetext") or "",
        food_selections=food_ids,
        food_freetext=row.get("food_freetext") or "",
        songs=_parse_songs(row.get("songs")),
        dietary=DietaryProfile(),
    )


def guest_response_from_new_row(row: dict) -> GuestResponse:
    """Konvertiert eine SQLite-Zeile im NEUEN Format (``drinks``/``food`` =
    JSON-Listen von Katalog-IDs) direkt, ohne Mapping-Tabelle. Katalog-
    Validierung passiert bewusst nicht hier, sondern (wie bei jeder anderen
    ``GuestResponse``) zentral in ``resolve_guest_preferences`` - unbekannte
    IDs erzeugen dort automatisch einen ``ReviewIssue`` statt eines Crashs."""
    return GuestResponse(
        guest_name=row.get("name", ""),
        start_time=row.get("start_time", ""),
        drink_selections=_parse_list(row.get("drinks")),
        drinks_freetext=row.get("drinks_freetext") or "",
        food_selections=_parse_list(row.get("food")),
        food_freetext=row.get("food_freetext") or "",
        songs=_parse_songs(row.get("songs")),
        dietary=DietaryProfile(),
    )


def guest_response_from_row(row: dict, catalog: PartyCatalog) -> GuestResponse:
    """Einheitlicher Einstiegspunkt für den Admin-Bereich: wählt automatisch
    den richtigen Konvertierungspfad (legacy-Mapping vs. direkter
    ID-Durchgriff) je nach ``is_legacy_row``."""
    if is_legacy_row(row):
        return guest_response_from_legacy_row(row, catalog)
    return guest_response_from_new_row(row)
