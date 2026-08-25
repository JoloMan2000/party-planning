"""Party-Kontext-Orchestrierung: kombiniert die separat gepflegten
Party-Settings (Event-Typ/Datum/Ort, ``event_theme.py``) mit dem
Infrastruktur-/Location-``PartyContext`` (``party_context/storage.py``) zu
einem einzigen, aktuellen ``PartyContext``, und leitet daraus den
``DerivedPartyContext`` ab (inkl. Geocoding + Admin-Overrides).

Extrahiert aus ``"Party Planning.py"`` (Backend-Migration Phase 1, Schritt
0b): ``get_party_context()``/``get_derived_party_context()`` enthielten von
Anfang an keine Streamlit-Aufrufe, lasen aber implizit das Modul-Level-Global
``_PARTY_SETTINGS``. Für einen langlebigen FastAPI-Prozess (keine
"Skript rerunnt komplett pro Interaktion"-Garantie wie bei Streamlit) müssen
Settings pro Aufruf explizit übergeben werden statt über ein Global gelesen
zu werden - daher hier als expliziter ``party_settings: dict``-Parameter.

Verwendung ("Party Planning.py" UND backend/):
    import party_engine.context_orchestration as context_orchestration

    ctx = context_orchestration.get_party_context(DB_PATH, party_settings)
    derived = context_orchestration.get_derived_party_context(DB_PATH, party_settings, guest_count)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date as ddate, datetime
from pathlib import Path

import event_theme
import party_engine.response_storage as response_storage
from party_context import learning_storage
from party_context import storage as party_context_storage
from party_context.domain import DerivedPartyContext, PartyContext, PartyRunSnapshot, SelectionEvent
from party_context.engine import PartyContextEngine
from party_context.geocoding import CachingGeocodingProvider, NominatimGeocodingProvider
from party_engine.domain import PartyCatalog


def get_party_context(db_path: str | Path, party_settings: dict) -> PartyContext:
    """Lädt den gespeicherten (Infrastruktur-/Location-)``PartyContext`` und
    überschreibt Anlass/Datum/Startzeit/Dauer mit den bereits an anderer
    Stelle gepflegten, live aktuellen Werten aus ``party_settings`` (siehe
    ``event_theme.get_party_settings(db_path)``)."""
    ctx = party_context_storage.get_party_context(db_path)
    ctx.occasion_id = event_theme.resolve_occasion_id(party_settings["event_type"])
    if party_settings["party_date"] and party_settings["party_start_time"]:
        ctx.start_datetime = datetime.fromisoformat(
            f"{party_settings['party_date']}T{party_settings['party_start_time']}"
        )
    else:
        ctx.start_datetime = None
    ctx.duration_hours = float(party_settings["party_duration_hours"])
    # Geo-Kultur-Spec §2: party_address ist kein eigenes UI-Eingabefeld,
    # sondern wird 1:1 aus dem bereits bestehenden party_location-Feld
    # (render_party_settings_section) gespiegelt.
    ctx.party_address = party_settings["party_location"]
    return ctx


def get_derived_party_context(
    db_path: str | Path, party_settings: dict, guest_count: int
) -> DerivedPartyContext:
    """Leitet den zentralen ``DerivedPartyContext`` ab (inkl. admin-gesetzter
    Overrides, §71/§72) - die einzige Stelle, an der ``PartyContextEngine``
    aufgerufen wird (§10: keine nachgelagerte Engine leitet Kontext selbst ab).

    Geo-Kultur-Spec §2: übergibt einen ``CachingGeocodingProvider`` (nur bei
    vorhandener ``party_address`` UND fehlendem Admin-Override überhaupt
    genutzt, siehe ``resolve_country_code``) - Live-Geocoding via Nominatim,
    Ergebnis wird in ``geocode_cache`` persistiert (Pflicht-Cache, max. 1
    Request/Sekunde laut Nominatim-Nutzungsrichtlinie)."""
    ctx = get_party_context(db_path, party_settings)
    ctx.guest_count = guest_count or 1
    overrides = party_context_storage.get_party_context_overrides(db_path)
    geocoding_provider = CachingGeocodingProvider(db_path, NominatimGeocodingProvider())
    return PartyContextEngine().derive_context(ctx, overrides=overrides, geocoding_provider=geocoding_provider)


def maybe_freeze_and_reset_party(
    db_path: str | Path, party_settings: dict, catalog: PartyCatalog
) -> bool:
    """Party-Lifecycle-Trigger (Geo-Kultur-Spec §7): automatische Erkennung,
    kein Extra-Button. MUSS vor dem Speichern eines NEUEN ``party_date``
    aufgerufen werden (siehe Save-Button-Handler in
    ``render_party_settings_section``). Falls das BISHER gespeicherte
    ``party_date`` bereits in der Vergangenheit liegt, werden die aktuellen
    ``responses`` + der zu diesem Zeitpunkt gültige ``DerivedPartyContext``
    als ``PartyRunSnapshot``/``SelectionEvent``s eingefroren, danach wird
    NUR die ``responses``-Tabelle geleert. ``party_settings`` bleibt
    vollständig als wiederverwendbare Vorlage erhalten (der Aufrufer
    speichert das neue Datum separat via ``event_theme.save_party_settings``).
    Liefert ``True``, falls ein Reset stattgefunden hat (für eine Admin-
    Erfolgsmeldung), sonst ``False`` (z.B. beim allerersten Party-Setup, wenn
    noch kein ``party_date`` gesetzt war, oder wenn keine ``responses``
    vorliegen - dann gibt es nichts Sinnvolles zu lernen)."""
    old_date_str = party_settings["party_date"]
    if not old_date_str:
        return False
    try:
        old_date = ddate.fromisoformat(old_date_str)
    except ValueError:
        return False
    if old_date >= ddate.today():
        return False

    responses = response_storage.load_responses(db_path)
    if not responses:
        return False

    derived_context = get_derived_party_context(db_path, party_settings, len(responses))
    snapshot = PartyRunSnapshot(
        started_at=datetime.now(),
        occasion_id=event_theme.resolve_occasion_id(party_settings["event_type"]),
        country_code=derived_context.country_code,
        season=derived_context.season,
        temperature_class=derived_context.temperature_class,
        location_type=derived_context.location_type,
        group_size_class=derived_context.group_size_class,
    )
    party_run_id = learning_storage.save_party_run(db_path, snapshot)

    events: list[SelectionEvent] = []
    for row in responses:
        for item_id in json.loads(row["drinks"] or "[]"):
            item_type = response_storage._classify_item_type(item_id, catalog)
            if item_type:
                events.append(SelectionEvent(item_id=item_id, item_type=item_type))
        for item_id in json.loads(row["food"] or "[]"):
            item_type = response_storage._classify_item_type(item_id, catalog)
            if item_type:
                events.append(SelectionEvent(item_id=item_id, item_type=item_type))
    learning_storage.save_selection_events(db_path, party_run_id, events)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM responses")

    return True


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_context_orchestration.db"
        party_context_storage.init_party_context_storage(db_path)
        event_theme.init_party_settings(db_path)

        settings = event_theme.get_party_settings(db_path)
        ctx = get_party_context(db_path, settings)
        assert isinstance(ctx, PartyContext)
        assert ctx.occasion_id  # resolve_occasion_id never raises, always non-empty

        derived = get_derived_party_context(db_path, settings, guest_count=5)
        assert isinstance(derived, DerivedPartyContext)
        assert derived.season  # always derivable, never empty

        print("party_engine/context_orchestration.py sanity check OK.")
