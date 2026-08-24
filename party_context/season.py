"""Saison-Ableitung aus dem Party-Datum (Spec §5). Zentral, damit keine Engine
eine eigene Saison-Logik besitzt (§10)."""

from __future__ import annotations

from datetime import date, datetime

from party_context.config import SEASON_BY_MONTH_NORTHERN, SEASON_BY_MONTH_SOUTHERN


def derive_season(
    party_date: date | datetime | None,
    hemisphere: str = "northern",
    override: str | None = None,
) -> str | None:
    """Leitet die Saison aus dem Party-Datum ab (§5). ``override`` (Admin) hat
    immer Vorrang. Ohne Datum und ohne Override wird ``None`` zurückgegeben -
    Caller/Engine entscheiden dann über einen neutralen Fallback."""
    if override:
        return override
    if party_date is None:
        return None
    table = SEASON_BY_MONTH_SOUTHERN if hemisphere == "southern" else SEASON_BY_MONTH_NORTHERN
    return table.get(party_date.month)


if __name__ == "__main__":
    assert derive_season(date(2026, 7, 18)) == "summer"
    assert derive_season(date(2026, 1, 10)) == "winter"
    assert derive_season(date(2026, 4, 1)) == "spring"
    assert derive_season(date(2026, 10, 5)) == "autumn"
    assert derive_season(date(2026, 7, 18), hemisphere="southern") == "winter"
    assert derive_season(None) is None
    assert derive_season(date(2026, 7, 18), override="winter") == "winter"
    print("party_context/season.py sanity check OK.")
