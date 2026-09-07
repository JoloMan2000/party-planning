"""Per-User Spotify-OAuth/PKCE-Connection-Lifecycle-Endpoints (Onboarding-Spec,
Phase 7 des Account-basierten Pivots): connect -> Browser-Consent -> callback ->
status -> disconnect. Kein Daten-Import (Top-Artists/-Genres) - das ist
Phase 8/9 (siehe Plan, Abschnitt "Explicit deferrals").

``GET /callback`` ist bewusst PUBLIC (kein ``get_current_user``) - Spotifys
Browser-Redirect kann keinen Bearer-Header mittragen. Der User wird
ausschließlich über die serverseitige ``state``-Zeile
(``accounts.spotify_storage.spotify_oauth_states``, angelegt während ``/connect``
mit einem eingeloggten User) identifiziert."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse

import accounts.spotify_oauth_client as spotify_oauth_client
import accounts.spotify_storage as spotify_storage
from accounts.domain import User
from backend.app.core.auth import get_current_user
from backend.app.core.deps import SpotifyOAuthConfig, get_db_path, get_spotify_oauth_config
from backend.app.schemas.spotify import SpotifyConnectResponse, SpotifyStatusResponse

router = APIRouter(prefix="/api/v1/me/music-provider/spotify", tags=["spotify-connect"])

_CANCELLED_HTML = "<html><body><p>Connection cancelled - you can close this tab.</p></body></html>"
_FAILED_HTML = "<html><body><p>Connection failed - you can close this tab and try again.</p></body></html>"
_SUCCESS_HTML = "<html><body><p>Connected! You can close this tab and return to the app.</p></body></html>"


@router.get("/connect", response_model=SpotifyConnectResponse)
def connect(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
    oauth_config: SpotifyOAuthConfig = Depends(get_spotify_oauth_config),
) -> SpotifyConnectResponse:
    state, code_challenge = spotify_storage.create_oauth_state(db_path, current_user.id)
    authorize_url = spotify_oauth_client.build_authorize_url(
        oauth_config.client_id, oauth_config.redirect_uri, state, code_challenge
    )
    return SpotifyConnectResponse(authorize_url=authorize_url)


@router.get("/callback", response_class=HTMLResponse)
def callback(
    state: str,
    code: str | None = None,
    error: str | None = None,
    db_path: Path = Depends(get_db_path),
    oauth_config: SpotifyOAuthConfig = Depends(get_spotify_oauth_config),
) -> HTMLResponse:
    if error is not None:
        spotify_storage.consume_oauth_state(db_path, state)
        return HTMLResponse(_CANCELLED_HTML)

    consumed = spotify_storage.consume_oauth_state(db_path, state)
    if consumed is None or code is None:
        return HTMLResponse(_FAILED_HTML, status_code=status.HTTP_400_BAD_REQUEST)
    user_id, code_verifier = consumed

    token_data = spotify_oauth_client.exchange_code_for_token(
        oauth_config.client_id, oauth_config.client_secret, oauth_config.redirect_uri, code, code_verifier
    )
    spotify_user_id = spotify_oauth_client.get_spotify_user_id(token_data["access_token"])
    spotify_storage.save_connection(
        db_path,
        oauth_config.encryption_key,
        user_id,
        spotify_user_id,
        token_data["access_token"],
        token_data["refresh_token"],
        token_data.get("scope", spotify_oauth_client.SCOPES),
        token_data["expires_in"],
    )
    return HTMLResponse(_SUCCESS_HTML)


@router.get("/status", response_model=SpotifyStatusResponse)
def get_status(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> SpotifyStatusResponse:
    connection = spotify_storage.get_connection(db_path, current_user.id)
    if connection is None:
        return SpotifyStatusResponse(connected=False)
    return SpotifyStatusResponse(
        connected=True, spotify_user_id=connection.spotify_user_id, connected_at=connection.connected_at
    )


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    current_user: User = Depends(get_current_user),
    db_path: Path = Depends(get_db_path),
) -> None:
    spotify_storage.delete_connection(db_path, current_user.id)
    return None
