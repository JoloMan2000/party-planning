"""
Spotify-Playlist-Erstellung aus Songwünschen
=============================================

Verbindet sich per OAuth (Authorization Code Flow) mit dem Spotify-Account
des Admins, sucht die von den Gästen gewünschten Songs (Interpret + Titel)
und legt daraus eine private Playlist ohne Duplikate an.

Benötigte Secrets (siehe README):
    spotify_client_id
    spotify_client_secret
    spotify_redirect_uri   (muss exakt im Spotify Developer Dashboard als
                             Redirect-URI eingetragen sein)

Designentscheidung: Der Refresh-Token wird lokal in einer gitignorten Datei
(.spotify_token.json) gespeichert, analog zu responses.db. Auf Streamlit
Community Cloud ist dieser Speicher nicht dauerhaft garantiert (siehe
README) - nach einem Neustart muss ggf. einmalig neu verbunden werden.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import requests

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
SCOPES = "playlist-modify-private playlist-modify-public"

APP_DIR = Path(__file__).parent
TOKEN_FILE = APP_DIR / ".spotify_token.json"

REQUEST_TIMEOUT_S = 10


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "show_dialog": "true",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def _basic_auth_header(client_id: str, client_secret: str) -> dict:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


def _save_token(token_data: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(token_data))


def _load_token() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_connected() -> bool:
    return _load_token() is not None


def disconnect() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def exchange_code_for_token(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        headers=_basic_auth_header(client_id, client_secret),
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    token_data = resp.json()
    _save_token(token_data)
    return token_data


def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers=_basic_auth_header(client_id, client_secret),
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    token_data = resp.json()
    # Spotify liefert beim Refresh nicht immer ein neues refresh_token mit.
    token_data.setdefault("refresh_token", refresh_token)
    _save_token(token_data)
    return token_data


def get_valid_access_token(client_id: str, client_secret: str) -> str | None:
    """Liefert ein gültiges Access-Token, erneuert es über den gespeicherten
    Refresh-Token. Gibt None zurück, wenn (noch) nicht verbunden."""
    token_data = _load_token()
    if token_data is None:
        return None
    refreshed = _refresh_access_token(client_id, client_secret, token_data["refresh_token"])
    return refreshed["access_token"]


def _get_current_user_id(access_token: str) -> str:
    resp = requests.get(
        f"{API_BASE}/me", headers={"Authorization": f"Bearer {access_token}"}, timeout=REQUEST_TIMEOUT_S
    )
    resp.raise_for_status()
    return resp.json()["id"]


def search_track(access_token: str, artist: str, title: str) -> str | None:
    """Sucht einen Track auf Spotify und gibt dessen URI zurück (oder None,
    falls kein Treffer gefunden wurde)."""
    query = f"track:{title} artist:{artist}"
    resp = requests.get(
        f"{API_BASE}/search",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "type": "track", "limit": 1},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    items = resp.json().get("tracks", {}).get("items", [])
    return items[0]["uri"] if items else None


def create_playlist(access_token: str, user_id: str, name: str, description: str) -> dict:
    resp = requests.post(
        f"{API_BASE}/users/{user_id}/playlists",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"name": name, "description": description, "public": False},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def add_tracks_to_playlist(access_token: str, playlist_id: str, uris: list[str]) -> None:
    # Spotify erlaubt maximal 100 URIs pro Request.
    for i in range(0, len(uris), 100):
        chunk = uris[i : i + 100]
        resp = requests.post(
            f"{API_BASE}/playlists/{playlist_id}/tracks",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"uris": chunk},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()


def build_playlist_from_songs(
    client_id: str,
    client_secret: str,
    songs: list[dict],
    playlist_name: str,
    playlist_description: str,
) -> dict:
    """
    songs: Liste von {"artist": str, "title": str, "guest_name": str}

    Rückgabe: {"playlist_url": str, "track_count": int, "not_found": list[dict]}
    """
    access_token = get_valid_access_token(client_id, client_secret)
    if access_token is None:
        raise RuntimeError("Nicht mit Spotify verbunden.")

    user_id = _get_current_user_id(access_token)

    seen_uris: set[str] = set()
    ordered_uris: list[str] = []
    not_found: list[dict] = []
    seen_wishes: set[tuple[str, str]] = set()  # dedupliziert gleiche Wünsche vor der Suche

    for song in songs:
        artist = song["artist"].strip()
        title = song["title"].strip()
        if not artist or not title:
            continue
        wish_key = (artist.lower(), title.lower())
        if wish_key in seen_wishes:
            continue
        seen_wishes.add(wish_key)

        uri = search_track(access_token, artist, title)
        if uri is None:
            not_found.append(song)
            continue
        if uri in seen_uris:  # z.B. zwei leicht unterschiedliche Schreibweisen -> gleicher Track
            continue
        seen_uris.add(uri)
        ordered_uris.append(uri)

    playlist = create_playlist(access_token, user_id, playlist_name, playlist_description)
    if ordered_uris:
        add_tracks_to_playlist(access_token, playlist["id"], ordered_uris)

    return {
        "playlist_url": playlist["external_urls"]["spotify"],
        "track_count": len(ordered_uris),
        "not_found": not_found,
    }
