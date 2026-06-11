"""
FastAPI application entry point.
Run with: uvicorn backend.main:app --reload
Or via: python start.py
"""

import asyncio
import json
import logging
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from .anki_connect import client as anki, AnkiConnectError
from .languages import list_languages
from .languages.base import WordData
from .models import (
    AnkiStatus,
    AnkiImportPreview,
    AnkiImportRequest,
    AnkiImportResult,
    BulkWordsRequest,
    CreateDeckRequest,
    DeckInfo,
    ImportResult,
    LanguageInfo,
    SyncResult,
    WordResponse,
    WordUpdateRequest,
)
from .pipeline import (
    delete_word_from_anki,
    flush_pending_sync,
    process_words,
    request_cancel,
    rescrape_word,
    sync_word_to_anki,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    status = anki.check_connection()
    if status["connected"]:
        logger.info("AnkiConnect ready (version %s)", status["version"])
    else:
        logger.info("Anki not running — cards will queue until synced.")
    yield


app = FastAPI(title="Vocab Builder", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if _STATIC_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


# ---------------------------------------------------------------------------
# Status / languages
# ---------------------------------------------------------------------------

@app.get("/api/status", response_model=AnkiStatus)
def get_status():
    anki.invalidate_cache()
    return AnkiStatus(**anki.check_connection())


@app.get("/api/languages", response_model=list[LanguageInfo])
def get_languages():
    return list_languages()


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------

@app.get("/api/decks", response_model=list[DeckInfo])
def list_decks(all: bool = False):
    """
    Return decks from Anki.
    ?all=false (default): only app-owned decks (those with a VocabBuilderDeck sentinel note)
    ?all=true: all decks in Anki, marked with is_app_deck flag
    """
    try:
        if all:
            app_deck_names = set(anki.get_app_decks())
            all_names = anki.get_all_decks()
            return [DeckInfo(name=n, is_app_deck=(n in app_deck_names)) for n in all_names]
        else:
            app_decks = anki.get_app_decks()
            return [DeckInfo(name=n, is_app_deck=True) for n in app_decks]
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/decks/last-used")
def last_used_deck(lang: str = "en"):
    """Return the most recently used deck name for this language from the local DB."""
    name = db.get_last_used_deck(lang)
    return {"deck_name": name}


@app.post("/api/decks", response_model=DeckInfo)
def create_deck(body: CreateDeckRequest):
    """Create a new deck in Anki and register it as an app deck via sentinel note."""
    try:
        anki.ensure_model()
        anki.ensure_deck(body.name)
        anki.register_deck(body.name)
        return DeckInfo(name=body.name, is_app_deck=True)
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------

@app.get("/api/words", response_model=list[WordResponse])
def list_words(lang: Optional[str] = None):
    return db.get_all_words(lang)


@app.post("/api/words", response_model=WordResponse)
def add_word_manually(lang: str = "en", word: str = "", deck: str = ""):
    """Add a single word manually. Creates a pending entry ready for scraping."""
    word = word.strip().lower()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")
    if db.word_exists(word, lang):
        raise HTTPException(status_code=409, detail="Word already exists")
    db.upsert_word(WordData(word=word, language_code=lang), status="pending", deck_name=deck or None)
    return db.get_word(word, lang)


@app.get("/api/words/{lang}/{word}", response_model=WordResponse)
def get_word(lang: str, word: str):
    row = db.get_word(word, lang)
    if not row:
        raise HTTPException(status_code=404, detail="Word not found")
    return row


@app.put("/api/words/{lang}/{word}", response_model=WordResponse)
def update_word(lang: str, word: str, body: WordUpdateRequest, auto_sync: bool = False):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    db.update_fields(word, lang, body.model_dump(exclude_none=True))
    if auto_sync and anki.check_connection()["connected"]:
        sync_word_to_anki(word, lang)
    return db.get_word(word, lang)


@app.put("/api/words/{lang}/{word}/rename", response_model=WordResponse)
def rename_word(lang: str, word: str, new_word: str = ""):
    """Rename a word. Transfers all data to the new word name."""
    new_word = new_word.strip().lower()
    if not new_word:
        raise HTTPException(status_code=400, detail="New word cannot be empty")
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    if db.word_exists(new_word, lang):
        raise HTTPException(status_code=409, detail="Target word already exists")
    db.rename_word(word, lang, new_word)
    return db.get_word(new_word, lang)


@app.delete("/api/words/{lang}/{word}")
def delete_word(lang: str, word: str, auto_sync: bool = False):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    delete_word_from_anki(word, lang, auto_sync=auto_sync)
    if auto_sync:
        # Word is gone from DB — return 204
        from fastapi.responses import Response
        return Response(status_code=204)
    # Word is queued for delete — return updated row so UI can show the badge
    return db.get_word(word, lang)


@app.post("/api/words/bulk-delete")
def bulk_delete(body: BulkWordsRequest):
    deleted = 0
    queued = 0
    for word in body.words:
        if not db.word_exists(word, body.lang):
            continue
        delete_word_from_anki(word, body.lang, auto_sync=body.auto_sync)
        if body.auto_sync:
            deleted += 1
        else:
            queued += 1
    return {"deleted": deleted, "queued": queued}


@app.post("/api/words/bulk-undelete")
def bulk_undelete(body: BulkWordsRequest):
    restored = 0
    for word in body.words:
        db.undelete_word(word, body.lang)
        restored += 1
    return {"restored": restored}


@app.post("/api/words/bulk-sync")
def bulk_sync_words(body: BulkWordsRequest):
    """Sync specific words to Anki immediately. Uses the deck from the request if provided."""
    if not anki.check_connection()["connected"]:
        raise HTTPException(status_code=503, detail="Anki is not running")
    try:
        anki.ensure_model()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Model bootstrap failed: {exc}")

    # If a deck is specified in the request, update each word's deck_name first
    deck = getattr(body, 'deck', None) or None

    synced = 0
    failed = 0
    errors: list[str] = []
    for word in body.words:
        if db.word_exists(word, body.lang):
            if deck:
                db.set_deck_name(word, body.lang, deck)
            ok = sync_word_to_anki(word, body.lang)
            if ok:
                synced += 1
            else:
                failed += 1
                errors.append(word)
    return {"synced": synced, "failed": failed, "errors": errors}


@app.post("/api/words/bulk-rescrape")
async def bulk_rescrape(body: BulkWordsRequest):
    """Re-scrape multiple words."""
    loop = asyncio.get_running_loop()
    results = {"rescraping": len(body.words)}
    def _do():
        for word in body.words:
            if db.word_exists(word, body.lang):
                rescrape_word(word, body.lang)
    await loop.run_in_executor(None, _do)
    return results


@app.post("/api/words/bulk-translate")
async def bulk_translate_words(body: BulkWordsRequest):
    """Translate specific words (not all untranslated)."""
    from .translator import translate_word as _translate_one
    target_language = db.get_setting("translation_target_language")
    if not target_language or target_language.lower() == "none":
        raise HTTPException(status_code=400, detail="No target language configured")
    from .languages import get_module
    module = get_module(body.lang)
    source_language = module.language_name

    loop = asyncio.get_running_loop()
    translated = 0
    failed = 0

    def _do():
        nonlocal translated, failed
        for word in body.words:
            result = _translate_one(word, target_language, source_language)
            if result:
                db.set_translation(word, body.lang, result, target_language)
                db.set_status(word, body.lang, "pending_sync")
                translated += 1
            else:
                failed += 1

    await loop.run_in_executor(None, _do)
    return {"translated": translated, "failed": failed}


@app.post("/api/words/{lang}/{word}/translate")
async def translate_single_word(lang: str, word: str):
    """Translate a single word."""
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    target_language = db.get_setting("translation_target_language")
    if not target_language or target_language.lower() == "none":
        raise HTTPException(status_code=400, detail="No target language configured")
    from .translator import translate_word as _translate_one
    from .languages import get_module
    module = get_module(lang)
    source_language = module.language_name

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _translate_one, word, target_language, source_language)
    if result:
        db.set_translation(word, lang, result, target_language)
        db.set_status(word, lang, "pending_sync")
        return db.get_word(word, lang)
    raise HTTPException(status_code=500, detail="Translation failed")


@app.post("/api/words/{lang}/{word}/undelete", response_model=WordResponse)
def undelete_word(lang: str, word: str):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    db.undelete_word(word, lang)
    return db.get_word(word, lang)


@app.post("/api/words/{lang}/{word}/rescrape", response_model=WordResponse)
async def rescrape(lang: str, word: str, auto_sync: bool = False, deck: Optional[str] = None):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, rescrape_word, word, lang, deck)
    # rescrape_word leaves status as pending_sync; push immediately if auto_sync
    if auto_sync and anki.check_connection()["connected"]:
        sync_word_to_anki(word, lang)
        result = db.get_word(word, lang) or result
    return result


