"""
Spotify Export Adapter (Spec §3/§77).
========================================

Löst die fertig geplante, sequenzierte interne Playlist (``MusicPlanningResult``/
``PlaylistPlan``) auf ein Spotify-taugliches Songformat auf - Spotify ist laut
Spec ausschließlich Resolver-/Export-Layer, niemals Teil des Kern-Domain-Modells
(``MusicTrack``/``TrackScore``/... kennen kein Spotify). Dieses Modul ist bewusst
dünn und Streamlit-frei: es übersetzt nur ``PlaylistSlot`` (Reihenfolge bereits
final) + ``MusicCatalog`` in die von ``spotify_playlist.build_playlist_from_songs()``
erwartete ``list[{"artist", "title", "guest_name"}]`` - die eigentliche
Spotify-API-Kommunikation (Suche/Erstellen/Hinzufügen) bleibt vollständig in
spotify_playlist.py.

Verwendung ("Party Planning.py"):
    songs = songs_from_planning_result(result, catalog)
    spotify_playlist.build_playlist_from_songs(client_id, client_secret, songs, ...)
"""

from __future__ import annotations

from music_engine.domain import MusicCatalog, MusicPlanningResult


def songs_from_planning_result(result: MusicPlanningResult, catalog: MusicCatalog) -> list[dict]:
    """Wandelt die final sequenzierte Playlist (``result.playlist``, bereits nach
    ``PlaylistSlot.position`` sortiert von ``optimize_sequence()``) in die vom
    Spotify-Adapter erwartete Songliste um. Tracks ohne Katalogeintrag (sollte
    nicht vorkommen, da alle Kandidaten aus demselben Katalog stammen) werden
    defensiv übersprungen statt zu werfen. Mehrere unterstützende Gäste eines
    Songwunsches werden zu einem einzigen Anzeige-Namen zusammengefasst."""
    songs: list[dict] = []
    for slot in sorted(result.playlist, key=lambda s: s.position):
        track = catalog.get_track(slot.track_id)
        if track is None:
            continue
        guest_name = ", ".join(slot.supporting_guests)
        songs.append({"artist": track.artist, "title": track.title, "guest_name": guest_name})
    return songs


if __name__ == "__main__":
    from music_engine.domain import MusicTrack, PlaylistSlot

    _catalog = MusicCatalog(
        tracks={
            "t1": MusicTrack(id="t1", title="Mr Brightside", artist="The Killers"),
            "t2": MusicTrack(id="t2", title="Dancing Queen", artist="ABBA"),
        }
    )
    _result = MusicPlanningResult(
        playlist=[
            PlaylistSlot(position=1, phase_id="peak", track_id="t2", supporting_guests=["Ben"]),
            PlaylistSlot(position=0, phase_id="arrival", track_id="t1", supporting_guests=["Anna", "Ben"]),
        ]
    )
    _songs = songs_from_planning_result(_result, _catalog)
    assert _songs[0] == {"artist": "The Killers", "title": "Mr Brightside", "guest_name": "Anna, Ben"}
    assert _songs[1] == {"artist": "ABBA", "title": "Dancing Queen", "guest_name": "Ben"}
    print(f"songs_from_planning_result OK -> {_songs}")
    print("music_engine/spotify_adapter.py sanity check OK.")
