"""Domain-Modell für ``Activity``/``ActivityVote`` (Equipment Engine Phase 4,
"Real Activities Domain + Guest Voting"). Ein eigenständiges Top-Level-Paket,
strukturell an ``organizers/`` angelehnt (plain Dataclasses, TEXT-``id``,
``created_at``-Timestamps via ``field(default_factory=lambda:
datetime.now(timezone.utc))``) - eine Activity ist party-gescoped (nicht
user- oder organizer-gescoped).

Eine ``Activity`` ist ein von Host/Co-Host vorgeschlagener Programmpunkt
("Beer Pong", "Karaoke", ...), für den Gäste per ``ActivityVote`` Interesse
bekunden können. Das aggregierte Voting-Ergebnis wird über
``equipment_engine.activity_integration`` in echten
``station_activity_interest``-Demand übersetzt (siehe dortigen Docstring).
Dieses Paket importiert bewusst NICHTS aus ``equipment_engine`` - der Router
(``backend/app/routers/admin_equipment.py``) macht den Join zwischen den
beiden Paketen, nicht dieses hier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Activity:
    """Ein von einem Host/Co-Host vorgeschlagener Programmpunkt/eine Station
    für seine Party."""

    id: str
    party_id: str
    created_by_user_id: str
    name: str
    # Freier String, NICHT gegen equipment_engine's Katalog-Vokabular
    # validiert (bewusste Entkopplung der beiden Pakete) - nur
    # ``station_id="beer_pong"`` hat heute eine echte Entsprechung in
    # ``catalog/equipment/demand_rules.json``s vier ``per_station``-Regeln
    # (``beer_pong_table``/``beer_pong_rack``/``beer_pong_ball_set``/ein
    # ``paper_cup``-Topup). Ein unbekannter oder fehlender ``station_id`` hat
    # schlicht keinerlei Equipment-Wirkung (siehe
    # ``equipment_engine.activity_integration.compute_station_activity_interest``).
    station_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ActivityVote:
    """Ein Gast-Vote für genau eine ``Activity``. ``UNIQUE(activity_id,
    user_id)`` in der Storage-Schicht (siehe ``activities/storage.py``) macht
    ein zweites Vote desselben Users für dieselbe Activity zu einem No-Op -
    mirrort ``social/follows.py``s Idempotenz-Konvention exakt."""

    id: str
    activity_id: str
    user_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
