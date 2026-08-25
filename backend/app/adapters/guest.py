"""dataclass <-> Pydantic Konvertierung für den Gäste-Antworten-Fluss."""

from __future__ import annotations

from backend.app.schemas.guest import GuestResponseCreate
from party_engine.domain import DietaryProfile, GuestResponse


def guest_stub_from_query(name: str, drinks: list[str], food: list[str]) -> GuestResponse:
    """Baut den anonymen "Stub"-Gast für die In-Wizard-Empfehlungs-
    Hervorhebung (mirroring ``_guest_recommended_ids`` in
    ``"Party Planning.py"``, dort aus ``st.session_state`` gelesen - hier
    explizit aus der Query, da die API stateless ist)."""
    return GuestResponse(
        guest_name=name,
        start_time="",
        drink_selections=list(drinks),
        food_selections=list(food),
        dietary=DietaryProfile(),
    )


def response_create_to_kwargs(payload: GuestResponseCreate) -> dict:
    """Liefert die kwargs für ``party_engine.response_storage.save_response``."""
    return {
        "name": payload.name.strip(),
        "start_time": payload.start_time,
        "drinks": payload.drinks,
        "drinks_freetext": payload.drinks_freetext,
        "food": payload.food,
        "food_freetext": payload.food_freetext,
        "songs": [song.model_dump() for song in payload.songs],
    }