@app.put("/api/words/{lang}/{word}/deck", response_model=WordResponse)
def set_word_deck(lang: str, word: str, body: CreateDeckRequest, auto_sync: bool = False):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    db.set_deck_name(word, lang, body.name)
    db.set_status(word, lang, "pending_sync")
    if auto_sync and anki.check_connection()["connected"]:
        sync_word_to_anki(word, lang)
    return db.get_word(word, lang)


# ---------------------------------------------------------------------------
# Image management
# ---------------------------------------------------------------------------

@app.delete("/api/words/{lang}/{word}/image", response_model=WordResponse)
def remove_image(lang: str, word: str, auto_sync: bool = False):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    db.clear_image(word, lang)
    if auto_sync and anki.check_connection()["connected"]:
        sync_word_to_anki(word, lang)
    return db.get_word(word, lang)


@app.post("/api/words/{lang}/{word}/image", response_model=WordResponse)
async def replace_image(lang: str, word: str, file: UploadFile = File(...), auto_sync: bool = False):
    if not db.word_exists(word, lang):
        raise HTTPException(status_code=404, detail="Word not found")
    content = await file.read()
    content_type = file.content_type or "image/jpeg"
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    ext = ext_map.get(content_type, ".jpg")
    filename = f"{lang}_{word.replace(' ', '_')}_custom{ext}"
    dest = db.MEDIA_DIR / filename
    dest.write_bytes(content)
    db.set_image_file(word, lang, filename)
    db.set_status(word, lang, "pending_sync")
    if auto_sync and anki.check_connection()["connected"]:
        sync_word_to_anki(word, lang)
    return db.get_word(word, lang)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@app.post("/api/import", response_model=ImportResult)
