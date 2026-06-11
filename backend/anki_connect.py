"""
AnkiConnect HTTP API client.
Communicates with the AnkiConnect add-on running inside Anki on localhost:8765.
"""

import base64
import logging
import time
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
ANKI_CONNECT_VERSION = 6
MODEL_NAME = "VocabBuilder"
DECK_META_MODEL = "VocabBuilderDeck"  # sentinel model — no card templates, marks app-owned decks

CARD_FRONT = """\
<div class="word">{{Word}}</div>
{{Audio}}
<div class="lang">{{Language}}</div>
"""

CARD_BACK = """\
{{FrontSide}}
<hr>
<div class="ipa">{{IPA}}</div>
{{Image}}
{{#Source}}<div class="source">{{Source}}</div>{{/Source}}
<div class="definitions">{{Definitions}}</div>
{{#Synonyms}}
<div class="synonyms"><em>Synonyms:</em> {{Synonyms}}</div>
{{/Synonyms}}
{{#Antonyms}}
<div class="antonyms"><em>Antonyms:</em> {{Antonyms}}</div>
{{/Antonyms}}
{{#Sentences}}
<div class="section-title">Example Sentences</div>
<div class="sentences">{{Sentences}}</div>
{{/Sentences}}
{{#Translation}}
<div class="section-title">Translation{{#TranslationLanguage}} ({{TranslationLanguage}}){{/TranslationLanguage}}</div>
<div class="translation">{{Translation}}</div>
{{/Translation}}
{{#Etymology}}
<div class="section-title">Word Origin</div>
<div class="etymology">{{Etymology}}</div>
{{/Etymology}}
"""

CARD_CSS = """\
.card { font-family: Georgia, serif; font-size: 18px; text-align: center;
        color: #222; background: #fff; padding: 20px; }
.word { font-size: 2em; font-weight: bold; margin-bottom: 8px; }
.ipa  { font-size: 1.1em; color: #555; margin-bottom: 12px; }
.lang { font-size: 0.8em; color: #aaa; }
.definitions { text-align: left; margin: 12px 0; }
.synonyms    { text-align: left; font-size: 0.9em; color: #555; margin-top: 8px; }
.antonyms    { text-align: left; font-size: 0.9em; color: #b91c1c; margin-top: 4px; }
.translation { text-align: left; font-size: 1em; color: #2563eb; margin: 8px 0; padding: 8px; background: #eff6ff; border-radius: 6px; }
.etymology   { text-align: left; font-size: 0.9em; color: #666; margin-top: 12px; border-left: 3px solid #ddd; padding-left: 8px; }
.sentences   { text-align: left; font-style: italic; color: #444; margin-top: 12px; }
.sentences li { margin-bottom: 4px; }
.source      { text-align: center; margin-top: 16px; font-size: 0.8em; }
.source a    { color: #888; text-decoration: none; }
.section-title { text-align: left; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.1em; color: #999; margin-top: 16px; margin-bottom: 4px; font-weight: 600; }
img { max-width: 300px; max-height: 200px; border-radius: 6px; margin: 10px auto; display: block; }
"""


class AnkiConnectError(Exception):
    pass


