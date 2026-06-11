"""
Pydantic models used by the FastAPI layer.
"""

from typing import Optional
from pydantic import BaseModel


class WordResponse(BaseModel):
    id: int
    word: str
    language_code: str
    ipa: Optional[str] = None
    audio_file: Optional[str] = None
    image_file: Optional[str] = None
    definitions: list[str] = []
    etymology: Optional[str] = None
    sentences: list[str] = []
    synonyms: list[str] = []
    antonyms: list[str] = []
    translation: Optional[str] = None
    translation_language: Optional[str] = None
    pos: Optional[str] = None
    source_url: Optional[str] = None
    thesaurus_url: Optional[str] = None
    deck_name: Optional[str] = None
    anki_note_id: Optional[int] = None
    scraped_at: Optional[str] = None
    error_message: Optional[str] = None
    status: str


class WordUpdateRequest(BaseModel):
    ipa: Optional[str] = None
    definitions: Optional[list[str]] = None
    etymology: Optional[str] = None
    sentences: Optional[list[str]] = None
    pos: Optional[str] = None


class ImportResult(BaseModel):
    total: int
    new: int
    duplicates: int
    words: list[str]
    duplicate_words: list[str]


class SyncResult(BaseModel):
    synced: int
    failed: int
    errors: list[str] = []


class AnkiStatus(BaseModel):
    connected: bool
    version: Optional[int] = None
    message: str


class LanguageInfo(BaseModel):
    code: str
    name: str
    deck: str


class DeckInfo(BaseModel):
    name: str
    is_app_deck: bool = True


class CreateDeckRequest(BaseModel):
    name: str


class BulkWordsRequest(BaseModel):
    lang: str
    words: list[str]
    auto_sync: bool = False
    deck: Optional[str] = None


class AnkiImportPreview(BaseModel):
    total: int
    new: int
    duplicates: list[dict]


class AnkiImportRequest(BaseModel):
    deck_name: str
    duplicate_action: str = "skip"   # "skip" | "overwrite"
    skip_words: list[str] = []
    overwrite_words: list[str] = []


class AnkiImportResult(BaseModel):
    imported: int
    skipped: int
    overwritten: int
    errors: list[str] = []