async def import_words(
    file: UploadFile = File(...),
    lang: str = Form(default="en"),
    deck: str = Form(default=""),
):
    content = await file.read()
    lines = content.decode("utf-8", errors="ignore").splitlines()
    words = [w.strip().lower() for w in lines if w.strip()]

    new_words: list[str] = []
    duplicate_words: list[str] = []
    for word in words:
        if db.word_exists(word, lang):
            duplicate_words.append(word)
        else:
            db.upsert_word(
                WordData(word=word, language_code=lang),
                status="pending",
                deck_name=deck or None,
            )
            new_words.append(word)

    return ImportResult(
        total=len(words),
        new=len(new_words),
        duplicates=len(duplicate_words),
        words=new_words,
        duplicate_words=duplicate_words,
    )


@app.post("/api/import/cancel")
def cancel_import():
    """Signal any in-progress import (file or Anki) to stop after the current word."""
    request_cancel()
    return {"cancelled": True}


@app.get("/api/import/anki/preview")
def anki_import_preview(deck: str):
    """Scan an Anki deck and return new/duplicate counts without writing anything."""
    from .anki_importer import preview_anki_import
    try:
        result = preview_anki_import(deck)
        return AnkiImportPreview(
            total=result["total"],
            new=result["new"],
            duplicates=result["duplicates"],
        )
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/import/anki", response_model=AnkiImportResult)
async def anki_import_execute(body: AnkiImportRequest):
    """Import VocabBuilder notes from an Anki deck into the local DB."""
    from .anki_importer import execute_anki_import
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        execute_anki_import,
        body.deck_name,
        body.duplicate_action,
        body.skip_words,
        body.overwrite_words,
    )
    return AnkiImportResult(**result)


@app.get("/api/import/stream")
async def import_stream(words: str, lang: str = "en", deck: str = "", auto_sync: bool = False, fetch_images: bool = False, rescrape: bool = False):
    word_list = [w.strip() for w in words.split(",") if w.strip()]

    async def event_generator():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

        def cb(w: str, status: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"word": w, "status": status})

        def _scrape_batch() -> None:
            try:
                # If rescraping, reset each word to pending first
                if rescrape:
                    for w in word_list:
                        if db.word_exists(w, lang):
                            db.set_status(w, lang, "pending")

                process_words(word_list, lang, progress_cb=cb, auto_sync=auto_sync, fetch_images=fetch_images)
                # Auto-translate if target language is configured
                target_lang = db.get_setting("translation_target_language")
                if target_lang and target_lang.lower() != "none" and db.get_setting("openai_api_key"):
                    from .translator import translate_batch
                    translate_batch(lang, progress_cb=cb)
            except Exception as exc:
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"word": "", "status": "error", "message": str(exc)}
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)
        asyncio.get_running_loop().run_in_executor(None, _scrape_batch)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        yield 'data: {"status": "done"}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    return db.get_all_settings()


