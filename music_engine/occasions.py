"""
MusicOccasionProfile-Loader
=============================

Lädt die statischen Musik-Anlass-Profile aus ``music_catalog/occasions/*.json``
(Spec §24-45: pro Anlass hinterlegte Genre-/Era-/Mood-/Tag-Gewichte,
Familiarity-/Danceability-/Mainstream-Targets und Energy-Curve) und baut daraus
typisierte ``MusicOccasionProfile``-Instanzen (siehe music_engine/domain.py).

Analog zu ``party_engine/occasions.py`` (gleiches Lade-/Fallback-Muster),
framework-agnostisch: kein Streamlit-Import, rein mit ``python3``/``pytest``
testbar.
"""

from __future__ import annotations

import json
from pathlib import Path

from music_engine.domain import DEFAULT_MUSIC_OCCASION_ID, MusicOccasionProfile

# Default: <repo_root>/music_catalog/occasions (dieses Modul liegt in <repo_root>/music_engine/)
_DEFAULT_OCCASIONS_DIR = Path(__file__).resolve().parent.parent / "music_catalog" / "occasions"


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_music_occasion_profile(row: dict) -> MusicOccasionProfile:
    return MusicOccasionProfile(
        occasion_id=row["occasion_id"],
        preferred_genres=dict(row.get("preferred_genres", {})),
        discouraged_genres=dict(row.get("discouraged_genres", {})),
        preferred_eras=dict(row.get("preferred_eras", {})),
        preferred_moods=dict(row.get("preferred_moods", {})),
        preferred_tags=dict(row.get("preferred_tags", {})),
        discouraged_tags=dict(row.get("discouraged_tags", {})),
        familiarity_target=row.get("familiarity_target", 0.6),
        danceability_target=row.get("danceability_target", 0.5),
        mainstream_target=row.get("mainstream_target", 0.6),
        energy_curve=dict(row.get("energy_curve", {})),
        diversity_rules=dict(row.get("diversity_rules", {})),
        default_explicit_policy=row.get("default_explicit_policy", "allow"),
        inherits_from=list(row.get("inherits_from", [])),
        profile_version=row.get("profile_version", "1.0"),
    )


def load_all_music_occasions(
    occasions_dir: str | Path = _DEFAULT_OCCASIONS_DIR,
) -> dict[str, MusicOccasionProfile]:
    """Lädt alle ``music_catalog/occasions/*.json`` Dateien in
    ``MusicOccasionProfile``-Instanzen, geschlüsselt nach ``occasion_id``."""
    occasions_path = Path(occasions_dir)
    profiles: dict[str, MusicOccasionProfile] = {}
    for json_path in sorted(occasions_path.glob("*.json")):
        row = _read_json(json_path)
        profile = _build_music_occasion_profile(row)
        profiles[profile.occasion_id] = profile
    return profiles


def get_music_occasion(
    occasion_id: str, occasions: dict[str, MusicOccasionProfile]
) -> MusicOccasionProfile:
    """Liefert das angeforderte ``MusicOccasionProfile``.

    Fallback-Logik (analog Spec §68 für den Party-Engine-Zwilling): Ist
    ``occasion_id`` unbekannt, wird niemals ein ``KeyError`` geworfen -
    stattdessen liefert diese Funktion das breite Fallback-Profil
    ``casual_get_together`` (DEFAULT_MUSIC_OCCASION_ID). Fehlt selbst dieses
    (z.B. in einem unvollständigen Test-Fixture), wird ein minimales
    Ad-hoc-Profil synthetisiert, damit der Aufrufer niemals crasht.
    """
    profile = occasions.get(occasion_id)
    if profile is not None:
        return profile

    fallback = occasions.get(DEFAULT_MUSIC_OCCASION_ID)
    if fallback is not None:
        return fallback

    return MusicOccasionProfile(occasion_id=DEFAULT_MUSIC_OCCASION_ID)


if __name__ == "__main__":
    _occasions = load_all_music_occasions()
    print(f"Loaded {len(_occasions)} music occasion profiles: {sorted(_occasions.keys())}")
    assert len(_occasions) == 23, f"expected 23 music occasion profiles, got {len(_occasions)}"
    assert DEFAULT_MUSIC_OCCASION_ID in _occasions

    _fallback_test = get_music_occasion("some_unknown_future_occasion", _occasions)
    assert _fallback_test.occasion_id == DEFAULT_MUSIC_OCCASION_ID
    print(f"Fallback OK -> {_fallback_test.occasion_id}")

    _wedding = get_music_occasion("wedding", _occasions)
    print(f"Wedding energy_curve: {_wedding.energy_curve}")

    print("music_engine/occasions.py sanity check OK.")
