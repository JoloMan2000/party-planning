from __future__ import annotations

from pydantic import BaseModel, Field


class SongRequest(BaseModel):
    artist: str
    title: str


class GuestResponseCreate(BaseModel):
    name: str
    start_time: str  # "HH:MM", mirroring dtime.strftime("%H:%M") im Streamlit-Wizard
    drinks: list[str] = Field(default_factory=list)
    drinks_freetext: str = ""
    food: list[str] = Field(default_factory=list)
    food_freetext: str = ""
    songs: list[SongRequest] = Field(default_factory=list)


class GuestRecommendationsQuery(BaseModel):
    """Für die "empfohlen"-Hervorhebung im laufenden Wizard (§60/§61 der
    Recommendation-Spec) - der Gast ist noch anonym/nicht gespeichert, daher
    werden die bisherigen In-Wizard-Selections explizit mitgeschickt statt
    (wie im Streamlit-Original) aus ``st.session_state`` gelesen."""

    name: str = ""
    drinks: list[str] = Field(default_factory=list)
    food: list[str] = Field(default_factory=list)
    top_n: int = 16
