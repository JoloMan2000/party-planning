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

Phase 1 (aktuell) implementiert nur die vier kontextfreien Demand-Driver
(``fixed``/``per_guest``/``capacity_based``/``per_station``) gegen einen
kleinen Starter-Katalog (~60 Items, 4 Kategorien) und das Host-Inventar.
Spätere Phasen (noch nicht implementiert, Landeplätze vorgemerkt):

    equipment_engine/context.py      -> Phase 2: echte PartyContext-Integration
                                         (Wetter, Capabilities, Sitzplätze),
                                         weitere Driver (per_table/per_area/...)
    equipment_engine/bundles.py      -> Phase 3: EquipmentBundle (Beer Pong Station,
                                         Cocktail Bar, BBQ, Buffet) + Activities-Integration
    equipment_engine/procurement.py  -> Phase 4: Buy/Rent/Borrow-Strategie,
                                         RentalSKU, EquipmentOverride
    equipment_engine/substitution.py -> Phase 4: EquipmentSubstitutionRule
    equipment_engine/checklist.py    -> Phase 4: Equipment-Checkliste (Buy/Rent/
                                         Bring/Setup/Return)

Wie bei ``party_engine/``/``music_engine/`` sind alle Module bewusst
Streamlit-/FastAPI-frei (reines ``python3``/``pytest``-testbar) - die
API-Anbindung lebt ausschließlich in ``backend/app/routers/``.

Zentrale Architekturregel (siehe Plan §3, mirrort ``party_engine/bom.py``):
Bedarf wird GLOBAL über alle Quellen aggregiert, BEVOR Reserve angewendet
wird, und Reserve wird BEVOR die finale Einkaufs-/Stückzahl-Rundung
angewendet wird - nie umgekehrt, nie mehrfach.
"""
