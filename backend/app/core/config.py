"""Backend-Konfiguration (Env-Var-basiert, siehe Phase-1-Plan Schritt 1/4).

Ersetzt die Streamlit-``st.secrets``-Quelle aus ``"Party Planning.py"`` durch
Standard-Umgebungsvariablen, da ``backend/`` kein Streamlit-Prozess ist.
Nutzt ``pydantic-settings`` (liest optional eine ``.env``-Datei im Repo-Root),
mirroring der übrigen Projekt-Konvention "Defaults, die auch ohne jede
Konfiguration ein lauffähiges lokales Dev-Setup ergeben".
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    db_path: Path = REPO_ROOT / "responses.db"
    media_dir: Path = REPO_ROOT / "media" / "profile_images"
    jwt_secret: str = "change-me-to-a-secret-jwt-signing-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    cors_origins: list[str] = ["*"]
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/api/v1/me/music-provider/spotify/callback"
    spotify_token_encryption_key: str = "Z2gwSwfJWFGkb502WXm7rf21GzM3ZhggiMtT_S1CsOI="
    # Geo Platform (siehe geo/providers.py::get_default_geo_search_provider) -
    # optionales Feature, exakt wie spotify_client_id/-secret: ohne Key läuft
    # alles mit dem kostenlosen Nominatim-Adapter (Zero-Config-Dev/Test).
    google_places_api_key: str = ""
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_username: str = "placeholder@example.com"
    smtp_password: str = "placeholder-app-password"
    smtp_from_email: str = "no-reply@partyplanning.local"
    password_reset_base_url: str = "partyplanning://reset"
    email_verification_base_url: str = "partyplanning://verify"
    account_unlock_base_url: str = "partyplanning://unlock"
    # Komma-separierte E-Mail-Liste, siehe backend/app/core/auth.py::require_admin.
    # Bewusst kein echtes Rollen-/Superuser-Modell (siehe Plan) - isoliert
    # hinter genau einer Dependency, damit ein späteres echtes System das
    # hier problemlos ersetzen kann.
    admin_emails: str = ""
    # Brute-Force-Schutz für /auth/login (siehe routers/auth.py + accounts/
    # user_storage.py::record_failed_login) - 3-stufige Eskalation statt einer
    # einzigen, unbegrenzt wiederholbaren Sperre: Tier 1 (5 Versuche / 15 Min)
    # ist der bisherige, gängige OWASP-Mittelweg für normale Tippfehler; Tier 2
    # (3 weitere Versuche / 1 Tag) und Tier 3 (5 weitere Versuche / dauerhafte
    # Blockierung, nur per E-Mail-Unlock aufhebbar) machen automatisiertes
    # Passwort-Raten über einen einzelnen Account hinweg unpraktikabel, statt
    # nur zu verlangsamen.
    login_tier1_max_attempts: int = 5
    login_tier1_lockout_minutes: int = 15
    login_tier2_max_attempts: int = 3
    login_tier2_lockout_minutes: int = 60 * 24
    login_tier3_max_attempts: int = 5


settings = Settings()

# Security-Hardening-Pass: diese Werte sind absichtlich unsichere, aber
# lauffähige Platzhalter (siehe jeweilige Feld-Defaults oben) - ein
# Deployment mit unveränderten Werten würde JWTs fälschbar bzw.
# gespeicherte Spotify-Tokens mit einem öffentlich im Repo stehenden
# Schlüssel "verschlüsseln" machen. Nur eine Warnung, kein harter Fail -
# lokale Dev-/Test-Läufe (inkl. der gesamten pytest-Suite, die `TestClient`
# ohne echte Secrets bootet) müssen weiterhin ohne jede Konfiguration
# funktionieren; das Signal ist für den Betreiber vor einem echten
# Deployment gedacht.
_INSECURE_DEFAULT_SECRETS = {
    "jwt_secret": "change-me-to-a-secret-jwt-signing-key",
    "spotify_token_encryption_key": "Z2gwSwfJWFGkb502WXm7rf21GzM3ZhggiMtT_S1CsOI=",
}


def warn_if_insecure_defaults(settings_obj: Settings) -> list[str]:
    """Loggt eine Warnung für jedes Feld in ``_INSECURE_DEFAULT_SECRETS``,
    das noch seinen eingecheckten Platzhalter-Wert trägt, und gibt die
    betroffenen Feldnamen zurück (für Tests - keine Notwendigkeit, Log-Output
    zu parsen)."""
    insecure = [
        name for name, placeholder in _INSECURE_DEFAULT_SECRETS.items() if getattr(settings_obj, name) == placeholder
    ]
    for name in insecure:
        _logger.warning(
            "SECURITY WARNING: settings.%s is still set to its checked-in placeholder value. "
            "Set a real secret via the %s environment variable before deploying.",
            name,
            name.upper(),
        )
    return insecure
