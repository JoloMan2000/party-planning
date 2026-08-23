"""
Music Recommendation & Party Playlist Engine
==============================================

Erweitert die bestehende Party-Planungs-App um eine eigenständige
Musikplanungs-Engine (siehe Claude-Code-Memory, ``music_engine_full_spec.txt``
für die vollständige 119-Abschnitte-Spezifikation "AUFGABE").

Architektur (Spec §1/§2, gespiegelt an ``party_engine/``):

    music_engine/domain.py       -> Datenstrukturen (KEINE Logik)
    music_engine/tags.py         -> Genre-/Era-/Mood-/Tag-Taxonomie
    music_engine/catalog.py      -> lädt music_catalog/*.json (MusicTrack-Seed)
    music_engine/occasions.py    -> lädt music_catalog/occasion_music_profiles.json
    music_engine/resolver.py     -> Track Resolver + Deduplication
    music_engine/legacy_adapter.py -> bindet bestehenden Songwunsch-Flow an
    music_engine/group_profile.py  -> GroupMusicProfile-Builder
    music_engine/fairness.py       -> Gast-Fairness-Auswahl
    music_engine/phases.py         -> Party Phase Planner
    music_engine/candidates.py     -> Candidate-Provider-Architektur
    music_engine/ranking.py        -> TrackRanker Protocol + RuleBasedTrackRanker
    music_engine/duration.py       -> Playlist Duration Optimizer
    music_engine/sequence.py       -> Sequence Optimizer
    music_engine/admin_settings.py -> AdminMusicSettings (Storage + Defaults)
    music_engine/spotify_adapter.py-> PlaylistPlan -> bestehender Spotify-Export
    music_engine/engine.py         -> plan_party_music() Core-API

Wie bei ``party_engine/`` sind alle Module bewusst Streamlit-frei (reines
``python3``/``pytest``-testbar). Die Streamlit-Anbindung (Caching, UI) lebt
ausschließlich in "Party Planning.py".

Zentrale Architekturregel (Spec §3): Spotify ist NICHT das interne
Domain-Modell. Ein ``MusicTrack`` besitzt eine eigene interne ``id``;
``spotify_uri`` ist nur eine externe Referenz, die erst im letzten Schritt
(``spotify_adapter.py``) verwendet wird.
"""
