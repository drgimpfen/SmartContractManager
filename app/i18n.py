from __future__ import annotations
from pathlib import Path
from typing import Any
import json

from fastapi import Request
from fastapi.templating import Jinja2Templates

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


def get_locale(request: Request | None = None) -> str:
    if request is None:
        return DEFAULT_LOCALE
    lang = request.query_params.get("lang") or request.cookies.get("lang")
    if lang:
        locale = normalize_locale(lang)
        if locale in SUPPORTED_LOCALES:
            return locale
    accept = request.headers.get("accept-language", "")
    for item in accept.split(","):
        code = item.split(";")[0].strip().lower().split("-")[0]
        if code in SUPPORTED_LOCALES:
            return code
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
    locale = normalize_locale(locale)
    translation = _lookup_translation(TRANSLATIONS.get(locale, {}), key)
    if translation is None:
        return key if not kwargs else key.format(**kwargs)
    if kwargs:
        try:
            return translation.format(**kwargs)
        except Exception:
            return translation
    return translation


def gettext(request: Request, key: str, **kwargs: Any) -> str:
    return translate(key, get_locale(request), **kwargs)


def translation_context(request: Request) -> dict[str, Any]:
    return {
        "_": lambda key, **kwargs: translate(key, get_locale(request), **kwargs),
        "lang": get_locale(request),
        "languages": {code: LANGUAGE_NAMES.get(code, code) for code in SUPPORTED_LOCALES},
    }


TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates"),
    context_processors=[translation_context],
)
