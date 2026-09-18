"""Activities-Integration (Phase 4, Spec §53/§58/§89/§90). Übersetzt ein
bereits AGGREGIERTES ``dict[station_id, roher_vote_count]`` in
``dict[station_id, station_count]`` - die Eingabe, die
``equipment_engine.demand.aggregate_equipment_demand``'s Pass 2
(``per_station``) seit Phase 1 schon kennt. Importiert bewusst NICHTS aus
dem neuen ``activities``-Paket - der Router
(``backend/app/routers/admin_equipment.py``) macht den Join zwischen den
beiden Paketen (Activity -> station_id, Votes zählen, hier konvertieren),
exakt wie ``equipment_engine.food_beverage_integration`` nie aus
``backend/app/routers/*`` importiert."""

from __future__ import annotations

import math

# Planungs-Default, NICHT spec-belegt - Spec §90 fordert nur explizit KEINE
# 1:1-Abbildung ("20 Beer Pong votes bedeutet nicht: 20 Beer Pong tables").
# Nur "beer_pong" hat heute echte per_station-Regeln (siehe
# catalog/equipment/demand_rules.json) - ein unbekannter station_id (z.B.
# eine host-erstellte "Karaoke"-Activity ohne Equipment-Bezug) wird unten
# sicher ignoriert, nicht als Fehler behandelt.
_GUESTS_PER_BEER_PONG_STATION = 8.0


def compute_station_activity_interest(vote_counts_by_station: dict[str, int]) -> dict[str, int]:
    """Spec §58/§90: Stationsanzahl skaliert sub-linear mit dem Interesse,
    nicht 1:1. ``max(1, ceil(votes / ratio))`` - sobald überhaupt Interesse
    besteht, mindestens eine Station."""
    ratios = {"beer_pong": _GUESTS_PER_BEER_PONG_STATION}
    result: dict[str, int] = {}
    for station_id, votes in vote_counts_by_station.items():
        if votes <= 0:
            continue
        ratio = ratios.get(station_id)
        if ratio is None:
            continue
        result[station_id] = max(1, math.ceil(votes / ratio))
    return result
