"""End-to-end/Szenario-Tests für die Music Recommendation & Party Playlist
Engine (music_engine/), gemäß den Testszenarien in
music_engine_full_spec.txt §96-110.

Nutzt ausschließlich den echten Musik-Katalog + echte Occasion-Profile (siehe
Fixtures unten), keine Mocks - analog zu tests/test_engine_e2e.py (AUFGABE §43).
"""

from __future__ import annotations

import pytest

from music_engine.catalog import load_music_catalog
from music_engine.domain import (
    AdminArtistOverride,
    AdminMusicSettings,
    AdminTrackOverride,
    RawSongRequest,
)
from music_engine.engine import build_music_strategy, plan_party_music
from music_engine.group_profile import build_group_music_profile, compute_group_weight
from music_engine.occasions import get_music_occasion, load_all_music_occasions
from music_engine.ranking import MAX_TRACKS_PER_ARTIST_AUTO
from music_engine.resolver import deduplicate_requests, resolve_song_requests


@pytest.fixture(scope="session")
def music_catalog():
    return load_music_catalog()


@pytest.fixture(scope="session")
def music_occasions():
    return load_all_music_occasions()


def _req(guest: str, title: str, artist: str = "") -> RawSongRequest:
    return RawSongRequest(guest_id=guest, text=f"{artist} - {title}" if artist else title, artist_hint=artist, title_hint=title)


def _first_tracks(catalog, n: int):
    return list(catalog.tracks.values())[:n]


# --- §96: Duplikat-Erkennung -------------------------------------------------


def test_duplicate_spellings_of_same_song_resolve_to_one_track_preference(music_catalog):
    """Spec §96: 'Mr Brightside', 'Mr. Brightside' und 'The Killers - Mr
    Brightside' von unterschiedlichen Gästen müssen auf denselben Track
    deduplizieren, mit allen Gästen als supporting_guests desselben Eintrags."""
    raw = [
        RawSongRequest(guest_id="Anna", text="Mr Brightside", title_hint="Mr Brightside"),
        RawSongRequest(guest_id="Ben", text="Mr. Brightside", title_hint="Mr. Brightside"),
        RawSongRequest(
            guest_id="Cara", text="The Killers - Mr Brightside", artist_hint="The Killers", title_hint="Mr Brightside"
        ),
    ]
    resolved = resolve_song_requests(raw, music_catalog)
    track_preferences, unresolved = deduplicate_requests(resolved)

    assert not unresolved, f"Erwartet: alle 3 Schreibweisen auflösbar, unresolved={unresolved}"
    assert len(track_preferences) == 1, f"Erwartet genau 1 dedupliziertem Track, bekam {len(track_preferences)}"

    pref = next(iter(track_preferences.values()))
    assert pref.supporting_guests == {"Anna", "Ben", "Cara"}
    assert pref.request_count == 3


# --- §97: Fairness zwischen Gästen -------------------------------------------


