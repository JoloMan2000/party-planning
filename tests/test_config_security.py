"""Tests für `warn_if_insecure_defaults` (Security-Hardening-Pass, siehe
`backend/app/core/config.py`) - stellt sicher, dass eingecheckte Platzhalter-
Secrets erkannt werden, echte (überschriebene) Werte aber nicht fälschlich
als unsicher gemeldet werden."""

from __future__ import annotations

from backend.app.core.config import Settings, warn_if_insecure_defaults


def test_warn_if_insecure_defaults_meldet_platzhalter_bei_default_settings():
    insecure = warn_if_insecure_defaults(Settings())
    assert set(insecure) == {"jwt_secret", "spotify_token_encryption_key"}


def test_warn_if_insecure_defaults_ist_leer_wenn_secrets_ueberschrieben_sind():
    settings_obj = Settings(
        jwt_secret="a-real-randomly-generated-secret",
        spotify_token_encryption_key="a-real-randomly-generated-fernet-key",
    )
    assert warn_if_insecure_defaults(settings_obj) == []
