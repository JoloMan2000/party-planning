"""Tageszeit-Ableitung (Spec §6/§7). Zentral, damit keine Engine eine eigene
Daypart-Berechnung besitzt (§10). Segmente sind minutenbasiert und
mitternachts-wraparound-fähig (siehe config.DAYPART_SEGMENTS_MIN)."""

from __future__ import annotations

from datetime import datetime

from party_context.config import DAYPART_ORDER, DAYPART_SEGMENTS_MIN

_MINUTES_PER_DAY = 1440


def _minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def derive_daypart(start_datetime: datetime | None) -> str:
    """Liefert den primären Daypart des Party-Starts (§6). Fällt ohne
    Zeitangabe auf ``"evening"`` zurück (häufigster Party-Start, neutral)."""
    if start_datetime is None:
        return "evening"
    minute = _minute_of_day(start_datetime)
    for start, end, name in DAYPART_SEGMENTS_MIN:
        if start <= minute < end:
            return name
    return "evening"  # unreachable (Segmente decken den vollen Tag ab)


def derive_daypart_weights(
    start_datetime: datetime | None, duration_hours: float
) -> dict[str, float]:
    """Verteilt das Party-Zeitfenster ``[start, start+duration)`` auf die
    Daypart-Segmente und liefert Anteile (Summe = 1.0) - für lange Partys, die
    mehrere Dayparts abdecken (§7). Wraparound über Mitternacht wird über
    Modulo-1440-Arithmetik abgebildet."""
    if start_datetime is None or duration_hours <= 0:
        primary = derive_daypart(start_datetime)
        return {primary: 1.0}

    start_minute = _minute_of_day(start_datetime)
    total_minutes = duration_hours * 60.0

    overlap: dict[str, float] = {name: 0.0 for name in DAYPART_ORDER}
    elapsed = 0.0
    cursor = start_minute
    # In kleinen Schritten durch das Party-Fenster wandern und je Minute den
    # zutreffenden Daypart bestimmen (Segmentgrenzen sind alle Vielfache von
    # 60min, daher genügt eine grobe Schrittweite ohne Genauigkeitsverlust).
    step = 1.0
    while elapsed < total_minutes:
        remaining = total_minutes - elapsed
        chunk = min(step, remaining)
        pos = int(cursor % _MINUTES_PER_DAY)
        for seg_start, seg_end, name in DAYPART_SEGMENTS_MIN:
            if seg_start <= pos < seg_end:
                overlap[name] += chunk
                break
        cursor += chunk
        elapsed += chunk

    total = sum(overlap.values()) or 1.0
    weights = {name: round(minutes / total, 4) for name, minutes in overlap.items() if minutes > 0}
    return weights


if __name__ == "__main__":
    assert derive_daypart(datetime(2026, 7, 18, 15, 0)) == "daytime"
    assert derive_daypart(datetime(2026, 7, 18, 20, 0)) == "evening"
    assert derive_daypart(datetime(2026, 7, 18, 2, 0)) == "late_night"
    assert derive_daypart(datetime(2026, 7, 18, 9, 0)) == "morning"
    assert derive_daypart(None) == "evening"

    weights = derive_daypart_weights(datetime(2026, 7, 18, 15, 0), 8.5)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert set(weights.keys()) <= {"daytime", "afternoon", "evening", "late_night"}
    assert weights["evening"] > weights.get("late_night", 0.0)
    assert weights.get("late_night", 0.0) > 0

    # Wraparound: Start 22:00, 4h -> 22-24 evening, 0-2 late_night
    wrap_weights = derive_daypart_weights(datetime(2026, 7, 18, 22, 0), 4.0)
    assert abs(sum(wrap_weights.values()) - 1.0) < 1e-6
    assert wrap_weights["late_night"] > 0

    single = derive_daypart_weights(datetime(2026, 7, 18, 15, 0), 0.0)
    assert single == {"daytime": 1.0}
    print(f"daypart weights (8h from 15:00) -> {weights}")
    print("party_context/daypart.py sanity check OK.")
