from __future__ import annotations

import json

from fastapi import APIRouter, Depends

import event_theme
import party_engine.context_orchestration as context_orchestration
import party_engine.response_storage as response_storage
from backend.app.core.dataclass_json import to_jsonable
from backend.app.core.deps import get_catalog, get_db_path, get_occasions
from backend.app.core.security import get_current_admin
from party_context import learning_storage
from party_engine.domain import PartyCatalog
from party_engine.recommendation import recommend_for_admin, resolve_occasion_for_scoring
from party_engine.recommendation_domain import RecommendationContext

router = APIRouter(prefix="/api/v1/admin/recommendations", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("")
def get_admin_recommendations(
    catalog: PartyCatalog = Depends(get_catalog),
    occasions=Depends(get_occasions),
    db_path=Depends(get_db_path),
) -> list[dict]:
    settings = event_theme.get_party_settings(db_path)
    responses = response_storage.load_responses(db_path)

    already_selected_ids: set[str] = set()
    for r in responses:
        already_selected_ids.update(json.loads(r["drinks"]))
        already_selected_ids.update(json.loads(r["food"]))

    occasion_id = event_theme.resolve_occasion_id(settings["event_type"])
    occasion_profile = resolve_occasion_for_scoring([occasion_id], occasions)
    recommendation_context = RecommendationContext(occasion_ids=[occasion_profile.id], guest_count=len(responses) or None)
    derived_context = context_orchestration.get_derived_party_context(db_path, settings, len(responses))
    learning_history = learning_storage.get_learning_history(db_path)

    recommended = recommend_for_admin(
        catalog,
        occasion_profile,
        recommendation_context,
        already_selected_ids=already_selected_ids,
        top_n=20,
        derived_context=derived_context,
        learning_history=learning_history,
    )
    return [{"item": to_jsonable(item), "score": to_jsonable(score)} for item, score in recommended]