class AnkiConnectClient:

    def invoke(self, action: str, **params) -> Any:
        payload = {"action": action, "version": ANKI_CONNECT_VERSION, "params": params}
        try:
            resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise AnkiConnectError("Cannot reach AnkiConnect. Is Anki running?")
        except requests.RequestException as exc:
            raise AnkiConnectError(f"AnkiConnect request failed: {exc}")

        body = resp.json()
        if body.get("error"):
            raise AnkiConnectError(body["error"])
        return body["result"]

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def check_connection(self) -> dict:
        """Return {"connected": bool, "version": int|None, "message": str}.
        Result is cached for 10 seconds to avoid hammering AnkiConnect on every edit.
        """
        now = time.monotonic()
        if hasattr(self, "_conn_cache") and now - self._conn_cache_ts < 10:
            return self._conn_cache  # type: ignore[return-value]
        try:
            version = self.invoke("version")
            result = {"connected": True, "version": version, "message": "AnkiConnect is running."}
        except AnkiConnectError as exc:
            result = {"connected": False, "version": None, "message": str(exc)}
        self._conn_cache = result
        self._conn_cache_ts = now
        return result

    def invalidate_cache(self) -> None:
        """Force the next check_connection call to hit AnkiConnect."""
        if hasattr(self, "_conn_cache"):
            del self._conn_cache

    # ------------------------------------------------------------------
    # Model bootstrap
    # ------------------------------------------------------------------

    def ensure_model(self) -> None:
        """Create or update the VocabBuilder note model in Anki."""
        existing = self.invoke("modelNames")

        _EXPECTED_FIELDS = ["Word", "Language", "IPA", "Audio", "Image",
                            "Translation", "TranslationLanguage", "Definitions", "Synonyms", "Antonyms",
                            "Etymology", "Sentences", "Source"]

        if MODEL_NAME not in existing:
            logger.info("Creating note model '%s' in Anki", MODEL_NAME)
            self.invoke(
                "createModel",
                modelName=MODEL_NAME,
                inOrderFields=_EXPECTED_FIELDS,
                css=CARD_CSS,
                cardTemplates=[{
                    "Name": "VocabBuilder Card",
                    "Front": CARD_FRONT,
                    "Back": CARD_BACK,
                }],
            )
        else:
            # Add any missing fields to the existing model
            current_fields = self.invoke("modelFieldNames", modelName=MODEL_NAME)
            for field in _EXPECTED_FIELDS:
                if field not in current_fields:
                    logger.info("Adding field '%s' to model '%s'", field, MODEL_NAME)
                    self.invoke("modelFieldAdd", modelName=MODEL_NAME, fieldName=field)
            # Update card templates to use the latest HTML/CSS
            templates = self.invoke("modelTemplates", modelName=MODEL_NAME)
            if templates:
                template_name = list(templates.keys())[0]
                self.invoke("updateModelTemplates", model={
                    "name": MODEL_NAME,
                    "templates": {template_name: {"Front": CARD_FRONT, "Back": CARD_BACK}},
                })
            self.invoke("updateModelStyling", model={"name": MODEL_NAME, "css": CARD_CSS})
        if DECK_META_MODEL not in existing:
            logger.info("Creating deck sentinel model '%s' in Anki", DECK_META_MODEL)
            self.invoke(
                "createModel",
                modelName=DECK_META_MODEL,
                inOrderFields=["DeckName", "Language", "CreatedAt"],
                css=".card { display: none; }",  # hide cards — this model is metadata only
                cardTemplates=[{
                    "Name": "Sentinel",
                    "Front": "{{DeckName}}",
                    "Back": "",
                }],
            )

    # ------------------------------------------------------------------
    # Deck
    # ------------------------------------------------------------------

    def ensure_deck(self, deck_name: str) -> None:
        self.invoke("createDeck", deck=deck_name)

    def register_deck(self, deck_name: str, language_code: str = "en") -> None:
        """Add a sentinel note to mark this deck as app-owned. Idempotent.
        The note is immediately suspended so it never appears in reviews.
        """
        existing = self.invoke("findNotes", query=f'note:{DECK_META_MODEL} DeckName:"{deck_name}"')
        if existing:
            return  # already registered
        from datetime import datetime, timezone
        note_id = self.invoke(
            "addNote",
            note={
                "deckName": deck_name,
                "modelName": DECK_META_MODEL,
                "fields": {
                    "DeckName": deck_name,
                    "Language": language_code,
                    "CreatedAt": datetime.now(timezone.utc).isoformat(),
                },
                "options": {"allowDuplicate": False},
                "tags": ["vocab-builder-deck"],
            },
        )
        # Suspend immediately — sentinel notes must never appear in reviews
        if note_id:
            try:
                # Get the card IDs for this note and suspend them
                cards = self.invoke("findCards", query=f"nid:{note_id}")
                if cards:
                    self.invoke("suspend", cards=cards)
            except AnkiConnectError as exc:
                logger.warning("Could not suspend sentinel card for '%s': %s", deck_name, exc)

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def find_note_id(self, word: str, deck_name: str) -> Optional[int]:
        """Return the existing note ID for a word, or None."""
        query = f'deck:"{deck_name}" Word:"{word}"'
        results = self.invoke("findNotes", query=query)
        return results[0] if results else None

    def add_note(self, deck_name: str, fields: dict) -> Optional[int]:
        """Add a new note and return its ID, or None if Anki rejected it (e.g. duplicate)."""
        note_id = self.invoke(
            "addNote",
            note={
                "deckName": deck_name,
                "modelName": MODEL_NAME,
                "fields": fields,
                "options": {"allowDuplicate": False, "duplicateScope": "deck"},
                "tags": ["vocab-builder"],
            },
        )
        return note_id  # may be None if Anki refused the note

    def update_note(self, note_id: int, fields: dict) -> None:
        """Update fields on an existing note."""
        self.invoke("updateNoteFields", note={"id": note_id, "fields": fields})

    def store_media(self, filename: str, file_path: Path) -> None:
        """Upload a media file (audio/image) to Anki's media collection."""
        data = base64.b64encode(file_path.read_bytes()).decode()
        self.invoke("storeMediaFile", filename=filename, data=data)

    def delete_notes(self, note_ids: list[int]) -> None:
        """Delete notes from Anki by ID."""
        self.invoke("deleteNotes", notes=note_ids)

    def get_app_decks(self) -> list[str]:
        """Return deck names registered as app-owned via sentinel notes.
        Single query — no per-deck iteration.
        """
        try:
            note_ids = self.invoke("findNotes", query=f"note:{DECK_META_MODEL}")
            if not note_ids:
                return []
            notes_info = self.invoke("notesInfo", notes=note_ids)
            decks = []
            seen: set[str] = set()
            for note in notes_info:
                name = note.get("fields", {}).get("DeckName", {}).get("value", "")
                if name and name not in seen:
                    seen.add(name)
                    decks.append(name)
            return sorted(decks)
        except AnkiConnectError:
            return []

    def get_all_decks(self) -> list[str]:
        """Return all deck names from Anki."""
        try:
            return sorted(self.invoke("deckNames"))
        except AnkiConnectError:
            return []

    def sync(self) -> None:
        """Trigger an AnkiWeb sync (best-effort, ignore errors)."""
        try:
            self.invoke("sync")
        except AnkiConnectError as exc:
            logger.warning("AnkiWeb sync failed: %s", exc)


# Module-level singleton
client = AnkiConnectClient()
