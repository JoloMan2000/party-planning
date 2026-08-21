"""
OccasionProfile-Loader
========================

Lädt die statischen Anlass-Profile aus ``catalog/occasions/*.json`` (siehe
Spec-Erweiterung "VOLLSTÄNDIGES TAG- UND OCCASION-MAPPING", §8-29/§68/§69/§74
in der Claude-Code-Memory unter recommendation_engine_full_spec.txt) und baut
daraus typisierte ``OccasionProfile``-Instanzen (siehe
party_engine/recommendation_domain.py).

Framework-agnostisch: Dieses Modul importiert Streamlit NICHT und funktioniert
mit reinem ``python3`` / ``pytest`` (Analog zu party_engine/catalog.py für den
Haupt-PartyCatalog).

Enthält außerdem die Fallback- (§68) und Multi-Occasion-Kombinationslogik
(§69), die von der eigentlichen Scoring-Engine (recommendation.py) sowie der
UI genutzt werden.
"""

from __future__ import annotations

import json
from pathlib import Path

from party_engine.recommendation_domain import DEFAULT_OCCASION_ID, OccasionProfile

# Default: <repo_root>/catalog/occasions  (dieses Modul liegt in <repo_root>/party_engine/)
_DEFAULT_OCCASIONS_DIR = Path(__file__).resolve().parent.parent / "catalog" / "occasions"

# Gewichtung für die Kombination von Primär-/Sekundär-Anlass (§69).
_PRIMARY_WEIGHT = 0.6
_SECONDARY_WEIGHT = 0.4


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_occasion_profile(row: dict) -> OccasionProfile:
    return OccasionProfile(
        id=row["id"],
        label_de=row["label_de"],
        label_en=row["label_en"],
        preferred_tags=dict(row.get("preferred_tags", {})),
        discouraged_tags=dict(row.get("discouraged_tags", {})),
        admin_food_slots=dict(row.get("admin_food_slots", {})),
        admin_beverage_slots=dict(row.get("admin_beverage_slots", {})),
        inherits_from=list(row.get("inherits_from", [])),
        profile_version=row.get("profile_version", "1.0"),
    )


def load_all_occasions(occasions_dir: str | Path = _DEFAULT_OCCASIONS_DIR) -> dict[str, OccasionProfile]:
    """Lädt alle ``catalog/occasions/*.json`` Dateien in ``OccasionProfile``-
    Instanzen, geschlüsselt nach ``id``.

    Jeder JSON-Datei-Inhalt entspricht 1:1 den Feldern von ``OccasionProfile``
    (siehe party_engine/recommendation_domain.py).
    """
    occasions_path = Path(occasions_dir)
    profiles: dict[str, OccasionProfile] = {}
    for json_path in sorted(occasions_path.glob("*.json")):
        row = _read_json(json_path)
        occasion = _build_occasion_profile(row)
        profiles[occasion.id] = occasion
    return profiles


def get_occasion(occasion_id: str, occasions: dict[str, OccasionProfile]) -> OccasionProfile:
    """Liefert das angeforderte ``OccasionProfile``.

    Fallback-Logik (§68): Ist ``occasion_id`` unbekannt (z.B. ein künftiger,
    noch nicht angelegter Custom-Anlass), wird niemals ein ``KeyError``
    geworfen - stattdessen liefert diese Funktion das breite Fallback-Profil
    ``casual_get_together`` (DEFAULT_OCCASION_ID). Fehlt selbst dieses (z.B.
    in einem unvollständigen Test-Fixture), wird ein minimales Ad-hoc-Profil
    synthetisiert, damit der Aufrufer niemals crasht.
    """
    profile = occasions.get(occasion_id)
    if profile is not None:
        return profile

    fallback = occasions.get(DEFAULT_OCCASION_ID)
    if fallback is not None:
        return fallback

    # Letzter Rettungsanker: falls selbst casual_get_together nicht geladen
    # werden konnte, liefere ein leeres, aber valides Profil zurück statt zu
    # crashen (§68: "muss niemals crashen").
    return OccasionProfile(
        id=DEFAULT_OCCASION_ID,
        label_de="Lockeres Beisammensein",
        label_en="Casual Get-Together",
    )


def _combine_weighted(
    primary: dict[str, float],
    secondary: dict[str, float],
    primary_weight: float = _PRIMARY_WEIGHT,
    secondary_weight: float = _SECONDARY_WEIGHT,
) -> dict[str, float]:
    """Vereinigt zwei Tag-Gewichts-Dicts gewichtet (§69), Werte auf [0, 1]
    geklemmt."""
    combined: dict[str, float] = {}
    for key in set(primary) | set(secondary):
        value = primary.get(key, 0.0) * primary_weight + secondary.get(key, 0.0) * secondary_weight
        combined[key] = max(0.0, min(1.0, value))
    return combined


def resolve_combined_profile(
    occasion_ids: list[str],
    occasions: dict[str, OccasionProfile],
) -> OccasionProfile:
    """Löst eine (Multi-)Occasion-Auswahl zu einem einzigen ``OccasionProfile``
    auf (§69).

    - Leere Liste oder genau eine ID: entspricht ``get_occasion`` (inkl.
      Fallback-Logik §68).
    - Zwei oder mehr IDs: der erste Eintrag gilt als Primär-Anlass (Gewicht
      0.6), der zweite als Sekundär-Anlass (Gewicht 0.4). Weitere IDs werden
      in Version 1 ignoriert (siehe Spec §69: "Version 1 may expose one
      primary occasion in UI, but architecture should not prevent combination
      later"). preferred_tags/discouraged_tags werden als gewichtete Union
      kombiniert; admin_food_slots/admin_beverage_slots werden vom
      Primär-Profil übernommen.
    """
    if not occasion_ids:
        return get_occasion(DEFAULT_OCCASION_ID, occasions)

    if len(occasion_ids) == 1:
        return get_occasion(occasion_ids[0], occasions)

    primary = get_occasion(occasion_ids[0], occasions)
    secondary = get_occasion(occasion_ids[1], occasions)

    combined_preferred = _combine_weighted(primary.preferred_tags, secondary.preferred_tags)
    combined_discouraged = _combine_weighted(primary.discouraged_tags, secondary.discouraged_tags)

    return OccasionProfile(
        id=f"{primary.id}+{secondary.id}",
        label_de=f"{primary.label_de} + {secondary.label_de}",
        label_en=f"{primary.label_en} + {secondary.label_en}",
        preferred_tags=combined_preferred,
        discouraged_tags=combined_discouraged,
        admin_food_slots=dict(primary.admin_food_slots),
        admin_beverage_slots=dict(primary.admin_beverage_slots),
        inherits_from=[primary.id, secondary.id],
        profile_version=primary.profile_version,
    )


if __name__ == "__main__":
    _occasions = load_all_occasions()
    print(f"Loaded {len(_occasions)} occasion profiles: {sorted(_occasions.keys())}")
    assert len(_occasions) == 23, f"expected 23 occasion profiles, got {len(_occasions)}"

    _fallback_test = get_occasion("some_unknown_future_occasion", _occasions)
    assert _fallback_test.id == DEFAULT_OCCASION_ID
    print(f"Fallback OK -> {_fallback_test.id}")

    _combined = resolve_combined_profile(["birthday", "garden_party"], _occasions)
    print(f"Combined profile id: {_combined.id}")
    print(f"Combined preferred_tags sample: {dict(list(_combined.preferred_tags.items())[:5])}")

    print("occasions.py sanity check OK.")
