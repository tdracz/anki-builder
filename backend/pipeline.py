"""
Scrape pipeline — orchestrates fetching, media download, DB persistence,
and optional immediate sync to Anki for a list of words.
"""

import logging
from pathlib import Path
from typing import Callable, Optional
import threading

import requests

from . import database as db
from .anki_connect import client as anki, AnkiConnectError
from .image_fetcher import fetch_image
from .languages import get_module
from .languages.base import WordData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cancellation flag — set to stop any in-progress import batch
# ---------------------------------------------------------------------------

_cancel_event = threading.Event()


def request_cancel() -> None:
    """Signal the current import batch to stop after the current word."""
    _cancel_event.set()


def clear_cancel() -> None:
    """Clear the cancellation flag before starting a new import."""
    _cancel_event.clear()


def is_cancelled() -> bool:
    return _cancel_event.is_set()


def _render_definitions_html(defs: list[str]) -> str:
    """
    Render definitions list to HTML.
    Handles __pos:X__ group headers and __sub__ sub-definitions.
    """
    if not defs:
        return ""

    html_parts: list[str] = []

    # First pass: group into structured data
    groups: list[dict] = []  # [{pos, items: [{text, subs}]}]
    current_group: dict = {"pos": None, "items": []}

    for entry in defs:
        if entry.startswith("__pos:") and entry.endswith("__"):
            if current_group["items"]:
                groups.append(current_group)
            current_group = {"pos": entry[6:-2], "items": []}
        elif entry.startswith("__sub__"):
            sub_text = entry[7:]
            if not current_group["items"]:
                # Sub-items with no parent — create a virtual empty parent
                current_group["items"].append({"text": "", "subs": []})
            current_group["items"][-1]["subs"].append(sub_text)
        else:
            current_group["items"].append({"text": entry, "subs": []})

    if current_group["items"]:
        groups.append(current_group)

    # Second pass: render to HTML
    for group in groups:
        if group["pos"]:
            html_parts.append(f'<p class="pos-header"><em>{group["pos"]}</em></p>')
        html_parts.append("<ol>")
        for item in group["items"]:
            if item["text"]:
                html_parts.append(f"<li>{item['text']}")
            else:
                html_parts.append("<li>")
            if item["subs"]:
                html_parts.append('<ol style="list-style-type:lower-alpha;margin-left:1em">')
                for sub in item["subs"]:
                    html_parts.append(f"<li>{sub}</li>")
                html_parts.append("</ol>")
            html_parts.append("</li>")
        html_parts.append("</ol>")

    return "".join(html_parts)


def _build_anki_fields(word_row: dict) -> dict:
    """Convert a DB row into the field dict expected by AnkiConnect."""
    defs = word_row.get("definitions") or []
    sents = word_row.get("sentences") or []
    syns = word_row.get("synonyms") or []
    ants = word_row.get("antonyms") or []

    def_html = _render_definitions_html(defs)
    sent_html = "<ul>" + "".join(f"<li>{s}</li>" for s in sents) + "</ul>" if sents else ""
    syn_text = ", ".join(syns) if syns else ""
    ant_text = ", ".join(ants) if ants else ""

    audio_tag = f"[sound:{word_row['audio_file']}]" if word_row.get("audio_file") else ""
    image_tag = f'<img src="{word_row["image_file"]}">' if word_row.get("image_file") else ""

    return {
        "Word": word_row["word"],
        "Language": word_row["language_code"],
        "IPA": word_row.get("ipa") or "",
        "Audio": audio_tag,
        "Image": image_tag,
        "Translation": word_row.get("translation") or "",
        "TranslationLanguage": word_row.get("translation_language") or "",
        "Definitions": def_html,
        "Synonyms": syn_text,
        "Antonyms": ant_text,
        "Etymology": word_row.get("etymology") or "",
        "Sentences": sent_html,
        "Source": (
            f'<a href="{word_row["source_url"]}">{word_row["source_url"]}</a>'
            if word_row.get("source_url") else ""
        ),
    }


