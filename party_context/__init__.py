"""
Party Context Intelligence Layer
===================================

Zentrale, gemeinsame Kontext-Schicht für Beverage-, Food-, Music- und
Occasion-Recommendation-Engine (siehe Claude-Code-Memory,
``party_context_engine_full_spec.txt`` für die vollständige
100-Abschnitte-Spezifikation "AUFGABE").

Architektur (Spec §97, gespiegelt an ``party_engine/``/``music_engine/``):

    party_context/domain.py        -> Datenstrukturen (KEINE Logik)
    party_context/config.py        -> zentrale Thresholds/Multiplikatoren/Gewichte (§92)
    party_context/season.py        -> derive_season() (§5)
    party_context/daypart.py       -> derive_daypart()/derive_daypart_weights() (§6/§7)
    party_context/temperature.py   -> classify_temperature() (§46)
    party_context/capabilities.py  -> Infrastruktur -> available_capabilities (§17/§18)
    party_context/locations.py     -> LOCATION_PROFILES für 20 Location-Typen (§3/§51-§60)
    party_context/weather.py       -> WeatherProvider-Anbindung (optional, §73-§75)
    party_context/engine.py        -> PartyContextEngine.derive_context() Core-API (§9)
    party_context/context_fit.py   -> ContextAffinity-Scoring je Item (§12/§42)
    party_context/storage.py       -> sqlite-Persistenz + Migration (§89-§91)

Zentrale Architekturregel (§98): alle Engines konsumieren denselben
``DerivedPartyContext`` - keine Engine besitzt eine isolierte Vorstellung der
Party. Wie bei ``party_engine/``/``music_engine/`` sind alle Module bewusst
Streamlit-frei; die Streamlit-Anbindung lebt ausschließlich in
"Party Planning.py".
"""
