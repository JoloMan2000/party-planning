"""Backend-Konfiguration (Env-Var-basiert, siehe Phase-1-Plan Schritt 1/4).

Ersetzt die Streamlit-``st.secrets``-Quelle aus ``"Party Planning.py"`` durch
Standard-Umgebungsvariablen, da ``backend/`` kein Streamlit-Prozess ist.
Nutzt ``pydantic-settings`` (liest optional eine ``.env``-Datei im Repo-Root),
mirroring der übrigen Projekt-Konvention "Defaults, die auch ohne jede
Konfiguration ein lauffähiges lokales Dev-Setup ergeben".
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_username: str = "placeholder@example.com"
    smtp_password: str = "placeholder-app-password"
    smtp_from_email: str = "no-reply@partyplanning.local"
    password_reset_base_url: str = "partyplanning://reset"
    # Komma-separierte E-Mail-Liste, siehe backend/app/core/auth.py::require_admin.
    # Bewusst kein echtes Rollen-/Superuser-Modell (siehe Plan) - isoliert
    # hinter genau einer Dependency, damit ein späteres echtes System das
    # hier problemlos ersetzen kann.
    admin_emails: str = ""
    # Brute-Force-Schutz für /auth/login (siehe routers/auth.py + accounts/
    # user_storage.py::record_failed_login). 5 Versuche / 15 Minuten Sperre
    # ist ein gängiger Mittelweg (OWASP nennt 3-5 als üblichen Schwellwert für
    # nutzerseitige Logins) - genug Toleranz für normale Tippfehler, aber eng
    # genug, dass automatisiertes Passwort-Raten unpraktikabel langsam wird.
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15


settings = Settings()
