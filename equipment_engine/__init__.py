"""
Party Equipment & Supplies Engine
===================================

Dritte große Planungs-Engine neben Food/Beverage (``party_engine/``) und
Music (``music_engine/``) - siehe Claude-Code-Memory,
``party_equipment_engine_full_spec.txt`` für die vollständige
174-Abschnitte-Spezifikation "AUFGABE". Bestimmt, welches Equipment,
welche Verbrauchsmaterialien und welche organisatorische Ausstattung eine
Party benötigt - mit eigener Demand-Logik pro Equipment-Art statt
``guest_count × amount``.

Architektur (gespiegelt an ``party_engine/``/``music_engine/``):

    equipment_engine/domain.py       -> Datenstrukturen (KEINE Logik)
    equipment_engine/catalog.py      -> lädt catalog/equipment/*.json
    equipment_engine/demand.py       -> Aggregation -> Reserve -> Inventory-Netting
    equipment_engine/purchasing.py   -> Einkaufsplan (nutzt party_engine.purchasing.optimize_purchase)
    equipment_engine/engine.py       -> calculate_equipment_demand() Haupteinstiegspunkt
    equipment_engine/storage.py      -> Host-Equipment-Inventar (Storage + CRUD)
    equipment_engine/context.py      -> PartyContext-Integration (Wetter, Capabilities,
                                         Sitzplätze/Tische)
    equipment_engine/food_beverage_integration.py -> Food-/Beverage-Plan-Integration
                                         (Kühlkapazität, Eisbedarf, Kuchen-Zubehör)

Phase 1 implementierte die vier kontextfreien Demand-Driver
(``fixed``/``per_guest``/``capacity_based``/``per_station``) gegen einen
kleinen Starter-Katalog und das Host-Inventar. Phase 2 ergänzte
``equipment_engine/context.py`` (echte PartyContext-Integration: Wetter,
Capabilities, Sitzplätze/Tische, ``per_duration``-Driver, Venue-Provisions).
Phase 3 ergänzte ``equipment_engine/food_beverage_integration.py`` (echte
Food-/Beverage-Plan-Anbindung: Kühlkapazität + Eisbedarf aus dem realen
Getränkeplan statt manueller Overrides, Kuchen-Zubehör-Trigger). Spätere
Phasen (noch nicht implementiert, Landeplätze vorgemerkt):

    equipment_engine/bundles.py      -> Phase 4: EquipmentBundle (Beer Pong Station,
                                         Cocktail Bar, BBQ, Buffet) + Activities-Integration
                                         (echtes station_activity_interest statt Stub)
    equipment_engine/procurement.py  -> Phase 5: Buy/Rent/Borrow-Strategie,
                                         RentalSKU, EquipmentOverride
    equipment_engine/substitution.py -> Phase 5: EquipmentSubstitutionRule
    equipment_engine/checklist.py    -> Phase 5: Equipment-Checkliste (Buy/Rent/
                                         Bring/Setup/Return)

Wie bei ``party_engine/``/``music_engine/`` sind alle Module bewusst
Streamlit-/FastAPI-frei (reines ``python3``/``pytest``-testbar) - die
API-Anbindung lebt ausschließlich in ``backend/app/routers/``.

Zentrale Architekturregel (siehe Plan §3, mirrort ``party_engine/bom.py``):
Bedarf wird GLOBAL über alle Quellen aggregiert, BEVOR Reserve angewendet
wird, und Reserve wird BEVOR die finale Einkaufs-/Stückzahl-Rundung
angewendet wird - nie umgekehrt, nie mehrfach.
"""
