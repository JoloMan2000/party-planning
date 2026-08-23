"""
Party Phase Planner (Spec §46-48).
======================================

Berechnet aus der Party-Gesamtdauer und dem (ggf. gruppen-geblendeten)
``MusicOccasionProfile.energy_curve`` eine konkrete Liste von ``MusicPhase``-
Objekten mit Start-/End-Fraction (0..1) der Gesamtdauer.

Kanonische Phasen-Vokabular (Architekturentscheidung, siehe
music_engine/domain.py Docstring zu ``MusicOccasionProfile.energy_curve``):
``arrival, social, build, peak, late, closing``. Kurze Partys verwenden
weniger, zusammengefasste Phasen (Spec §47 Beispiel 2 Stunden:
"Arrival / Build / Peak-Closing") - die Merge-Logik ist rein
längenbasiert, nicht occasion-spezifisch, damit neue Anlässe automatisch
funktionieren (Spec §118 Erweiterbarkeit).
"""

from __future__ import annotations

from music_engine.domain import MusicOccasionProfile, MusicPhase

_DEFAULT_ENERGY = 0.5

# Statische Tag-Präferenzen je kanonischer Phase (Funktions-Tags aus
# music_engine/tags.py FUNCTION_TAGS + ein paar ergänzende Charakter-Tags).
# Occasion-spezifische preferred_tags werden separat (in ranking.py) mit
# diesen kombiniert - diese Zuordnung ist bewusst occasion-unabhängig.
PHASE_PREFERRED_TAGS: dict[str, dict[str, float]] = {
    "arrival": {"background": 0.7, "conversation_friendly": 0.6, "warmup": 0.5},
    "social": {"conversation_friendly": 0.5, "warmup": 0.6, "social": 0.6},
    "build": {"build_up": 0.8, "dancefloor": 0.5},
    "peak": {"peak": 0.9, "dancefloor": 0.9, "anthem": 0.6},
    "late": {"late_night": 0.7, "singalong": 0.7, "peak": 0.3},
    "closing": {"closing": 0.9, "singalong": 0.6, "nostalgic": 0.4},
}

# Kleine additive Familiarity-Anpassung je Phase (Peak/Late = bekanntere
# Mitsing-Klassiker, Arrival = darf ruhig etwas weniger bekannt sein).
_PHASE_FAMILIARITY_OFFSET: dict[str, float] = {
    "arrival": -0.05, "social": 0.0, "build": 0.0, "peak": 0.05, "late": 0.05, "closing": 0.0,
}

# Phasen-Templates nach Party-Gesamtdauer (Minuten). Jedes Template ist eine
# Liste von (merged_phase_id, [canonical_ids, die dieser Slot repräsentiert],
# start_fraction, end_fraction). Kürzere Partys fassen benachbarte Phasen
# zusammen (Spec §47).
_TEMPLATE_VERY_SHORT = [
    ("arrival", ["arrival"], 0.0, 0.3),
    ("peak", ["build", "peak", "late", "closing"], 0.3, 1.0),
]

_TEMPLATE_SHORT = [
    ("arrival", ["arrival"], 0.0, 0.25),
    ("build", ["social", "build"], 0.25, 0.45),
    ("peak", ["peak", "late", "closing"], 0.45, 1.0),
]

_TEMPLATE_MEDIUM = [
    ("arrival", ["arrival"], 0.0, 0.20),
    ("build", ["social", "build"], 0.20, 0.45),
    ("peak", ["peak"], 0.45, 0.82),
    ("closing", ["late", "closing"], 0.82, 1.0),
]

_TEMPLATE_FULL = [
    ("arrival", ["arrival"], 0.0, 0.18),
    ("social", ["social"], 0.18, 0.32),
    ("build", ["build"], 0.32, 0.45),
    ("peak", ["peak"], 0.45, 0.80),
    ("late", ["late"], 0.80, 0.92),
    ("closing", ["closing"], 0.92, 1.0),
]

# Schwellen in Minuten.
_VERY_SHORT_MAX_MINUTES = 90.0
_SHORT_MAX_MINUTES = 150.0
_MEDIUM_MAX_MINUTES = 240.0