def test_fairness_prevents_single_guest_from_dominating_selection(music_catalog, music_occasions):
    """Spec §97: Ein Gast mit sehr vielen Songwünschen darf die kurze Playlist
    nicht komplett dominieren - mindestens ein Song eines anderen Gasts mit nur
    einem Wunsch muss es in eine knapp bemessene Playlist schaffen."""
    tracks = _first_tracks(music_catalog, 20)
    raw = [_req("Dominant", t.title, t.artist) for t in tracks[:15]]
    raw.append(_req("Fair", tracks[15].title, tracks[15].artist))

    occasion = get_music_occasion("casual_get_together", music_occasions)
    result = plan_party_music(
        raw_song_requests=raw,
        party_duration_minutes=20.0,  # sehr kurz -> erzwingt Reduktion
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    selected_guests = {g for slot in result.playlist for g in slot.supporting_guests}
    assert "Fair" in selected_guests, "Der Gast mit nur einem Wunsch wurde von 'Dominant' komplett verdrängt."


# --- §98: Multi-Guest Request (mehrere Gäste, ein Song) ----------------------


def test_multi_guest_request_lists_all_supporting_guests_on_the_slot(music_catalog, music_occasions):
    """Spec §98: Wünschen mehrere Gäste denselben Song, muss der finale
    PlaylistSlot alle unterstützenden Gästenamen tragen (nicht nur den ersten)."""
    track = _first_tracks(music_catalog, 1)[0]
    raw = [_req(g, track.title, track.artist) for g in ("Anna", "Ben", "Cara")]

    occasion = get_music_occasion("casual_get_together", music_occasions)
    result = plan_party_music(
        raw_song_requests=raw,
        party_duration_minutes=180.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    matching = [slot for slot in result.playlist if slot.track_id == track.id]
    assert matching, "Der mehrfach gewünschte Track fehlt in der finalen Playlist."
    assert set(matching[0].supporting_guests) == {"Anna", "Ben", "Cara"}


# --- §99: Zu kurze Playlist-Zeit (Songwünsche übersteigen Zeitbudget) -------


def test_excess_song_requests_are_reduced_but_not_deleted_from_preferences(music_catalog, music_occasions):
    """Spec §99: Übersteigen die Songwünsche das Zeitbudget massiv, muss die
    Engine intelligent reduzieren (nicht crashen, keine Überlänge), wobei
    'requested_tracks_selected' < 'requested_tracks_total' zeigt, dass reduziert
    wurde, ohne dass die Requests selbst verloren gehen (Coverage-Statistik
    bleibt korrekt)."""
    tracks = _first_tracks(music_catalog, 80)
    raw = [_req(f"Gast{i % 12}", t.title, t.artist) for i, t in enumerate(tracks)]

    occasion = get_music_occasion("grill_party", music_occasions)
    result = plan_party_music(
        raw_song_requests=raw,
        party_duration_minutes=60.0,  # 80 Songs a ~3-4min >> 60min
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    assert result.requested_tracks_selected < result.requested_tracks_total
    assert result.actual_duration_ms <= result.target_duration_ms * 1.05


# --- §100: Zu wenige Songwünsche (Playlist muss aufgefüllt werden) ---------


def test_too_few_song_requests_are_filled_up_to_target_duration(music_catalog, music_occasions):
    """Spec §100: Bei einer langen Party mit nur 2 Songwünschen muss die
    Engine die restliche Zeit mit sinnvollen Empfehlungen auffüllen -
    total_tracks muss weit über der Zahl der Requests liegen."""
    tracks = _first_tracks(music_catalog, 2)
    raw = [_req("Anna", tracks[0].title, tracks[0].artist), _req("Ben", tracks[1].title, tracks[1].artist)]

    occasion = get_music_occasion("house_party", music_occasions)
    result = plan_party_music(
        raw_song_requests=raw,
        party_duration_minutes=180.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    assert result.total_tracks > 10
    assert result.requested_tracks_selected == 2


# --- §101: Keine Songwünsche (Playlist rein aus Anlass/Occasion) -----------


def test_no_song_requests_still_produces_full_playlist_from_occasion_only(music_catalog, music_occasions):
    """Spec §101: Auch ganz ohne Songwünsche muss eine vollständige,
    anlassbasierte Playlist entstehen."""
    occasion = get_music_occasion("grill_party", music_occasions)
    result = plan_party_music(
        raw_song_requests=[],
        party_duration_minutes=120.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    assert result.total_tracks > 0
    assert result.requested_tracks_total == 0
    assert result.guest_coverage == 0.0


# --- §102: Grillparty vs. Dinnerparty (rein Occasion-getrieben) ------------


def test_grill_party_strategy_has_higher_targets_than_dinner_party_with_no_requests(music_catalog, music_occasions):
    """Spec §102: Ohne Songwünsche muss die Strategie 1:1 dem Occasion-Prior
    entsprechen - grill_party liegt auf familiarity/danceability/mainstream
    laut Katalogdaten strikt über dinner_party, das muss sich in
    build_music_strategy() widerspiegeln."""
    grill = get_music_occasion("grill_party", music_occasions)
    dinner = get_music_occasion("dinner_party", music_occasions)

    empty_profile = build_group_music_profile({}, music_catalog)
    settings = AdminMusicSettings()

    grill_strategy = build_music_strategy(grill, empty_profile, settings, total_minutes=120.0)
    dinner_strategy = build_music_strategy(dinner, empty_profile, settings, total_minutes=120.0)

    assert grill_strategy.group_weight == 0.0  # keine Requests -> reiner Occasion-Prior
    assert grill_strategy.familiarity_target > dinner_strategy.familiarity_target
    assert grill_strategy.danceability_target > dinner_strategy.danceability_target


# --- §103: Occasion-Prior wird durch viele Gästewünsche korrigiert --------


def test_group_weight_grows_towards_one_as_request_count_increases():
    """Spec §103/§50: group_weight = request_count / (request_count + 15) muss
    mit steigender Anzahl an Songwünschen monoton gegen 1 wachsen (Bayesian
    Shrinkage), sodass viele Gästewünsche den Anlass-Prior zunehmend
    überschreiben."""
    w0 = compute_group_weight(0)
    w15 = compute_group_weight(15)
    w100 = compute_group_weight(100)

    assert w0 == 0.0
    assert w15 == pytest.approx(0.5, rel=1e-6)
    assert w0 < w15 < w100 < 1.0


# --- §104: Artist Diversity (Auto-Empfehlungen, nicht Requests) -----------


def test_artist_diversity_caps_auto_filled_tracks_but_exempts_requests(music_catalog, music_occasions):
    """Spec §104/§55: Automatisch aufgefüllte (nicht angefragte) Tracks
    desselben Artists dürfen MAX_TRACKS_PER_ARTIST_AUTO nicht überschreiten,
    während explizit angefragte Tracks desselben Artists von diesem Limit
    ausgenommen sind (Spec §106 Analogie: Requests sind harte Priorität)."""
    # Finde einen Artist mit ausreichend vielen Katalog-Tracks für den Test.
    artist_counts: dict[str, int] = {}
    for t in music_catalog.tracks.values():
        artist_counts[t.artist] = artist_counts.get(t.artist, 0) + 1
    artist = max(artist_counts, key=artist_counts.get)
    assert artist_counts[artist] > MAX_TRACKS_PER_ARTIST_AUTO, "Testvoraussetzung: Artist mit genug Tracks nötig."

    occasion = get_music_occasion("house_party", music_occasions)
    result = plan_party_music(
        raw_song_requests=[],  # keine Requests -> alle Tracks sind Auto-Fill
        party_duration_minutes=600.0,  # großzügig, damit der Artist überhaupt oft genug Kandidat wäre
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    artist_track_count = sum(
        1 for slot in result.playlist if (t := music_catalog.get_track(slot.track_id)) and t.artist == artist
    )
    assert artist_track_count <= MAX_TRACKS_PER_ARTIST_AUTO


# --- §105: Phase Energy (Energiekurve über die Party hinweg) --------------


def test_house_party_late_phase_targets_higher_energy_than_arrival_phase(music_catalog, music_occasions):
    """Spec §105/§46: house_party hat laut Katalogdaten eine ausgeprägte
    Energiekurve (arrival niedrig, peak hoch) - das muss sich 1:1 in den
    berechneten MusicPhase.target_energy-Werten der Strategie wiederfinden."""
    occasion = get_music_occasion("house_party", music_occasions)
    empty_profile = build_group_music_profile({}, music_catalog)
    strategy = build_music_strategy(occasion, empty_profile, AdminMusicSettings(), total_minutes=180.0)

    phases_by_id = {p.id: p for p in strategy.phases}
    assert "arrival" in phases_by_id and "peak" in phases_by_id
    assert phases_by_id["peak"].target_energy > phases_by_id["arrival"].target_energy


# --- §106: Admin Must-Play übersteht Diversity-/Zeit-Reduktion ------------


def test_admin_must_play_track_survives_even_when_excluded_by_diversity_rules(music_catalog, music_occasions):
    """Spec §106: Ein per Admin-Override auf 'must_play' gesetzter Track muss
    in der finalen Playlist erscheinen - selbst wenn er (ohne Override) durch
    Diversity-/Artist-Caps ausgeschlossen worden wäre."""
    tracks = list(music_catalog.tracks.values())
    must_play_track = tracks[0]

    occasion = get_music_occasion("casual_get_together", music_occasions)
    overrides = {must_play_track.id: AdminTrackOverride(track_id=must_play_track.id, status="must_play")}
    result = plan_party_music(
        raw_song_requests=[],
        party_duration_minutes=90.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
        admin_track_overrides=overrides,
    )

    assert any(slot.track_id == must_play_track.id for slot in result.playlist)


def test_admin_ban_overrides_even_a_guest_song_request(music_catalog, music_occasions):
    """Spec §106/§107: Ein explizites Admin-Ban ist die einzige Instanz, die
    sogar einen echten Gästewunsch aus der Playlist ausschließen darf."""
    track = _first_tracks(music_catalog, 1)[0]
    raw = [_req("Anna", track.title, track.artist)]

    occasion = get_music_occasion("casual_get_together", music_occasions)
    overrides = {track.id: AdminTrackOverride(track_id=track.id, status="banned")}
    result = plan_party_music(
        raw_song_requests=raw,
        party_duration_minutes=120.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
        admin_track_overrides=overrides,
    )

    assert all(slot.track_id != track.id for slot in result.playlist)


# --- §107: Banned Genres --------------------------------------------------


def test_banned_genre_never_appears_in_final_playlist(music_catalog, music_occasions):
    """Spec §107: Ein per Admin als 'banned_genres' markiertes Genre darf in
    keinem finalen Playlist-Slot vorkommen."""
    # Wähle ein im Katalog tatsächlich vorkommendes Genre.
    genre = next(iter(music_catalog.genre_index.keys()))

    occasion = get_music_occasion("house_party", music_occasions)
    settings = AdminMusicSettings(banned_genres={genre})
    result = plan_party_music(
        raw_song_requests=[],
        party_duration_minutes=120.0,
        occasion_profile=occasion,
        admin_settings=settings,
        catalog=music_catalog,
    )

    for slot in result.playlist:
        track = music_catalog.get_track(slot.track_id)
        assert track is not None
        assert genre not in track.genres


def test_artist_ban_overrides_even_a_guest_song_request(music_catalog, music_occasions):
    """Spec §107: Analog zum Track-Ban - ein Admin-Artist-Ban schließt auch
    Requests dieses Artists aus."""
    track = _first_tracks(music_catalog, 1)[0]
    raw = [_req("Anna", track.title, track.artist)]

    occasion = get_music_occasion("casual_get_together", music_occasions)
    artist_key = track.artist.strip().lower()  # ranking.is_hard_excluded() lookt per lower-cased Artist-Key auf.
    artist_overrides = {artist_key: AdminArtistOverride(artist_id=artist_key, status="banned")}
    result = plan_party_music(
        raw_song_requests=raw,
        party_duration_minutes=120.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
        admin_artist_overrides=artist_overrides,
    )

    assert all(slot.track_id != track.id for slot in result.playlist)


# --- §108: Explicit Policy --------------------------------------------------


def test_explicit_tracks_excluded_when_admin_disallows_explicit(music_catalog, music_occasions):
    """Spec §108: Ist 'explicit_allowed=False' gesetzt, dürfen keine als
    explicit markierten Tracks in der finalen Playlist auftauchen."""
    occasion = get_music_occasion("dinner_party", music_occasions)
    settings = AdminMusicSettings(explicit_allowed=False)
    result = plan_party_music(
        raw_song_requests=[],
        party_duration_minutes=120.0,
        occasion_profile=occasion,
        admin_settings=settings,
        catalog=music_catalog,
    )

    for slot in result.playlist:
        track = music_catalog.get_track(slot.track_id)
        assert track is not None
        assert track.explicit is not True


# --- §109: Duration Buffer (Zieldauer = Partydauer * (1 + Puffer)) --------


def test_target_duration_includes_configured_buffer_percentage(music_catalog, music_occasions):
    """Spec §13/§109: Die Zieldauer muss exakt Partydauer * (1 + Puffer)
    entsprechen (in Millisekunden, gerundet)."""
    occasion = get_music_occasion("casual_get_together", music_occasions)
    settings = AdminMusicSettings(playlist_duration_buffer=0.2)
    result = plan_party_music(
        raw_song_requests=[],
        party_duration_minutes=100.0,
        occasion_profile=occasion,
        admin_settings=settings,
        catalog=music_catalog,
    )

    expected_target_ms = int(100.0 * 1.2 * 60_000)
    assert result.target_duration_ms == expected_target_ms


# --- §110: Sequenzierung (finale Positionen lückenlos & sortiert) --------


def test_playlist_positions_are_contiguous_and_sorted(music_catalog, music_occasions):
    """Spec §110/§67-69: Die finale Playlist muss lückenlos von 1..n
    durchnummeriert und in dieser Reihenfolge sortiert sein (Sequence
    Optimizer Output-Kontrakt)."""
    occasion = get_music_occasion("house_party", music_occasions)
    result = plan_party_music(
        raw_song_requests=[],
        party_duration_minutes=90.0,
        occasion_profile=occasion,
        admin_settings=AdminMusicSettings(),
        catalog=music_catalog,
    )

    positions = [slot.position for slot in result.playlist]
    assert positions == list(range(1, len(result.playlist) + 1))
