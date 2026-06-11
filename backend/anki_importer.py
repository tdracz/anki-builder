"""
Import words from an Anki deck back into the local DB.
Parses rendered HTML fields back to structured data with fallbacks.
"""

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from . import database as db
from .anki_connect import client as anki, AnkiConnectError, MODEL_NAME

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field parsers — each returns clean Python data from Anki HTML field values
# ---------------------------------------------------------------------------

def _parse_definitions(html: str) -> list[str]:
    """
    Parse the Definitions field back to our internal format.

    Expected structure (our renderer):
        <p class="pos-header"><em>noun</em></p>
        <ol><li>def1</li><li>def2</li></ol>
        <p class="pos-header"><em>adjective</em></p>
        <ol><li>def3</li></ol>

    Fallback: strip all tags, split on newlines / list items.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    result: list[str] = []

    # Try structured parse first
    pos_headers = soup.find_all("p", class_="pos-header")
    if pos_headers:
        # Walk through the document in order
        for elem in soup.body.children if soup.body else soup.children:
            tag = getattr(elem, "name", None)
            if tag == "p" and "pos-header" in (elem.get("class") or []):
                pos_text = elem.get_text(strip=True).lower()
                if pos_text:
                    result.append(f"__pos:{pos_text}__")
            elif tag == "ol":
                for li in elem.find_all("li"):
                    text = li.get_text(" ", strip=True)
                    if text:
                        result.append(text)
        if result:
            return result

    # Fallback: extract all <li> items
    items = [li.get_text(" ", strip=True) for li in soup.find_all("li")]
    if items:
        return items

    # Last resort: plain text, split by newlines
    text = soup.get_text("\n", strip=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_sentences(html: str) -> list[str]:
    """
    Parse the Sentences field.
    Expected: <ul><li>sentence</li>...</ul>
    Fallback: extract any text.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    items = [li.get_text(" ", strip=True) for li in soup.find_all("li")]
    if items:
        return items
    text = soup.get_text("\n", strip=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_synonyms(text: str) -> list[str]:
    """Synonyms are stored as plain comma-separated text."""
    if not text:
        return []
    return [s.strip() for s in text.split(",") if s.strip()]


def _parse_source_url(html: str) -> Optional[str]:
    """Extract href from <a href="...">...</a>. Fallback: treat as plain URL."""
    if not html:
        return None
    # Fast path: plain URL (no HTML parsing needed, avoids BeautifulSoup warning)
    stripped = html.strip()
    if stripped.startswith("http") and "<" not in stripped:
        return stripped
    soup = BeautifulSoup(html, "lxml")
    a = soup.find("a", href=True)
    if a:
        return a["href"]
    text = soup.get_text(strip=True)
    return text if text.startswith("http") else None


def _parse_audio_filename(field: str) -> Optional[str]:
    """Extract filename from [sound:filename.mp3]."""
    if not field:
        return None
    m = re.search(r'\[sound:([^\]]+)\]', field)
    return m.group(1) if m else None


def _parse_image_filename(html: str) -> Optional[str]:
    """Extract src from <img src="filename.jpg">."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    img = soup.find("img", src=True)
    return img["src"] if img else None


def _extract_pos_from_definitions(definitions: list[str]) -> Optional[str]:
    """Derive the primary POS from the first __pos:X__ marker."""
    for d in definitions:
        if d.startswith("__pos:") and d.endswith("__"):
            return d[6:-2]
    return None


# ---------------------------------------------------------------------------
# Media retrieval
# ---------------------------------------------------------------------------

def _retrieve_media(filename: str, media_dir: Path) -> bool:
    """
    Download a media file from Anki's collection to local media_dir.
    Returns True if successful.
    """
    dest = media_dir / filename
    if dest.exists():
        return True  # already have it
    try:
        data_b64 = anki.invoke("retrieveMediaFile", filename=filename)
        if not data_b64:
            return False
        dest.write_bytes(base64.b64decode(data_b64))
        return True
    except (AnkiConnectError, Exception) as exc:
        logger.warning("Could not retrieve media '%s': %s", filename, exc)
        return False


# ---------------------------------------------------------------------------
# Note → DB record conversion
# ---------------------------------------------------------------------------

def _note_to_record(note: dict, deck_name: str) -> dict:
    """
    Convert a notesInfo entry to a dict ready for DB insertion.
    """
    fields = note.get("fields", {})

    def fv(name: str) -> str:
        return fields.get(name, {}).get("value", "") or ""

    word = fv("Word").strip().lower()
    language_code = fv("Language").strip() or "en"
    definitions = _parse_definitions(fv("Definitions"))

    audio_filename = _parse_audio_filename(fv("Audio"))
    image_filename = _parse_image_filename(fv("Image"))

    # Retrieve media files from Anki
    if audio_filename:
        _retrieve_media(audio_filename, db.MEDIA_DIR)
    if image_filename:
        _retrieve_media(image_filename, db.MEDIA_DIR)

    return {
        "word": word,
        "language_code": language_code,
        "ipa": fv("IPA") or None,
        "audio_file": audio_filename,
        "image_file": image_filename,
        "definitions": definitions,
        "etymology": fv("Etymology") or None,
        "sentences": _parse_sentences(fv("Sentences")),
        "synonyms": _parse_synonyms(fv("Synonyms")),
        "pos": _extract_pos_from_definitions(definitions),
        "source_url": _parse_source_url(fv("Source")),
        "deck_name": deck_name,
        "anki_note_id": note.get("noteId"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "status": "synced",
    }


# ---------------------------------------------------------------------------
# Preview — scan deck without writing anything
# ---------------------------------------------------------------------------

def preview_anki_import(deck_name: str) -> dict:
    """
    Scan a deck and classify each note as new / duplicate.
    Returns a summary without touching the DB.
    """
    note_ids = anki.invoke("findNotes", query=f'deck:"{deck_name}" note:{MODEL_NAME}')
    if not note_ids:
        return {"total": 0, "new": 0, "duplicates": [], "note_ids": []}

    notes_info = anki.invoke("notesInfo", notes=note_ids)
    new_count = 0
    duplicates: list[dict] = []

    for note in notes_info:
        fields = note.get("fields", {})
        word = (fields.get("Word", {}).get("value", "") or "").strip().lower()
        lang = (fields.get("Language", {}).get("value", "") or "en").strip()
        if not word:
            continue
        existing = db.get_word(word, lang)
        if existing:
            duplicates.append({
                "word": word,
                "language_code": lang,
                "local_status": existing["status"],
                "local_anki_id": existing.get("anki_note_id"),
                "anki_note_id": note.get("noteId"),
            })
        else:
            new_count += 1

    return {
        "total": len(notes_info),
        "new": new_count,
        "duplicates": duplicates,
        "note_ids": note_ids,
    }


# ---------------------------------------------------------------------------
# Execute import
# ---------------------------------------------------------------------------

def execute_anki_import(
    deck_name: str,
    duplicate_action: str = "skip",  # "skip" | "overwrite"
    skip_words: Optional[list[str]] = None,
    overwrite_words: Optional[list[str]] = None,
) -> dict:
    """
    Import VocabBuilder notes from an Anki deck into the local DB.

    duplicate_action: default action for duplicates not in skip_words/overwrite_words
    skip_words: words to always skip regardless of duplicate_action
    overwrite_words: words to always overwrite regardless of duplicate_action

    Returns {"imported": int, "skipped": int, "overwritten": int, "errors": list[str]}
    """
    skip_set = set(skip_words or [])
    overwrite_set = set(overwrite_words or [])

    from .pipeline import clear_cancel, is_cancelled
    clear_cancel()

    note_ids = anki.invoke("findNotes", query=f'deck:"{deck_name}" note:{MODEL_NAME}')
    if not note_ids:
        return {"imported": 0, "skipped": 0, "overwritten": 0, "errors": []}

    notes_info = anki.invoke("notesInfo", notes=note_ids)
    imported = 0
    skipped = 0
    overwritten = 0
    errors: list[str] = []

    for note in notes_info:
        if is_cancelled():
            logger.info("Anki import cancelled")
            break

        fields = note.get("fields", {})
        word = (fields.get("Word", {}).get("value", "") or "").strip().lower()
        lang = (fields.get("Language", {}).get("value", "") or "en").strip()
        if not word:
            continue

        try:
            record = _note_to_record(note, deck_name)
            existing = db.get_word(word, lang)

            if existing:
                # Determine action for this duplicate
                if word in skip_set:
                    action = "skip"
                elif word in overwrite_set:
                    action = "overwrite"
                else:
                    action = duplicate_action

                if action == "skip":
                    skipped += 1
                    continue
                else:  # overwrite
                    _write_record(record)
                    overwritten += 1
            else:
                _write_record(record)
                imported += 1

        except Exception as exc:
            logger.error("Failed to import word '%s': %s", word, exc)
            errors.append(word)

    return {
        "imported": imported,
        "skipped": skipped,
        "overwritten": overwritten,
        "errors": errors,
    }


def _write_record(record: dict) -> None:
    """Write a parsed Anki note record to the DB."""
    with db.get_connection() as conn:
        conn.execute("""
            INSERT INTO words
                (word, language_code, ipa, audio_file, image_file,
                 definitions, etymology, sentences, synonyms, pos,
                 source_url, deck_name, anki_note_id, scraped_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(word, language_code) DO UPDATE SET
                ipa          = excluded.ipa,
                audio_file   = excluded.audio_file,
                image_file   = excluded.image_file,
                definitions  = excluded.definitions,
                etymology    = excluded.etymology,
                sentences    = excluded.sentences,
                synonyms     = excluded.synonyms,
                pos          = excluded.pos,
                source_url   = excluded.source_url,
                deck_name    = excluded.deck_name,
                anki_note_id = excluded.anki_note_id,
                scraped_at   = excluded.scraped_at,
                status       = excluded.status
        """, (
            record["word"],
            record["language_code"],
            record["ipa"],
            record["audio_file"],
            record["image_file"],
            json.dumps(record["definitions"]),
            record["etymology"],
            json.dumps(record["sentences"]),
            json.dumps(record["synonyms"]),
            record["pos"],
            record["source_url"],
            record["deck_name"],
            record["anki_note_id"],
            record["scraped_at"],
            record["status"],
        ))
        conn.commit()
