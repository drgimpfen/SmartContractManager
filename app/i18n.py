from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from flask import request

DEFAULT_LOCALE = "en"
LOCALE_DIR = Path(__file__).resolve().parent / "locales"
LANGUAGE_NAMES = {"en": "English", "de": "Deutsch"}


def load_translations() -> dict[str, dict[str, Any]]:
    translations: dict[str, dict[str, Any]] = {}
    if not LOCALE_DIR.exists():
        return translations
    for locale_file in sorted(LOCALE_DIR.glob("*.json")):
        locale = locale_file.stem.lower()
        try:
            with locale_file.open("r", encoding="utf-8") as handle:
                content = json.load(handle)
            if isinstance(content, dict):
                translations[locale] = content
        except Exception:
            continue
    return translations


TRANSLATIONS = load_translations()
SUPPORTED_LOCALES = sorted(TRANSLATIONS.keys()) or [DEFAULT_LOCALE]


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    locale = locale.lower().split("-")[0]
    if locale in SUPPORTED_LOCALES:
        return locale
    return DEFAULT_LOCALE


def get_locale() -> str:
    # 1. Query parameter ?lang=
    try:
        lang = request.args.get("lang")
        if lang:
            loc = normalize_locale(lang)
            if loc in SUPPORTED_LOCALES:
                return loc
    except Exception:
        pass

    # 2. Cookie lang
    try:
        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            loc = normalize_locale(cookie_lang)
            if loc in SUPPORTED_LOCALES:
                return loc
    except Exception:
        pass

    # 3. Accept-Language header
    try:
        accept = request.headers.get("Accept-Language", "")
        for item in accept.split(","):
            code = item.split(";")[0].strip().lower().split("-")[0]
            if code in SUPPORTED_LOCALES:
                return code
    except Exception:
        pass

    # 4. Fallback: DEFAULT_LOCALE
    return DEFAULT_LOCALE


def _lookup_translation(translations: dict[str, Any], key: str) -> str | None:
    current: Any = translations
    for segment in key.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return str(current) if not isinstance(current, dict) else None


def translate(key: str, locale: str | None = None, **kwargs: Any) -> str:
    global TRANSLATIONS
    try:
        from flask import current_app
        if current_app and current_app.debug:
            TRANSLATIONS = load_translations()
    except Exception:
        pass

    locale = normalize_locale(locale)
    translation = _lookup_translation(TRANSLATIONS.get(locale, {}), key)
    # Fallback to default locale if not found
    if translation is None and locale != DEFAULT_LOCALE:
        translation = _lookup_translation(TRANSLATIONS.get(DEFAULT_LOCALE, {}), key)
    if translation is None:
        return key if not kwargs else key.format(**kwargs)
    if kwargs:
        try:
            return translation.format(**kwargs)
        except Exception:
            return translation
    return translation
