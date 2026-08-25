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
    admin_password: str = "change-me-to-a-secret-value"
    jwt_secret: str = "change-me-to-a-secret-jwt-signing-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["*"]


settings = Settings()
