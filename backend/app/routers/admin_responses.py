from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Response

import party_engine.response_storage as response_storage
from backend.app.core.deps import get_catalog, get_db_path
from backend.app.core.security import get_current_admin
from party_engine.domain import PartyCatalog
from translations import catalog_item_name

router = APIRouter(prefix="/api/v1/admin/responses", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _display_name_for_selection(value: str, catalog: PartyCatalog, lang: str = "de") -> str:
    """Mirroring ``display_name_for_selection`` in ``"Party Planning.py"``."""
    item = catalog.get_item(value)
    if item is None:
        return value
    return catalog_item_name(item.id, item.name, lang)


def _format_songs(songs_json: str | None) -> str:
    songs = json.loads(songs_json) if songs_json else []
    return "; ".join(f"{s['artist']} – {s['title']}" for s in songs)


@router.get("")
def list_responses(db_path=Depends(get_db_path)) -> list[dict]:
    return response_storage.load_responses(db_path)


@router.get("/csv")
def export_responses_csv(
    db_path=Depends(get_db_path), catalog: PartyCatalog = Depends(get_catalog)
) -> Response:
    responses = response_storage.load_responses(db_path)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Name", "Startzeit", "Getränke", "Getränke (Freitext)", "Essen", "Essen (Freitext)", "Songwünsche", "Eingereicht am"]
    )
    for r in responses:
        drinks = [_display_name_for_selection(v, catalog) for v in json.loads(r["drinks"])]
        food = [_display_name_for_selection(v, catalog) for v in json.loads(r["food"])]
        writer.writerow(
            [
                r["name"],
                r["start_time"],
                ", ".join(drinks),
                r["drinks_freetext"] or "",
                ", ".join(food),
                r["food_freetext"] or "",
                _format_songs(r["songs"]),
                r["submitted_at"],
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=responses.csv"},
    )
