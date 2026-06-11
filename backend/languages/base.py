"""
Base interface for language modules.
Each language is a plugin that implements LanguageModule and returns WordData.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WordData:
    word: str
    language_code: str
    ipa: Optional[str] = None
    audio_url: Optional[str] = None
    definitions: list[str] = field(default_factory=list)
    etymology: Optional[str] = None
    sentences: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    antonyms: list[str] = field(default_factory=list)
    pos: Optional[str] = None
    image_query: Optional[str] = None
    source_url: Optional[str] = None
    thesaurus_url: Optional[str] = None
    not_found: bool = False   # True when the dictionary has no entry for this word


class WordNotFoundError(Exception):
    """Raised when a word has no entry in the dictionary (e.g. HTTP 404)."""


class LanguageModule(ABC):
    language_code: str   # e.g. "en"
    language_name: str   # e.g. "English"
    deck_name: str       # default Anki deck name

    @abstractmethod
    def fetch(self, word: str) -> WordData:
        """Fetch all card data for a word from the language's dictionary source."""
        ...

    @abstractmethod
    def should_fetch_image(self, data: WordData) -> bool:
        """Return True if fetching an image makes sense for this word."""
        ...
