"""Generische Dataclass -> JSON-fähiges-dict-Konvertierung für READ-Response-
Bodies, die komplexe, tief verschachtelte Domain-Dataclasses zurückgeben
(``PartyDemandResult``, ``MusicPlanningResult``, ``DerivedPartyContext``, ...).

Bewusste Design-Entscheidung (Abweichung von der im Plan skizzierten
"ein Pydantic-Modell pro Dataclass"-Idee): diese Ergebnis-Dataclasses haben
zusammen >15 verschachtelte Typen. Ein von Hand gepflegter Pydantic-Baum
dafür wäre eine große, bei jeder Engine-Änderung nachzuziehende Parallel-
struktur - das primäre Ziel von Schritt 3 (Dataclasses bleiben autoritativ,
keine Business-Logik-Duplikation) wird von einer generischen, rekursiven
``dataclasses.asdict``-Variante mit ``set -> sorted(list)``-Normalisierung
besser erfüllt. Pydantic-Modelle bleiben für REQUEST-Bodies (siehe
``backend/app/schemas/``), wo Validierung tatsächlich Mehrwert bietet.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (set, frozenset)):
        return sorted(to_jsonable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
