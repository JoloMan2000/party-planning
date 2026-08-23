"""
Track Resolver + Request Deduplication (Spec §6-10/§78/§79/§96).
===================================================================

Löst rohe Gästewünsche (``RawSongRequest``, Freitext oder Artist/Titel-Felder
aus der bestehenden UI) gegen den ``MusicCatalog`` auf (``ResolvedSongRequest``)
und fasst mehrere Schreibweisen desselben Songs zu einer einzigen
``TrackPreference`` zusammen (Spec §8/§9/§96: "Mr Brightside" / "Mr. Brightside"
/ "The Killers - Mr Brightside" -> 1 Track, 3 supporting requests).

Confidence-Schwellen (Spec §7):
    >= 0.90         automatisch übernehmen (needs_review=False)
    0.75-0.89       übernehmen + Adminhinweis (needs_review=True)
    < 0.75          Review (needs_review=True, ggf. kein track_id)

Unbekannte Songwünsche werden NIE verworfen (Spec §7 Schlusssatz) - sie
bleiben als ``ResolvedSongRequest`` mit ``resolution_type="unresolved"``
erhalten und tauchen später in ``MusicPlanningResult.unresolved_requests`` /
``review_issues`` auf.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from music_engine.catalog import (
    normalize_artist_key,
    normalize_song_key,
    normalize_text_key,
    normalize_title_key,
)
from music_engine.domain import MusicCatalog, RawSongRequest, ResolvedSongRequest, TrackPreference
from music_engine.tags import ERAS, GENRES

# Spec §10: initiale Quellen-Gewichtung, zentral konfigurierbar.
SOURCE_WEIGHT: dict[str, float] = {
    "admin_must_play": 10.0,
    "multi_guest_request": 6.0,
    "guest_request": 4.0,
    "admin_preferred": 3.5,
    "group_recommendation": 2.0,
    "occasion_recommendation": 1.3,
    "exploration": 0.5,
}

_AUTO_CONFIDENCE_THRESHOLD = 0.90
_ADMIN_HINT_CONFIDENCE_THRESHOLD = 0.75

# Deutsche/englische Jahrzehnt-Alias-Wörter für freitextliche Era-Wünsche
# ("2000er Party Musik", Spec §6 Beispiel).
_ERA_ALIASES: dict[str, str] = {
    "60er": "60s", "60s": "60s", "sixties": "60s",
    "70er": "70s", "70s": "70s", "seventies": "70s",
    "80er": "80s", "80s": "80s", "eighties": "80s",
    "90er": "90s", "90s": "90s", "nineties": "90s",
    "2000er": "2000s", "2000s": "2000s",
    "2010er": "2010s", "2010s": "2010s",
    "2020er": "2020s", "2020s": "2020s",
    "aktuell": "current", "current": "current", "charts": "current", "neu": "current",
}

# Ein paar gebräuchliche deutschsprachige Genre-Aliase zusätzlich zur
# music_engine.tags.GENRES-Taxonomie (die Genre-Slugs selbst, z.B. "hip_hop",
# werden ohnehin per Unterstrich/Leerzeichen-Toleranz erkannt).
_GENRE_ALIASES: dict[str, str] = {
    "hiphop": "hip_hop", "hip hop": "hip_hop",
    "deutschrap": "german_rap", "deutsch rap": "german_rap",
    "deutschpop": "german_pop", "deutsch pop": "german_pop",
    "elektro": "edm", "electro": "edm",
}

# Text-Trennzeichen zwischen Artist und Titel in Freitext-Eingaben
# ("The Killers - Mr Brightside", Spec §6/§8).
_SEPARATORS = (" - ", " – ", " — ", ": ")


def _split_artist_title(text: str) -> tuple[str, str]:
    """Best-effort Split eines Freitexts in (artist, title). Liefert
    (\"\", text) falls kein Trennzeichen gefunden wird - der Resolver
    behandelt den gesamten Text dann als Titel-Kandidat."""
    for sep in _SEPARATORS:
        if sep in text:
            left, right = text.split(sep, 1)
            return left.strip(), right.strip()
    return "", text.strip()


def _best_match(query_key: str, candidate_keys: list[str]) -> tuple[str | None, float]:
    """Liefert den best-passenden Kandidaten-Key + Ratio (0..1) via
    ``difflib.SequenceMatcher``. Der Katalog ist klein genug (~350 Tracks),
    um einen linearen Scan pro Anfrage zu erlauben."""
    best_key: str | None = None
    best_ratio = 0.0
    for candidate in candidate_keys:
        ratio = SequenceMatcher(None, query_key, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = candidate
    return best_key, best_ratio


def _pick_best_of(track_ids: list[str], catalog: MusicCatalog) -> str:
    """Bei mehrdeutigen Titel-Treffern (mehrere Artists mit demselben
    Songtitel) wird der bekannteste Track gewählt (höchster
    ``familiarity_prior``, dann ``party_score``)."""
    return max(
        track_ids,
        key=lambda tid: (catalog.tracks[tid].familiarity_prior, catalog.tracks[tid].party_score),
    )


def _detect_era(normalized_text: str) -> str | None:
    words = normalized_text.split(" ")
    for word in words:
        if word in _ERA_ALIASES:
            return _ERA_ALIASES[word]
    for era in ERAS:
        if era in normalized_text:
            return era
    return None


def _detect_genre(normalized_text: str) -> str | None:
    for alias, genre in _GENRE_ALIASES.items():
        if alias in normalized_text:
            return genre
    for genre in GENRES:
        if genre.replace("_", " ") in normalized_text:
            return genre
    return None


def resolve_song_request(raw: RawSongRequest, catalog: MusicCatalog) -> ResolvedSongRequest:
    """Löst einen einzelnen ``RawSongRequest`` gegen den ``MusicCatalog`` auf."""
    artist_raw = raw.artist_hint.strip() if raw.artist_hint else ""
    title_raw = raw.title_hint.strip() if raw.title_hint else ""

    if not artist_raw and not title_raw:
        artist_raw, title_raw = _split_artist_title(raw.text)
    if not title_raw:
        title_raw = raw.text.strip()

    # 1) Exakter Treffer über normalisierten "artist|title"-Key.
    if artist_raw:
        exact_key = normalize_song_key(artist_raw, title_raw)
        track_id = catalog.normalized_song_index.get(exact_key)
        if track_id:
            return ResolvedSongRequest(
                guest_id=raw.guest_id,
                original_text=raw.text,
                resolution_type="track",
                track_id=track_id,
                artist=catalog.tracks[track_id].artist,
                confidence=0.98,
                needs_review=False,
            )

    # 2) Exakter Treffer über reinen Titel-Key, falls kein Artist angegeben
    #    wurde (Spec §6 Beispiel "Mr Brightside" ohne "The Killers").
    title_key = normalize_title_key(title_raw)
    exact_title_matches = catalog.normalized_title_index.get(title_key)
    if not artist_raw and exact_title_matches:
        track_id = _pick_best_of(exact_title_matches, catalog)
        confidence = 0.95 if len(exact_title_matches) == 1 else 0.85
        return ResolvedSongRequest(
            guest_id=raw.guest_id,
            original_text=raw.text,
            resolution_type="track",
            track_id=track_id,
            artist=catalog.tracks[track_id].artist,
            confidence=confidence,
            needs_review=confidence < _AUTO_CONFIDENCE_THRESHOLD,
        )

    # 3) Fuzzy-Match über normalisierte Titel-Keys UND kombinierte Song-Keys
    #    (deckt Tippfehler, fehlende Satzzeichen, vertauschte Reihenfolge
    #    etc. ab - Spec §96). Der bessere der beiden Kandidaten gewinnt.
    combined_query_key = normalize_song_key(artist_raw, title_raw) if artist_raw else title_key
    best_combined_key, combined_ratio = _best_match(
        combined_query_key, list(catalog.normalized_song_index.keys())
    )
    best_title_key, title_ratio = _best_match(title_key, list(catalog.normalized_title_index.keys()))

    if best_title_key is not None and title_ratio >= combined_ratio and title_ratio >= _ADMIN_HINT_CONFIDENCE_THRESHOLD:
        matches = catalog.normalized_title_index[best_title_key]
        track_id = _pick_best_of(matches, catalog)
        confidence = min(0.97, title_ratio)
        return ResolvedSongRequest(
            guest_id=raw.guest_id,
            original_text=raw.text,
            resolution_type="track",
            track_id=track_id,
            artist=catalog.tracks[track_id].artist,
            confidence=confidence,
            needs_review=confidence < _AUTO_CONFIDENCE_THRESHOLD,
        )

    if best_combined_key is not None and combined_ratio >= _ADMIN_HINT_CONFIDENCE_THRESHOLD:
        track_id = catalog.normalized_song_index[best_combined_key]
        confidence = min(0.97, combined_ratio)
        return ResolvedSongRequest(
            guest_id=raw.guest_id,
            original_text=raw.text,
            resolution_type="track",
            track_id=track_id,
            artist=catalog.tracks[track_id].artist,
            confidence=confidence,
            needs_review=confidence < _AUTO_CONFIDENCE_THRESHOLD,
        )

    # 4) Reiner Artist-Freitext ohne klaren Titel-Treffer.
    normalized_text = normalize_text_key(raw.text)

    artist_keys = list(catalog.normalized_artist_index.keys())
    best_artist_key, artist_ratio = _best_match(normalize_text_key(artist_raw or raw.text), artist_keys)
    if best_artist_key is not None and artist_ratio >= _ADMIN_HINT_CONFIDENCE_THRESHOLD:
        candidate_track_ids = catalog.normalized_artist_index[best_artist_key]
        return ResolvedSongRequest(
            guest_id=raw.guest_id,
            original_text=raw.text,
            resolution_type="artist",
            track_id=None,
            artist=catalog.tracks[candidate_track_ids[0]].artist,
            confidence=min(0.85, artist_ratio),
            needs_review=True,
        )

    # 5) Genre-/Era-Erkennung für generische Wünsche ("2000er Party Musik").
    era = _detect_era(normalized_text)
    genre = _detect_genre(normalized_text)
    if era or genre:
        resolution_type = "genre" if genre else "era"
        return ResolvedSongRequest(
            guest_id=raw.guest_id,
            original_text=raw.text,
            resolution_type=resolution_type,
            track_id=None,
            genre=genre,
            era=era,
            confidence=0.6,
            needs_review=True,
        )

    # 6) Kompletter Fehlschlag: NIE verwerfen (Spec §7), sondern als
    #    unresolved markieren, damit der Admin es sehen/nachbearbeiten kann.
    return ResolvedSongRequest(
        guest_id=raw.guest_id,
        original_text=raw.text,
        resolution_type="unresolved",
        track_id=None,
        confidence=0.0,
        needs_review=True,
    )


def resolve_song_requests(
    raw_requests: list[RawSongRequest], catalog: MusicCatalog
) -> list[ResolvedSongRequest]:
    return [resolve_song_request(raw, catalog) for raw in raw_requests]


def deduplicate_requests(
    resolved_requests: list[ResolvedSongRequest],
) -> tuple[dict[str, TrackPreference], list[ResolvedSongRequest]]:
    """Fasst alle ``ResolvedSongRequest`` mit demselben ``track_id`` zu einer
    ``TrackPreference`` zusammen (Spec §8/§9/§96).

    Liefert (track_preferences, unresolved_or_untracked) - letzteres enthält
    alle Requests ohne ``track_id`` (artist/genre/era/unresolved), die nicht
    in eine ``TrackPreference`` einfließen können, aber für Review/Explain-
    ability weiterhin gebraucht werden.
    """
    preferences: dict[str, TrackPreference] = {}
    leftover: list[ResolvedSongRequest] = []

    for resolved in resolved_requests:
        if not resolved.track_id:
            leftover.append(resolved)
            continue

        pref = preferences.get(resolved.track_id)
        if pref is None:
            pref = TrackPreference(track_id=resolved.track_id, source="guest_request")
            preferences[resolved.track_id] = pref

        pref.supporting_guests.add(resolved.guest_id)
        pref.request_count += 1
        # Konfidenz der Preference = niedrigster Einzelwert (konservativ) -
        # verhindert, dass ein unsicherer Fuzzy-Match durch einen zweiten,
        # sehr sicheren Treffer "reingewaschen" wird.
        pref.confidence = min(pref.confidence, resolved.confidence) if pref.request_count > 1 else resolved.confidence

    for pref in preferences.values():
        is_multi_guest = len(pref.supporting_guests) > 1
        weight_key = "multi_guest_request" if is_multi_guest else "guest_request"
        pref.guest_priority_score = SOURCE_WEIGHT[weight_key]

    return preferences, leftover


if __name__ == "__main__":
    from music_engine.catalog import load_music_catalog

    _catalog = load_music_catalog()

    # Spec §96 TEST: DUPLIKATE
    _raw = [
        RawSongRequest(guest_id="Anna", text="Mr Brightside", title_hint="Mr Brightside"),
        RawSongRequest(guest_id="Ben", text="Mr. Brightside", title_hint="Mr. Brightside"),
        RawSongRequest(
            guest_id="Carla",
            text="The Killers - Mr Brightside",
            artist_hint="The Killers",
            title_hint="Mr Brightside",
        ),
    ]
    _resolved = resolve_song_requests(_raw, _catalog)
    for r in _resolved:
        print(r)
    _prefs, _leftover = deduplicate_requests(_resolved)
    assert len(_prefs) == 1, f"expected 1 track preference, got {len(_prefs)}"
    _only_pref = next(iter(_prefs.values()))
    assert _only_pref.request_count == 3, _only_pref.request_count
    assert len(_only_pref.supporting_guests) == 3, _only_pref.supporting_guests
    print(f"Dedup OK -> track_id={_only_pref.track_id}, request_count={_only_pref.request_count}")

    # Unresolved / genre-based request should never crash and never vanish.
    _generic = resolve_song_request(
        RawSongRequest(guest_id="Deniz", text="2000er Party Musik"), _catalog
    )
    print(f"Generic era request -> {_generic.resolution_type}, era={_generic.era}")
    assert _generic.resolution_type in ("era", "genre", "unresolved")

    print("music_engine/resolver.py sanity check OK.")