@app.get("/api/settings/models")
def get_openai_models():
    """Fetch available models from the configured OpenAI API."""
    api_key = db.get_setting("openai_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not configured")
    try:
        from openai import OpenAI
        base_url = db.get_setting("openai_base_url")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        models = client.models.list()
        names = sorted([m.id for m in models.data])
        return {"models": names}
    except ImportError:
        raise HTTPException(status_code=500, detail="openai package not installed")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.put("/api/settings")
def update_settings(body: dict):
    for key, value in body.items():
        db.set_setting(key, str(value))
    return db.get_all_settings()


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

@app.post("/api/translate")
async def translate_words(lang: str = "en"):
    """Translate all untranslated words for a language using OpenAI."""
    from .translator import translate_batch
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, translate_batch, lang)
    return result


@app.get("/api/translate/stream")
async def translate_stream(words: str, lang: str = "en"):
    """SSE stream that translates specific words one by one with progress."""
    word_list = [w.strip() for w in words.split(",") if w.strip()]

    async def event_generator():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

        def cb(w: str, status: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"word": w, "status": status})

        def _translate_batch() -> None:
            from .translator import translate_word as _translate_one
            from .pipeline import clear_cancel, is_cancelled
            clear_cancel()

            target_language = db.get_setting("translation_target_language")
            if not target_language or target_language.lower() == "none":
                loop.call_soon_threadsafe(queue.put_nowait, {"word": "", "status": "error", "message": "No target language configured"})
                return

            from .languages import get_module
            module = get_module(lang)
            source_language = module.language_name

            for word in word_list:
                if is_cancelled():
                    cb("", "cancelled")
                    break
                cb(word, "translating")
                result = _translate_one(word, target_language, source_language)
                if result:
                    db.set_translation(word, lang, result, target_language)
                    db.set_status(word, lang, "pending_sync")
                    cb(word, "translated")
                else:
                    cb(word, "translation_failed")

        def _run():
            try:
                _translate_batch()
            except Exception as exc:
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"word": "", "status": "error", "message": str(exc)}
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.get_running_loop().run_in_executor(None, _run)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        yield 'data: {"status": "done"}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/api/export")
def export_words(lang: str = "en"):
    """Export all words for a language as a plain text file, one word per line."""
    rows = db.get_all_words(lang)
    content = "\n".join(r["word"] for r in rows) + "\n" if rows else ""
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{lang}_words.txt"'},
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

@app.post("/api/sync", response_model=SyncResult)
async def sync_to_anki(lang: Optional[str] = None):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, flush_pending_sync, lang)
    return SyncResult(**result)


@app.get("/api/sync/stream")
async def sync_stream(lang: str = "en"):
    """SSE stream that syncs all pending words one by one with per-word progress."""
    async def event_generator():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

        def _run() -> None:
            from .pipeline import _check_anki_once, sync_word_to_anki, is_cancelled, clear_cancel
            clear_cancel()

            pending_sync = db.get_pending_sync(lang)
            pending_delete = db.get_pending_deletes(lang)

            if not pending_sync and not pending_delete:
                loop.call_soon_threadsafe(queue.put_nowait, {"word": "", "status": "nothing_to_sync"})
                return

            if not _check_anki_once():
                loop.call_soon_threadsafe(queue.put_nowait, {"word": "", "status": "error", "message": "Anki is not running"})
                return

            # Sync updates
            for row in pending_sync:
                if is_cancelled():
                    loop.call_soon_threadsafe(queue.put_nowait, {"word": "", "status": "cancelled"})
                    break
                word = row["word"]
                loop.call_soon_threadsafe(queue.put_nowait, {"word": word, "status": "syncing"})
                ok = sync_word_to_anki(word, lang)
                loop.call_soon_threadsafe(queue.put_nowait, {"word": word, "status": "synced" if ok else "sync_failed"})

            # Process deletes
            for row in pending_delete:
                if is_cancelled():
                    break
                word = row["word"]
                loop.call_soon_threadsafe(queue.put_nowait, {"word": word, "status": "syncing"})
                try:
                    note_id = db.delete_word(word, lang)
                    if note_id:
                        from .anki_connect import client as anki_client
                        anki_client.delete_notes([note_id])
                    loop.call_soon_threadsafe(queue.put_nowait, {"word": word, "status": "deleted"})
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, {"word": word, "status": "sync_failed", "message": str(exc)})

        def _wrap():
            try:
                _run()
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {"word": "", "status": "error", "message": str(exc)})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.get_running_loop().run_in_executor(None, _wrap)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        yield 'data: {"status": "done"}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

@app.get("/api/media/{filename}")
def serve_media(filename: str):
    path = db.MEDIA_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(str(path))


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import threading
    import time
    import uvicorn

    def _open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000/app")

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
