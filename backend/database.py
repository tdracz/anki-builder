"""
SQLite persistence layer.
All words are stored here regardless of whether Anki is running.
"""

import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .languages.base import WordData

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    """Return the platform-appropriate user data directory."""
    import sys
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home() / ".local" / "share"
    d = base / "anki-builder"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "words.db"
MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


from contextlib import contextmanager

@contextmanager
def _conn():
    """Open a connection, commit on success, always close."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS words (
                id            INTEGER PRIMARY KEY,
                word          TEXT NOT NULL,
                language_code TEXT NOT NULL DEFAULT 'en',
                ipa           TEXT,
                audio_file    TEXT,
                image_file    TEXT,
                definitions   TEXT,
                etymology     TEXT,
                sentences     TEXT,
                synonyms      TEXT,
                pos           TEXT,
                source_url    TEXT,
                deck_name     TEXT,
                anki_note_id  INTEGER,
                scraped_at    TEXT,
                status        TEXT NOT NULL DEFAULT 'pending',
                UNIQUE(word, language_code)
            )
        """)
        # Migrate older DBs
        for col, typedef in [
            ("source_url", "TEXT"),
            ("synonyms",   "TEXT"),
            ("deck_name",  "TEXT"),
            ("translation", "TEXT"),
            ("translation_language", "TEXT"),
            ("error_message", "TEXT"),
            ("antonyms", "TEXT"),
            ("thesaurus_url", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE words ADD COLUMN {col} {typedef}")
            except Exception:
                pass

        # Settings table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
    logger.info("Database ready at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def upsert_word(data: WordData, status: str = "done", deck_name: Optional[str] = None) -> None:
    """Insert or update a word record from scraped WordData.
    Existing audio_file and image_file are preserved on conflict (COALESCE).
    """
    with _conn() as conn:
        conn.execute("""
            INSERT INTO words
                (word, language_code, ipa, audio_file, image_file,
                 definitions, etymology, sentences, synonyms, antonyms, pos,
                 source_url, thesaurus_url, deck_name, scraped_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(word, language_code) DO UPDATE SET
                ipa          = excluded.ipa,
                audio_file   = COALESCE(audio_file, excluded.audio_file),
                image_file   = COALESCE(image_file, excluded.image_file),
                definitions  = excluded.definitions,
                etymology    = excluded.etymology,
                sentences    = excluded.sentences,
                synonyms     = excluded.synonyms,
                antonyms     = excluded.antonyms,
                pos          = excluded.pos,
                source_url   = excluded.source_url,
                thesaurus_url = excluded.thesaurus_url,
                deck_name    = COALESCE(excluded.deck_name, deck_name),
                scraped_at   = excluded.scraped_at,
                status       = excluded.status
        """, (
            data.word,
            data.language_code,
            data.ipa,
            None,
            None,
            json.dumps(data.definitions),
            data.etymology,
            json.dumps(data.sentences),
            json.dumps(data.synonyms),
            json.dumps(data.antonyms),
            data.pos,
            data.source_url,
            data.thesaurus_url,
            deck_name,
            datetime.now(timezone.utc).isoformat(),
            status,
        ))


def set_audio_file(word: str, language_code: str, filename: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET audio_file=? WHERE word=? AND language_code=?",
            (filename, word, language_code),
        )


def set_image_file(word: str, language_code: str, filename: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET image_file=? WHERE word=? AND language_code=?",
            (filename, word, language_code),
        )


def set_status(word: str, language_code: str, status: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET status=? WHERE word=? AND language_code=?",
            (status, word, language_code),
        )


def set_error(word: str, language_code: str, message: str) -> None:
    """Set status to 'error' and store the error message."""
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET status='error', error_message=? WHERE word=? AND language_code=?",
            (message, word, language_code),
        )


def set_anki_note_id(word: str, language_code: str, note_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET anki_note_id=?, status='synced' WHERE word=? AND language_code=?",
            (note_id, word, language_code),
        )


def set_deck_name(word: str, language_code: str, deck_name: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET deck_name=? WHERE word=? AND language_code=?",
            (deck_name, word, language_code),
        )


def clear_image(word: str, language_code: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET image_file=NULL, status='pending_sync' WHERE word=? AND language_code=?",
            (word, language_code),
        )


def delete_word(word: str, language_code: str) -> Optional[int]:
    """Delete a word from the DB. Returns the anki_note_id if it had one."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT anki_note_id FROM words WHERE word=? AND language_code=?",
            (word, language_code),
        ).fetchone()
        conn.execute(
            "DELETE FROM words WHERE word=? AND language_code=?",
            (word, language_code),
        )
    return row["anki_note_id"] if row else None


def queue_delete(word: str, language_code: str) -> None:
    """Mark a word as pending_delete instead of removing it immediately.
    The word stays visible in the UI with a 'Pending delete' badge until
    the next sync flushes it from Anki and the DB.
    """
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET status='pending_delete' WHERE word=? AND language_code=?",
            (word, language_code),
        )


def undelete_word(word: str, language_code: str) -> None:
    """Restore a pending_delete word back to its previous synced/pending_sync state."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT anki_note_id FROM words WHERE word=? AND language_code=? AND status='pending_delete'",
            (word, language_code),
        ).fetchone()
        if not row:
            return
        restore_status = "synced" if row["anki_note_id"] else "pending_sync"
        conn.execute(
            "UPDATE words SET status=? WHERE word=? AND language_code=?",
            (restore_status, word, language_code),
        )


def get_pending_deletes(language_code: Optional[str] = None) -> list[dict]:
    with _conn() as conn:
        if language_code:
            rows = conn.execute(
                "SELECT * FROM words WHERE status='pending_delete' AND language_code=?",
                (language_code,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM words WHERE status='pending_delete'"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_last_used_deck(language_code: str = "en") -> Optional[str]:
    """Return the deck_name most recently used for this language, or None."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT deck_name FROM words
               WHERE language_code=? AND deck_name IS NOT NULL
               ORDER BY scraped_at DESC LIMIT 1""",
            (language_code,),
        ).fetchone()
    return row["deck_name"] if row else None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_all_settings() -> dict[str, str]:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_translation(word: str, language_code: str, translation: str, translation_language: Optional[str] = None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET translation=?, translation_language=? WHERE word=? AND language_code=?",
            (translation, translation_language, word, language_code),
        )


def get_untranslated_words(language_code: str) -> list[dict]:
    """Return words that have been scraped but have no translation yet."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM words
               WHERE language_code=? AND translation IS NULL
               AND status NOT IN ('error', 'not_found', 'pending', 'pending_delete')""",
            (language_code,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def rename_word(word: str, language_code: str, new_word: str) -> None:
    """Rename a word, keeping all other data intact."""
    with _conn() as conn:
        conn.execute(
            "UPDATE words SET word=?, status='pending_sync' WHERE word=? AND language_code=?",
            (new_word, word, language_code),
        )


def update_fields(word: str, language_code: str, fields: dict) -> None:
    """Update arbitrary text fields (for manual edits from the UI)."""
    allowed = {"ipa", "definitions", "etymology", "sentences", "pos"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    # JSON-encode list fields
    for key in ("definitions", "sentences"):
        if key in updates and isinstance(updates[key], list):
            updates[key] = json.dumps(updates[key])
    cols = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [word, language_code]
    with _conn() as conn:
        conn.execute(
            f"UPDATE words SET {cols}, status='pending_sync' WHERE word=? AND language_code=?",
            values,
        )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def word_exists(word: str, language_code: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM words WHERE word=? AND language_code=?",
            (word, language_code),
        ).fetchone()
    return row is not None


def get_word(word: str, language_code: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM words WHERE word=? AND language_code=?",
            (word, language_code),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_all_words(language_code: Optional[str] = None) -> list[dict]:
    with _conn() as conn:
        if language_code:
            rows = conn.execute(
                "SELECT * FROM words WHERE language_code=? ORDER BY word",
                (language_code,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM words ORDER BY language_code, word"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_pending_sync(language_code: Optional[str] = None) -> list[dict]:
    with _conn() as conn:
        if language_code:
            rows = conn.execute(
                "SELECT * FROM words WHERE status IN ('done','pending_sync') AND language_code=?",
                (language_code,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM words WHERE status IN ('done','pending_sync')"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("definitions", "sentences", "synonyms", "antonyms"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse JSON for field '%s' on word '%s'", key, d.get("word"))
                d[key] = []
        else:
            d[key] = []
    return d
