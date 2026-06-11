"""
Tests for the FastAPI endpoints (backend/main.py).
Uses httpx.AsyncClient with the ASGI transport — no real server needed.
"""

import io
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

from backend.main import app
from backend import database as db
from backend.languages.base import WordData


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_connected(client):
    with patch("backend.main.anki") as mock_anki:
        mock_anki.check_connection.return_value = {
            "connected": True, "version": 6, "message": "OK"
        }
        resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["version"] == 6


@pytest.mark.asyncio
async def test_status_disconnected(client):
    with patch("backend.main.anki") as mock_anki:
        mock_anki.check_connection.return_value = {
            "connected": False, "version": None, "message": "Not running"
        }
        resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


# ---------------------------------------------------------------------------
# GET /api/languages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_languages(client):
    resp = await client.get("/api/languages")
    assert resp.status_code == 200
    langs = resp.json()
    assert isinstance(langs, list)
    assert any(l["code"] == "en" for l in langs)


# ---------------------------------------------------------------------------
# GET /api/words
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_words_empty(client):
    resp = await client.get("/api/words?lang=en")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_words_returns_inserted(client):
    db.upsert_word(WordData(
        word="serendipity", language_code="en",
        ipa="(sĕr′ən-dĭp′ĭ-tē)", definitions=["A happy accident."],
    ))
    resp = await client.get("/api/words?lang=en")
    assert resp.status_code == 200
    words = [w["word"] for w in resp.json()]
    assert "serendipity" in words


# ---------------------------------------------------------------------------
# GET /api/words/{lang}/{word}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_word_found(client):
    db.upsert_word(WordData(word="melancholy", language_code="en", ipa="(mĕl′ən-kŏl′ē)"))
    resp = await client.get("/api/words/en/melancholy")
    assert resp.status_code == 200
    assert resp.json()["word"] == "melancholy"