def _check_anki_once() -> bool:
    """
    Single connection check. Returns True if AnkiConnect is reachable
    and the note model is bootstrapped. Call this once per batch, not per word.
    """
    status = anki.check_connection()
    if not status["connected"]:
        logger.info("Anki not reachable — cards will queue as pending_sync.")
        return False
    try:
        anki.ensure_model()
        return True
    except AnkiConnectError as exc:
        logger.warning("Anki model bootstrap failed: %s", exc)
        return False


def sync_word_to_anki(word: str, language_code: str) -> bool:
    """
    Push a single word from the DB to Anki.
    Uses deck_name stored on the word row; falls back to module default.
    """
    row = db.get_word(word, language_code)
    if not row:
        return False

    module = get_module(language_code)
    deck_name = row.get("deck_name") or module.deck_name
    fields = _build_anki_fields(row)

    try:
        # Upload media files first
        media_dir = db.MEDIA_DIR
        if row.get("audio_file"):
            path = media_dir / row["audio_file"]
            if path.exists():
                anki.store_media(row["audio_file"], path)
        if row.get("image_file"):
            path = media_dir / row["image_file"]
            if path.exists():
                anki.store_media(row["image_file"], path)

        anki.ensure_deck(deck_name)
        anki.register_deck(deck_name, language_code)  # idempotent — marks deck as app-owned
        existing_id = anki.find_note_id(word, deck_name)
        if existing_id:
            anki.update_note(existing_id, fields)
            db.set_anki_note_id(word, language_code, existing_id)
        else:
            note_id = anki.add_note(deck_name, fields)
            if note_id is None:
                # Anki refused (duplicate by first field) — try to find the existing note
                note_id = anki.find_note_id(word, deck_name)
            if note_id is not None:
                db.set_anki_note_id(word, language_code, note_id)
            else:
                logger.warning("Could not add or find note for '%s' in Anki", word)
                return False
        return True
    except AnkiConnectError as exc:
        logger.error("Anki sync failed for '%s': %s", word, exc)
        return False


def process_words(
    words: list[str],
    language_code: str,
    progress_cb: Optional[Callable[[str, str], None]] = None,
    auto_sync: bool = True,
    fetch_images: bool = False,
) -> list[dict]:
    """
    Full pipeline for a batch of words.
    Checks the cancellation flag between each word and stops early if set.
    fetch_images=False (default) skips image search for all words.
    """
    clear_cancel()
    anki_available = _check_anki_once() if auto_sync else False

    results = []
    for word in words:
        if is_cancelled():
            logger.info("Import cancelled after %d/%d words", len(results), len(words))
            if progress_cb:
                progress_cb("", "cancelled")
            break
        results.append(
            _process_single(word, language_code, anki_available, progress_cb, fetch_images)
        )
    return results


def process_word(
    word: str,
    language_code: str,
    progress_cb: Optional[Callable[[str, str], None]] = None,
    anki_available: Optional[bool] = None,
    auto_sync: bool = True,
    fetch_images: bool = False,
) -> dict:
    """
    Full pipeline for a single word.
    When auto_sync=False, always queues regardless of Anki availability.
    """
    if not auto_sync:
        anki_available = False
    elif anki_available is None:
        anki_available = _check_anki_once()
    return _process_single(word, language_code, anki_available, progress_cb, fetch_images)


