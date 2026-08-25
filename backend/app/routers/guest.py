"""Gäste-Endpunkte - anonym, kein Auth nötig (mirroring der aktuellen
GuestResponse-Semantik: keine Identität über den selbst eingetragenen Namen
hinaus)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

import calendar_export
import event_theme
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from backend.app.adapters.guest import guest_stub_from_query, response_create_to_kwargs
from backend.app.core.deps import get_catalog, get_db_path, get_occasions
from backend.app.schemas.guest import GuestRecommendationsQuery, GuestResponseCreate
from party_context import learning_storage
from party_engine.domain import PartyCatalog
from party_engine.recommendation import recommend_for_guest, resolve_occasion_for_scoring
from party_engine.recommendation_domain import RecommendationContext
from translations import t

router = APIRouter(prefix="/api/v1/guest", tags=["guest"])


@router.get("/party-info")
def get_party_info(lang: str = "de", db_path=Depends(get_db_path)) -> dict:
    settings = event_theme.get_party_settings(db_path)
    theme = event_theme.EVENT_TYPES.get(settings["event_type"], event_theme.EVENT_TYPES[event_theme.DEFAULT_EVENT_TYPE])
    title = f"{theme['emoji']} {event_theme.resolve_party_title(settings)}"
    return {
        "event_type": settings["event_type"],
        "party_name": settings["party_name"],
        "title": title,
        "theme": theme,
        "hero_subtitle": t(lang, "hero_subtitle"),
        "meta_datetime": calendar_export.format_party_datetime(settings),
        "has_scheduled_date": calendar_export.has_scheduled_date(settings),
        "google_calendar_url": calendar_export.google_calendar_url(settings, title),
    }


@router.get("/calendar.ics")
def get_calendar_ics(db_path=Depends(get_db_path)) -> Response:
    settings = event_theme.get_party_settings(db_path)
    theme = event_theme.EVENT_TYPES.get(settings["event_type"], event_theme.EVENT_TYPES[event_theme.DEFAULT_EVENT_TYPE])
    title = f"{theme['emoji']} {event_theme.resolve_party_title(settings)}"
    ics = calendar_export.ics_content(settings, title)
    if not ics:
        return Response(status_code=404)
    return Response(content=ics, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=party.ics"})


@router.post("/responses", status_code=201)
def submit_response(payload: GuestResponseCreate, db_path=Depends(get_db_path)) -> dict:
    response_storage.save_response(db_path, **response_create_to_kwargs(payload))
    return {"status": "ok"}


@router.post("/recommendations")
def guest_recommendations(
    query: GuestRecommendationsQuery,
    catalog: PartyCatalog = Depends(get_catalog),
    occasions=Depends(get_occasions),
    db_path=Depends(get_db_path),
) -> list[str]:
    """Score-sortierte Item-IDs für die "empfohlen"-Hervorhebung im laufenden
    Wizard (mirroring ``_guest_recommended_ids``)."""
    settings = event_theme.get_party_settings(db_path)
    stub_guest = guest_stub_from_query(query.name, query.drinks, query.food)
    already_selected = set(query.drinks) | set(query.food)
    occasion_id = event_theme.resolve_occasion_id(settings["event_type"])
    occasion_profile = resolve_occasion_for_scoring([occasion_id], occasions)
    recommendation_context = RecommendationContext(occasion_ids=[occasion_profile.id])
    responses = response_storage.load_responses(db_path)
    derived_context = context_orchestration.get_derived_party_context(db_path, settings, len(responses))
    learning_history = learning_storage.get_learning_history(db_path)
    recommended = recommend_for_guest(
        catalog,
        occasion_profile,
        recommendation_context,
        stub_guest,
        already_selected_ids=already_selected,
        top_n=query.top_n,
        derived_context=derived_context,
        learning_history=learning_history,
    )
    return [item.id for item, _score in recommended]
