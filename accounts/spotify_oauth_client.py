"""Reine HTTP-/PKCE-Hilfsfunktionen für den per-User Spotify-OAuth-Flow
(Onboarding-Spec, Phase 7 des Account-basierten Pivots).

Bewusst KEIN DB-Zugriff hier (siehe ``accounts/spotify_storage.py`` dafür) -
damit lässt sich dieses Modul in Tests komplett als Ganzes mocken
(``monkeypatch.setattr(spotify_oauth_client, "exchange_code_for_token", ...)``),
ohne echte Netzwerkaufrufe gegen Spotify.

Komplett getrennt vom bestehenden admin-only Single-Account-Flow in
``spotify_playlist.py`` (Authorization Code ohne PKCE, dateibasierter
Token-Speicher, Playlist-Export-Scopes) - dieser Flow ist PKCE-basiert,
pro User, und persistiert nichts selbst."""

from __future__ import annotations

import base64
import hashlib
import secrets

import requests

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

# Nur der Scope, der für die (spätere, noch nicht gebaute) Top-Artists/Genres-
# Import-Funktion nötig ist - so muss ein bereits verbundener User später
# keine zweite Consent-Runde durchlaufen (siehe Plan, Abschnitt
# "MusicProviderAdapter"). Keine Playlist-/Library-Scopes - unabhängig vom
# bestehenden Admin-Playlist-Export.
SCOPES = "user-top-read"

REQUEST_TIMEOUT_S = 10


def generate_pkce_pair() -> tuple[str, str]:
    """Liefert ``(code_verifier, code_challenge)`` nach RFC 7636 (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def exchange_code_for_token(
    client_id: str, client_secret: str, redirect_uri: str, code: str, code_verifier: str
) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
        auth=(client_id, client_secret),
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(client_id, client_secret),
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    token_data = resp.json()
    # Spotify liefert beim Refresh nicht immer ein neues refresh_token mit.
    token_data.setdefault("refresh_token", refresh_token)
    return token_data


def get_spotify_user_id(access_token: str) -> str:
    resp = requests.get(
        f"{API_BASE}/me", headers={"Authorization": f"Bearer {access_token}"}, timeout=REQUEST_TIMEOUT_S
    )
    resp.raise_for_status()
    return resp.json()["id"]