def _process_single(
    word: str,
    language_code: str,
    anki_available: bool,
    progress_cb: Optional[Callable[[str, str], None]],
    fetch_images: bool = False,
) -> dict:
    def notify(status: str):
        if progress_cb:
            progress_cb(word, status)

    module = get_module(language_code)
    notify("scraping")

    # 1. Scrape — catch all errors so one bad word doesn't abort the batch
    try:
        data: WordData = module.fetch(word)
    except Exception as exc:
        logger.error("Scrape failed for '%s': %s", word, exc)
        db.set_error(word, language_code, f"Scrape failed: {exc}")
        notify("error")
        return db.get_word(word, language_code) or {}

    # Store with "done" only if we actually got content; otherwise mark error
    if data.not_found:
        db.upsert_word(data, status="not_found")
        notify("not_found")
        return db.get_word(word, language_code) or {}

    if not data.definitions and not data.ipa:
        db.upsert_word(data, status="error")
        db.set_error(word, language_code, "No definitions or pronunciation found on the page")
        notify("error")
        return db.get_word(word, language_code) or {}

    # Preserve existing deck_name if already set
    existing = db.get_word(word, language_code)
    existing_deck = existing.get("deck_name") if existing else None
    db.upsert_word(data, status="done", deck_name=existing_deck)
    notify("scraped")

    # 2. Download audio
    if data.audio_url:
        audio_filename = _download_audio(data.audio_url, word, language_code)
        if audio_filename:
            db.set_audio_file(word, language_code, audio_filename)
            notify("audio_done")

    # 3. Download image — only if explicitly requested
    if fetch_images and module.should_fetch_image(data):
        query = data.image_query or word
        image_filename = fetch_image(query, db.MEDIA_DIR)
        if image_filename:
            db.set_image_file(word, language_code, image_filename)
            notify("image_done")

    # 4. Mark pending_sync
    db.set_status(word, language_code, "pending_sync")

    # 5. Sync to Anki — only if we already know it's reachable
    if anki_available:
        synced = sync_word_to_anki(word, language_code)
        notify("synced" if synced else "pending_sync")
    else:
        notify("pending_sync")

    return db.get_word(word, language_code) or {}


def _download_audio(url: str, word: str, language_code: str) -> Optional[str]:
    """Download audio MP3 and return the filename, or None on failure."""
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("Content-Type", "")
        if "audio" not in content_type and not url.endswith(".mp3"):
            return None
        slug = word.lower().replace(" ", "_")
        filename = f"{language_code}_{slug}.mp3"
        dest = db.MEDIA_DIR / filename
        if not dest.exists():
            dest.write_bytes(resp.content)
        return filename
    except Exception as exc:
        logger.warning("Audio download failed for '%s': %s", word, exc)
        return None


def delete_word_from_anki(word: str, language_code: str, auto_sync: bool = True) -> None:
    """
    Delete a word from Anki and the local DB.
    When auto_sync=False, marks as pending_delete instead of deleting immediately.
    """
    if not auto_sync:
        db.queue_delete(word, language_code)
        return
    note_id = db.delete_word(word, language_code)
    if note_id:
        try:
            anki.delete_notes([note_id])
        except AnkiConnectError as exc:
            logger.warning("Could not delete Anki note %s: %s", note_id, exc)


def rescrape_word(word: str, language_code: str, deck_name: Optional[str] = None) -> dict:
    """Re-scrape a word and queue it for sync. Preserves the existing deck assignment."""
    db.set_status(word, language_code, "pending")
    return process_word(word, language_code, auto_sync=False)


def flush_pending_sync(language_code: Optional[str] = None) -> dict:
    """
    Push all pending_sync words to Anki and execute all pending_delete deletions.
    Connection is checked once at the start.
    Returns {"synced": int, "failed": int, "errors": list[str]}.
    """
    pending_sync = db.get_pending_sync(language_code)
    pending_delete = db.get_pending_deletes(language_code)

    if not pending_sync and not pending_delete:
        return {"synced": 0, "failed": 0, "errors": []}

    if not _check_anki_once():
        total = len(pending_sync) + len(pending_delete)
        return {
            "synced": 0,
            "failed": total,
            "errors": ["Anki is not running or AnkiConnect is not reachable."],
        }

    synced = 0
    failed = 0
    errors = []

    # Process pending syncs (updates/new cards)
    for row in pending_sync:
        ok = sync_word_to_anki(row["word"], row["language_code"])
        if ok:
            synced += 1
        else:
            failed += 1
            errors.append(row["word"])

    # Process pending deletes
    for row in pending_delete:
        try:
            note_id = db.delete_word(row["word"], row["language_code"])
            if note_id:
                anki.delete_notes([note_id])
            synced += 1
        except Exception as exc:
            logger.error("Failed to delete '%s' from Anki: %s", row["word"], exc)
            failed += 1
            errors.append(row["word"])

    return {"synced": synced, "failed": failed, "errors": errors}
