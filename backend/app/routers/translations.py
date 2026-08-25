from __future__ import annotations

from fastapi import APIRouter, HTTPException

import translations as translations_module

router = APIRouter(prefix="/api/v1/translations", tags=["translations"])


@router.get("/languages")
def list_languages() -> dict:
    return {
        "default_language": translations_module.DEFAULT_LANGUAGE,
        "primary_languages": [
            {"code": code, "name": name, "emoji": emoji}
            for code, name, emoji in translations_module.PRIMARY_LANGUAGES
        ],
        "extra_languages": [
            {"code": code, "name": name, "emoji": emoji}
            for code, name, emoji in translations_module.EXTRA_LANGUAGES
        ],
    }


@router.get("/{lang}")
def get_translations_for_language(lang: str) -> dict:
    """Liefert die vollständige ``ui``-Übersetzungstabelle für ``lang``, mit
    derselben Fallback-Kette wie ``translations.t()``
    (lang -> FALLBACK_LANGUAGE -> DEFAULT_LANGUAGE), damit ein Mobile-Client
    lokal wie ``t()`` nachschlagen kann, ohne einen Request pro Key zu
    brauchen."""
    all_codes = {code for code, _, _ in translations_module.ALL_LANGUAGES}
    if lang not in all_codes:
        raise HTTPException(status_code=404, detail=f"Unbekannte Sprache: {lang}")
    merged: dict[str, str] = {}
    for candidate in (
        translations_module.DEFAULT_LANGUAGE,
        translations_module.FALLBACK_LANGUAGE,
        lang,
    ):
        merged.update(translations_module.LANG_DATA.get(candidate, {}).get("ui", {}))
    return merged