def _select_template(total_minutes: float) -> list[tuple[str, list[str], float, float]]:
    if total_minutes <= _VERY_SHORT_MAX_MINUTES:
        return _TEMPLATE_VERY_SHORT
    if total_minutes <= _SHORT_MAX_MINUTES:
        return _TEMPLATE_SHORT
    if total_minutes <= _MEDIUM_MAX_MINUTES:
        return _TEMPLATE_MEDIUM
    return _TEMPLATE_FULL


def compute_phases(
    total_minutes: float,
    occasion_profile: MusicOccasionProfile,
) -> list[MusicPhase]:
    """Berechnet die konkreten ``MusicPhase``-Objekte für eine Party gegebener
    Gesamtdauer (Minuten) und Anlass-Energiekurve (Spec §46/§47)."""
    template = _select_template(max(total_minutes, 1.0))
    phases: list[MusicPhase] = []

    for phase_id, canonical_ids, start_fraction, end_fraction in template:
        energy_values = [
            occasion_profile.energy_curve.get(cid, _DEFAULT_ENERGY) for cid in canonical_ids
        ]
        target_energy = sum(energy_values) / len(energy_values) if energy_values else _DEFAULT_ENERGY

        familiarity_offset = sum(_PHASE_FAMILIARITY_OFFSET.get(cid, 0.0) for cid in canonical_ids) / len(
            canonical_ids
        )
        target_familiarity = min(1.0, max(0.0, occasion_profile.familiarity_target + familiarity_offset))

        # Danceability skaliert leicht mit der relativen Energie der Phase
        # gegenüber dem Occasion-Durchschnitt (laute Peak-Phasen tanzbarer,
        # ruhige Arrival-Phasen weniger tanzbar) - begrenzt auf [0, 1].
        avg_curve_energy = (
            sum(occasion_profile.energy_curve.values()) / len(occasion_profile.energy_curve)
            if occasion_profile.energy_curve
            else _DEFAULT_ENERGY
        )
        energy_factor = (target_energy / avg_curve_energy) if avg_curve_energy > 0 else 1.0
        energy_factor = min(1.3, max(0.6, energy_factor))
        target_danceability = min(1.0, max(0.0, occasion_profile.danceability_target * energy_factor))

        preferred_tags: dict[str, float] = {}
        for cid in canonical_ids:
            for tag, weight in PHASE_PREFERRED_TAGS.get(cid, {}).items():
                preferred_tags[tag] = max(preferred_tags.get(tag, 0.0), weight)

        phases.append(
            MusicPhase(
                id=phase_id,
                start_fraction=start_fraction,
                end_fraction=end_fraction,
                target_energy=round(target_energy, 4),
                target_danceability=round(target_danceability, 4),
                target_familiarity=round(target_familiarity, 4),
                preferred_tags=preferred_tags,
            )
        )

    return phases


def phase_minutes(phase: MusicPhase, total_minutes: float) -> float:
    """Hilfsfunktion: konkrete Minutenspanne einer Phase innerhalb der
    Gesamtdauer."""
    return (phase.end_fraction - phase.start_fraction) * total_minutes


if __name__ == "__main__":
    from music_engine.occasions import get_music_occasion, load_all_music_occasions

    _occasions = load_all_music_occasions()
    _grill = get_music_occasion("grill_party", _occasions)

    _phases_7h = compute_phases(420.0, _grill)
    print(f"7h party -> {len(_phases_7h)} phases: {[p.id for p in _phases_7h]}")
    assert len(_phases_7h) == 6, len(_phases_7h)
    assert abs(_phases_7h[-1].end_fraction - 1.0) < 1e-9
    assert _phases_7h[0].start_fraction == 0.0

    _phases_2h = compute_phases(120.0, _grill)
    print(f"2h party -> {len(_phases_2h)} phases: {[p.id for p in _phases_2h]}")
    assert len(_phases_2h) == 3, len(_phases_2h)

    _phases_1h = compute_phases(60.0, _grill)
    print(f"1h party -> {len(_phases_1h)} phases: {[p.id for p in _phases_1h]}")
    assert len(_phases_1h) == 2, len(_phases_1h)

    for p in _phases_7h:
        print(f"  {p.id}: {p.start_fraction:.2f}-{p.end_fraction:.2f} energy={p.target_energy} tags={p.preferred_tags}")

    print("music_engine/phases.py sanity check OK.")