@pytest.mark.asyncio
async def test_get_word_not_found(client):
    resp = await client.get("/api/words/en/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/words/{lang}/{word}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_word(client):
    db.upsert_word(WordData(word="ephemeral", language_code="en", ipa="old_ipa"))

    with patch("backend.main.sync_word_to_anki", return_value=False):
        resp = await client.put(
            "/api/words/en/ephemeral",
            json={"ipa": "/ɪˈfem.ər.əl/"},
        )

    assert resp.status_code == 200
    assert resp.json()["ipa"] == "/ɪˈfem.ər.əl/"


@pytest.mark.asyncio
async def test_update_word_not_found(client):
    resp = await client.put("/api/words/en/ghost", json={"ipa": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/import
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_new_words(client):
    content = b"serendipity\nmelancholy\nephemeral\n"
    resp = await client.post(
        "/api/import",
        files={"file": ("words.txt", io.BytesIO(content), "text/plain")},
        data={"lang": "en"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["new"] == 3
    assert data["duplicates"] == 0
    assert set(data["words"]) == {"serendipity", "melancholy", "ephemeral"}


@pytest.mark.asyncio
async def test_import_detects_duplicates(client):
    db.upsert_word(WordData(word="serendipity", language_code="en"))

    content = b"serendipity\nmelancholy\n"
    resp = await client.post(
        "/api/import",
        files={"file": ("words.txt", io.BytesIO(content), "text/plain")},
        data={"lang": "en"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["new"] == 1
    assert data["duplicates"] == 1
    assert "serendipity" in data["duplicate_words"]
    assert "melancholy" in data["words"]


@pytest.mark.asyncio
async def test_import_lowercases_words(client):
    content = b"Serendipity\nMELANCHOLY\n"
    resp = await client.post(
        "/api/import",
        files={"file": ("words.txt", io.BytesIO(content), "text/plain")},
        data={"lang": "en"},
    )
    data = resp.json()
    assert "serendipity" in data["words"]
    assert "melancholy" in data["words"]


@pytest.mark.asyncio
async def test_import_skips_blank_lines(client):
    content = b"apple\n\n  \nbanana\n"
    resp = await client.post(
        "/api/import",
        files={"file": ("words.txt", io.BytesIO(content), "text/plain")},
        data={"lang": "en"},
    )
    assert resp.json()["total"] == 2


# ---------------------------------------------------------------------------
# POST /api/sync
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_returns_result(client):
    with patch("backend.main.flush_pending_sync", return_value={"synced": 3, "failed": 0, "errors": []}):
        resp = await client.post("/api/sync?lang=en")
    assert resp.status_code == 200
    assert resp.json()["synced"] == 3


# ---------------------------------------------------------------------------
# GET /api/media/{filename}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_media_not_found(client):
    resp = await client.get("/api/media/nonexistent.mp3")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_media_serves_file(client, tmp_path, monkeypatch):
    import backend.database as db_module
    test_file = db_module.MEDIA_DIR / "test.mp3"
    test_file.write_bytes(b"fake audio data")

    resp = await client.get("/api/media/test.mp3")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/words/{lang}/{word}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_word_queues_when_auto_sync_false(client):
    db.upsert_word(WordData(word="serendipity", language_code="en"))
    resp = await client.delete("/api/words/en/serendipity?auto_sync=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_delete"
    assert db.word_exists("serendipity", "en")  # still in DB


@pytest.mark.asyncio
async def test_delete_word_removes_immediately_when_auto_sync_true(client):
    db.upsert_word(WordData(word="serendipity", language_code="en"))
    with patch("backend.main.delete_word_from_anki") as mock_del:
        mock_del.return_value = None
        resp = await client.delete("/api/words/en/serendipity?auto_sync=true")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_word_not_found(client):
    resp = await client.delete("/api/words/en/ghost")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/words/{lang}/{word}/undelete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_undelete_word(client):
    db.upsert_word(WordData(word="serendipity", language_code="en"), status="pending_delete")
    resp = await client.post("/api/words/en/serendipity/undelete")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("synced", "pending_sync")


@pytest.mark.asyncio
async def test_undelete_word_not_found(client):
    resp = await client.post("/api/words/en/ghost/undelete")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/words/bulk-delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_delete_queues(client):
    for w in ["apple", "banana"]:
        db.upsert_word(WordData(word=w, language_code="en"))
    resp = await client.post("/api/words/bulk-delete", json={
        "lang": "en", "words": ["apple", "banana"], "auto_sync": False
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 2
    assert data["deleted"] == 0


@pytest.mark.asyncio
async def test_bulk_delete_skips_missing_words(client):
    db.upsert_word(WordData(word="apple", language_code="en"))
    resp = await client.post("/api/words/bulk-delete", json={
        "lang": "en", "words": ["apple", "nonexistent"], "auto_sync": False
    })
    assert resp.status_code == 200
    assert resp.json()["queued"] == 1


# ---------------------------------------------------------------------------
# POST /api/words/bulk-undelete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_undelete(client):
    for w in ["apple", "banana"]:
        db.upsert_word(WordData(word=w, language_code="en"), status="pending_delete")
    resp = await client.post("/api/words/bulk-undelete", json={
        "lang": "en", "words": ["apple", "banana"], "auto_sync": False
    })
    assert resp.status_code == 200
    assert resp.json()["restored"] == 2
    assert db.get_word("apple", "en")["status"] in ("synced", "pending_sync")


# ---------------------------------------------------------------------------
# DELETE /api/words/{lang}/{word}/image
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_image(client):
    db.upsert_word(WordData(word="serendipity", language_code="en"), status="synced")
    db.set_image_file("serendipity", "en", "img.jpg")
    with patch("backend.main.sync_word_to_anki", return_value=False):
        resp = await client.delete("/api/words/en/serendipity/image")
    assert resp.status_code == 200
    assert resp.json()["image_file"] is None
    assert resp.json()["status"] == "pending_sync"


# ---------------------------------------------------------------------------
# GET /api/decks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_decks_our_decks(client):
    with patch("backend.main.anki") as mock_anki:
        mock_anki.get_app_decks.return_value = ["English Vocabulary", "German"]
        resp = await client.get("/api/decks")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "English Vocabulary" in names
    assert all(d["is_app_deck"] for d in resp.json())


@pytest.mark.asyncio
async def test_list_decks_all(client):
    with patch("backend.main.anki") as mock_anki:
        mock_anki.get_app_decks.return_value = ["English Vocabulary"]
        mock_anki.get_all_decks.return_value = ["English Vocabulary", "Default", "German"]
        resp = await client.get("/api/decks?all=true")
    assert resp.status_code == 200
    data = resp.json()
    app_flags = {d["name"]: d["is_app_deck"] for d in data}
    assert app_flags["English Vocabulary"] is True
    assert app_flags["Default"] is False


@pytest.mark.asyncio
async def test_last_used_deck_none_when_empty(client):
    resp = await client.get("/api/decks/last-used?lang=en")
    assert resp.status_code == 200
    assert resp.json()["deck_name"] is None


@pytest.mark.asyncio
async def test_last_used_deck_returns_value(client):
    db.upsert_word(WordData(word="test", language_code="en"), deck_name="My Deck")
    resp = await client.get("/api/decks/last-used?lang=en")
    assert resp.status_code == 200
    assert resp.json()["deck_name"] == "My Deck"


# ---------------------------------------------------------------------------
# GET /api/import/anki/preview
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anki_import_preview(client):
    db.upsert_word(WordData(word="existing", language_code="en"))
    with patch("backend.anki_importer.preview_anki_import") as mock_preview:
        mock_preview.return_value = {
            "total": 3,
            "new": 2,
            "duplicates": [{"word": "existing", "language_code": "en",
                            "local_status": "synced", "local_anki_id": None, "anki_note_id": 1}],
            "note_ids": [1, 2, 3],
        }
        resp = await client.get("/api/import/anki/preview?deck=English+Vocabulary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["new"] == 2
    assert len(data["duplicates"]) == 1


# ---------------------------------------------------------------------------
# POST /api/import/anki
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anki_import_execute(client):
    with patch("backend.anki_importer.execute_anki_import") as mock_exec:
        mock_exec.return_value = {"imported": 5, "skipped": 1, "overwritten": 0, "errors": []}
        resp = await client.post("/api/import/anki", json={
            "deck_name": "English Vocabulary",
            "duplicate_action": "skip",
            "skip_words": [],
            "overwrite_words": [],
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 5
    assert data["skipped"] == 1
