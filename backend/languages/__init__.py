"""
Language module registry.
Add new language modules here to make them available in the app.
"""

from .base import LanguageModule, WordData
from .english import EnglishModule
from .german import GermanModule

# Registry: language_code -> module instance
_REGISTRY: dict[str, LanguageModule] = {}


def _register(module: LanguageModule) -> None:
    _REGISTRY[module.language_code] = module


_register(EnglishModule())
_register(GermanModule())


def get_module(language_code: str) -> LanguageModule:
    module = _REGISTRY.get(language_code)
    if not module:
        raise ValueError(f"No language module registered for code: '{language_code}'")
    return module


def list_languages() -> list[dict]:
    """Return a list of available languages for the UI."""
    return [
        {
            "code": m.language_code,
            "name": m.language_name,
            "deck": m.deck_name,
        }
        for m in _REGISTRY.values()
    ]
