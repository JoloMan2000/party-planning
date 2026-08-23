"""
Music-Legacy-Adapter
=======================

Bindet den bestehenden Songwunsch-Flow (``st.session_state.songs`` /
``responses.songs`` JSON-Spalte in "Party Planning.py") an das neue
``RawSongRequest``-Domain-Modell an (Spec §117 Schritt 3).

Bestehendes Format je Song-Eintrag (siehe "Party Planning.py" Zeile ~810):

```python
{"artist": "The Killers", "title": "Mr Brightside"}
```

und beim Admin-Export zusätzlich geflacht mit ``guest_name`` (Zeile ~1103):

```python
{"artist": ..., "title": ..., "guest_name": r["name"]}
```

Analog zu ``party_engine/legacy_adapter.py``: robuste, Streamlit-freie
Konvertierungslogik, tolerant gegenüber rohem JSON-String ODER bereits
dekodierter Liste (SQLite-Zeile vs. In-Memory ``st.session_state``).
"""

from __future__ import annotations

import json

from music_engine.domain import RawSongRequest


def _parse_songs(value) -> list[dict]:
    """Robust gegenüber rohem SQLite-Zeileninhalt (JSON-String) UND bereits
    dekodierten Listen (``st.session_state.songs``)."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    elif isinstance(value, list):
        parsed = value
    else:
        return []
    return [s for s in parsed if isinstance(s, dict)]


def raw_song_requests_from_songs(songs: list[dict] | str, guest_id: str, submitted_at: str = "") -> list[RawSongRequest]:
    """Konvertiert die rohe Songwunschliste EINES Gastes (bereits dekodierte
    Liste ODER JSON-String aus der ``songs``-Spalte) in ``RawSongRequest``-
    Objekte. Leere Artist/Titel-Einträge werden übersprungen (können in der
    bestehenden UI nicht entstehen, da beide Felder dort Pflichtfelder sind -
    trotzdem defensiv gefiltert, siehe party_engine-Konvention)."""
    parsed = _parse_songs(songs)
    requests: list[RawSongRequest] = []
    for song in parsed:
        artist = str(song.get("artist", "")).strip()
        title = str(song.get("title", "")).strip()
        if not artist and not title:
            continue
        text = f"{artist} - {title}".strip(" -") if artist else title
        requests.append(
            RawSongRequest(
                guest_id=guest_id,
                text=text,
                submitted_at=submitted_at,
                artist_hint=artist,
                title_hint=title,
            )
        )
    return requests


def raw_song_requests_from_row(row: dict) -> list[RawSongRequest]:
    """Konvertiert eine einzelne ``responses``-Zeile (dict mit mindestens
    ``name``/``songs``, optional ``start_time``) in ``RawSongRequest``-
    Objekte für genau diesen Gast."""
    guest_id = str(row.get("name", "")).strip()
    submitted_at = str(row.get("start_time", "") or "")
    return raw_song_requests_from_songs(row.get("songs"), guest_id=guest_id, submitted_at=submitted_at)


def raw_song_requests_from_responses(rows: list[dict]) -> list[RawSongRequest]:
    """Flacht alle Songwünsche über alle Gäste-Antworten (``responses``-Zeilen)
    zu einer einzigen Liste von ``RawSongRequest`` - der Standard-Einstiegspunkt
    für ``music_engine/engine.py``."""
    requests: list[RawSongRequest] = []
    for row in rows:
        requests.extend(raw_song_requests_from_row(row))
    return requests


if __name__ == "__main__":
    _session_songs = [
        {"artist": "The Killers", "title": "Mr Brightside"},
        {"artist": "", "title": "2000er Party Musik"},
    ]
    _requests = raw_song_requests_from_songs(_session_songs, guest_id="Anna")
    assert len(_requests) == 2, len(_requests)
    assert _requests[0].artist_hint == "The Killers"
    assert _requests[1].text == "2000er Party Musik"
    print(f"raw_song_requests_from_songs OK -> {_requests}")

    _rows = [
        {"name": "Anna", "start_time": "18:00", "songs": json.dumps(_session_songs)},
        {"name": "Ben", "start_time": "19:00", "songs": [{"artist": "ABBA", "title": "Dancing Queen"}]},
    ]
    _all_requests = raw_song_requests_from_responses(_rows)
    assert len(_all_requests) == 3, len(_all_requests)
    print(f"raw_song_requests_from_responses OK -> {len(_all_requests)} requests total")

    print("music_engine/legacy_adapter.py sanity check OK.")
