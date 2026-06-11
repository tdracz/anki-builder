"""
Tests for backend/pipeline.py — scrape pipeline orchestration.
All external I/O (scraping, image fetch, audio download, AnkiConnect) is mocked.
"""

from unittest.mock import MagicMock, patch, call
import pytest

from backend import database as db
from backend.languages.base import WordData
from backend.pipeline import (
    _build_anki_fields,
    _check_anki_once,
    flush_pending_sync,
    process_word,
    process_words,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_word(word="serendipity", lang="en", status="pending_sync"):
    data = WordData(
        word=word,
        language_code=lang,
        ipa="(sĕr′ən-dĭp′ĭ-tē)",
        definitions=["A happy accident."],
        etymology="From Serendip.",
        sentences=["Pure serendipity."],
        pos="noun",
    )
    db.upsert_word(data, status=status)
    return data


# ---------------------------------------------------------------------------
# _build_anki_fields
# ---------------------------------------------------------------------------

class TestBuildAnkiFields:
    def test_basic_fields(self):
        _insert_word()
        db.set_audio_file("serendipity", "en", "en_serendipity.mp3")
        db.set_image_file("serendipity", "en", "serendipity.jpg")
        row = db.get_word("serendipity", "en")
        fields = _build_anki_fields(row)

        assert fields["Word"] == "serendipity"
        assert fields["Language"] == "en"
        assert fields["IPA"] == "(sĕr′ən-dĭp′ĭ-tē)"
        assert fields["Audio"] == "[sound:en_serendipity.mp3]"
        assert fields["Image"] == '<img src="serendipity.jpg">'
        assert "<li>A happy accident.</li>" in fields["Definitions"]
        assert "<li>Pure serendipity.</li>" in fields["Sentences"]
        assert "From Serendip." in fields["Etymology"]

    def test_empty_audio_and_image(self):
        _insert_word()
        row = db.get_word("serendipity", "en")
        fields = _build_anki_fields(row)
        assert fields["Audio"] == ""
        assert fields["Image"] == ""

    def test_empty_definitions_and_sentences(self):
        data = WordData(word="test", language_code="en")
        db.upsert_word(data)
        row = db.get_word("test", "en")
        fields = _build_anki_fields(row)
        assert fields["Definitions"] == ""
        assert fields["Sentences"] == ""


# ---------------------------------------------------------------------------
# _check_anki_once
# ---------------------------------------------------------------------------

class TestCheckAnkiOnce:
    def test_returns_false_when_anki_not_running(self):
        with patch("backend.pipeline.anki") as mock_anki:
            mock_anki.check_connection.return_value = {
                "connected": False, "version": None, "message": "Not running"
            }
            assert _check_anki_once() is False
            mock_anki.ensure_model.assert_not_called()

    def test_returns_true_when_anki_running(self):
        with patch("backend.pipeline.anki") as mock_anki:
            mock_anki.check_connection.return_value = {
                "connected": True, "version": 6, "message": "OK"
            }
            assert _check_anki_once() is True
            mock_anki.ensure_model.assert_called_once()

    def test_returns_false_when_model_bootstrap_fails(self):
        from backend.anki_connect import AnkiConnectError
        with patch("backend.pipeline.anki") as mock_anki:
            mock_anki.check_connection.return_value = {
                "connected": True, "version": 6, "message": "OK"
            }
            mock_anki.ensure_model.side_effect = AnkiConnectError("Model error")
            assert _check_anki_once() is False


# ---------------------------------------------------------------------------
# process_word / process_words
# ---------------------------------------------------------------------------

class TestProcessWord:
    def _mock_module(self, word="serendipity", lang="en"):
        """Return a mock LanguageModule that returns a minimal WordData."""
        mock_module = MagicMock()
        mock_module.language_code = lang
        mock_module.deck_name = "English Vocabulary"
        mock_module.fetch.return_value = WordData(
            word=word,
            language_code=lang,
            ipa="(sĕr′ən-dĭp′ĭ-tē)",
            definitions=["A happy accident."],
            etymology="From Serendip.",
            sentences=["Pure serendipity."],
            pos="noun",
            audio_url="https://example.com/audio.mp3",
            image_query=word,
        )
        mock_module.should_fetch_image.return_value = False
        return mock_module

    def test_word_saved_to_db_after_scrape(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="pending")

        with patch("backend.pipeline.get_module", return_value=self._mock_module()), \
             patch("backend.pipeline._check_anki_once", return_value=False), \
             patch("backend.pipeline._download_audio", return_value=None), \
             patch("backend.pipeline.fetch_image", return_value=None):
            process_word("serendipity", "en")

        row = db.get_word("serendipity", "en")
        assert row is not None
        assert row["ipa"] == "(sĕr′ən-dĭp′ĭ-tē)"
        assert row["definitions"] == ["A happy accident."]

    def test_status_is_pending_sync_when_anki_unavailable(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="pending")

        with patch("backend.pipeline.get_module", return_value=self._mock_module()), \
             patch("backend.pipeline._check_anki_once", return_value=False), \
             patch("backend.pipeline._download_audio", return_value=None), \
             patch("backend.pipeline.fetch_image", return_value=None):
            process_word("serendipity", "en")

        row = db.get_word("serendipity", "en")
        assert row["status"] == "pending_sync"

    def test_status_is_synced_when_anki_available(self):
        """When Anki is available and sync succeeds, the progress callback reports 'synced'."""
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="pending")
        events = []

        with patch("backend.pipeline.get_module", return_value=self._mock_module()), \
             patch("backend.pipeline._check_anki_once", return_value=True), \
             patch("backend.pipeline._download_audio", return_value=None), \
             patch("backend.pipeline.fetch_image", return_value=None), \
             patch("backend.pipeline.sync_word_to_anki", return_value=True):
            process_word("serendipity", "en", progress_cb=lambda w, s: events.append(s))

        assert "synced" in events

    def test_scrape_error_marks_word_as_error(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="pending")

        mock_module = self._mock_module()
        mock_module.fetch.side_effect = Exception("Network failure")

        with patch("backend.pipeline.get_module", return_value=mock_module), \
             patch("backend.pipeline._check_anki_once", return_value=False):
            process_word("serendipity", "en")

        row = db.get_word("serendipity", "en")
        assert row["status"] == "error"

    def test_progress_callback_called(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="pending")
        events = []

        with patch("backend.pipeline.get_module", return_value=self._mock_module()), \
             patch("backend.pipeline._check_anki_once", return_value=False), \
             patch("backend.pipeline._download_audio", return_value=None), \
             patch("backend.pipeline.fetch_image", return_value=None):
            process_word("serendipity", "en", progress_cb=lambda w, s: events.append((w, s)))

        assert ("serendipity", "scraping") in events
        assert ("serendipity", "scraped") in events

    def test_anki_checked_once_for_batch(self):
        """process_words must call _check_anki_once exactly once regardless of batch size."""
        for word in ["apple", "banana", "cherry"]:
            db.upsert_word(WordData(word=word, language_code="en"), status="pending")

        mock_module = self._mock_module()
        mock_module.fetch.side_effect = lambda w: WordData(
            word=w, language_code="en", definitions=["def"], ipa="ipa"
        )

        with patch("backend.pipeline.get_module", return_value=mock_module), \
             patch("backend.pipeline._check_anki_once", return_value=False) as mock_check, \
             patch("backend.pipeline._download_audio", return_value=None), \
             patch("backend.pipeline.fetch_image", return_value=None):
            process_words(["apple", "banana", "cherry"], "en")

        mock_check.assert_called_once()

    def test_one_bad_word_does_not_abort_batch(self):
        """A scrape failure on one word must not prevent other words from being processed."""
        for word in ["good1", "bad", "good2"]:
            db.upsert_word(WordData(word=word, language_code="en"), status="pending")

        def fake_fetch(word):
            if word == "bad":
                raise Exception("Scrape failed")
            return WordData(word=word, language_code="en", definitions=["def"], ipa="ipa")

        mock_module = MagicMock()
        mock_module.language_code = "en"
        mock_module.deck_name = "English Vocabulary"
        mock_module.fetch.side_effect = fake_fetch
        mock_module.should_fetch_image.return_value = False

        with patch("backend.pipeline.get_module", return_value=mock_module), \
             patch("backend.pipeline._check_anki_once", return_value=False), \
             patch("backend.pipeline._download_audio", return_value=None), \
             patch("backend.pipeline.fetch_image", return_value=None):
            process_words(["good1", "bad", "good2"], "en")

        assert db.get_word("good1", "en")["status"] == "pending_sync"
        assert db.get_word("bad", "en")["status"] == "error"
        assert db.get_word("good2", "en")["status"] == "pending_sync"


# ---------------------------------------------------------------------------
# flush_pending_sync
# ---------------------------------------------------------------------------

class TestFlushPendingSync:
    def test_returns_immediately_when_anki_unavailable(self):
        _insert_word("apple", status="pending_sync")
        _insert_word("banana", status="pending_sync")

        with patch("backend.pipeline._check_anki_once", return_value=False):
            result = flush_pending_sync("en")

        assert result["synced"] == 0
        assert result["failed"] == 2
        assert len(result["errors"]) == 1  # single message, not per-word

    def test_returns_empty_when_nothing_pending(self):
        with patch("backend.pipeline._check_anki_once", return_value=True):
            result = flush_pending_sync("en")

        assert result == {"synced": 0, "failed": 0, "errors": []}

    def test_syncs_all_pending_words(self):
        _insert_word("apple", status="pending_sync")
        _insert_word("banana", status="pending_sync")

        with patch("backend.pipeline._check_anki_once", return_value=True), \
             patch("backend.pipeline.sync_word_to_anki", return_value=True) as mock_sync:
            result = flush_pending_sync("en")

        assert result["synced"] == 2
        assert result["failed"] == 0
        assert mock_sync.call_count == 2

    def test_counts_failures_correctly(self):
        _insert_word("apple", status="pending_sync")
        _insert_word("banana", status="pending_sync")

        with patch("backend.pipeline._check_anki_once", return_value=True), \
             patch("backend.pipeline.sync_word_to_anki", side_effect=[True, False]):
            result = flush_pending_sync("en")

        assert result["synced"] == 1
        assert result["failed"] == 1
        assert "banana" in result["errors"]


# ---------------------------------------------------------------------------
# _render_definitions_html
# ---------------------------------------------------------------------------

from backend.pipeline import _render_definitions_html


class TestRenderDefinitionsHtml:
    def test_empty_returns_empty_string(self):
        assert _render_definitions_html([]) == ""

    def test_plain_definitions_no_pos(self):
        html = _render_definitions_html(["Sadness.", "Gloom."])
        assert "<li>Sadness.</li>" in html
        assert "<li>Gloom.</li>" in html
        assert "<ol>" in html

    def test_pos_groups_produce_headers(self):
        defs = ["__pos:noun__", "Sadness.", "__pos:adjective__", "Feeling sad."]
        html = _render_definitions_html(defs)
        assert "<em>noun</em>" in html
        assert "<em>adjective</em>" in html
        assert "<li>Sadness.</li>" in html
        assert "<li>Feeling sad.</li>" in html

    def test_multiple_pos_groups_separate_lists(self):
        defs = ["__pos:noun__", "Def1.", "Def2.", "__pos:verb__", "Def3."]
        html = _render_definitions_html(defs)
        # Should have two <ol> blocks
        assert html.count("<ol>") == 2

    def test_synonyms_in_anki_fields(self):
        _insert_word()
        row = db.get_word("serendipity", "en")
        # Inject synonyms
        import json
        import sqlite3
        import backend.database as db_mod
        with db_mod.get_connection() as conn:
            conn.execute(
                "UPDATE words SET synonyms=? WHERE word='serendipity'",
                (json.dumps(["luck", "fortune"]),)
            )
            conn.commit()
        row = db.get_word("serendipity", "en")
        fields = _build_anki_fields(row)
        assert "luck" in fields["Synonyms"]
        assert "fortune" in fields["Synonyms"]


# ---------------------------------------------------------------------------
# delete_word_from_anki
# ---------------------------------------------------------------------------

from backend.pipeline import delete_word_from_anki


class TestDeleteWordFromAnki:
    def test_queues_when_auto_sync_false(self):
        _insert_word("serendipity", status="synced")
        delete_word_from_anki("serendipity", "en", auto_sync=False)
        row = db.get_word("serendipity", "en")
        assert row is not None
        assert row["status"] == "pending_delete"

    def test_deletes_immediately_when_auto_sync_true(self):
        _insert_word("serendipity", status="synced")
        with patch("backend.pipeline.anki") as mock_anki:
            mock_anki.delete_notes = MagicMock()
            delete_word_from_anki("serendipity", "en", auto_sync=True)
        assert db.get_word("serendipity", "en") is None

    def test_calls_anki_delete_when_note_id_exists(self):
        _insert_word("serendipity", status="synced")
        db.set_anki_note_id("serendipity", "en", 42)
        with patch("backend.pipeline.anki") as mock_anki:
            mock_anki.delete_notes = MagicMock()
            delete_word_from_anki("serendipity", "en", auto_sync=True)
        mock_anki.delete_notes.assert_called_once_with([42])

    def test_no_anki_call_when_no_note_id(self):
        _insert_word("serendipity", status="pending_sync")  # never synced
        with patch("backend.pipeline.anki") as mock_anki:
            mock_anki.delete_notes = MagicMock()
            delete_word_from_anki("serendipity", "en", auto_sync=True)
        mock_anki.delete_notes.assert_not_called()


# ---------------------------------------------------------------------------
# flush_pending_sync — pending deletes
# ---------------------------------------------------------------------------

class TestFlushPendingDelete:
    def test_flushes_pending_deletes(self):
        _insert_word("apple", status="pending_delete")
        db.set_anki_note_id("apple", "en", 99)
        # Re-set to pending_delete since set_anki_note_id changes status
        db.set_status("apple", "en", "pending_delete")

        with patch("backend.pipeline._check_anki_once", return_value=True), \
             patch("backend.pipeline.anki") as mock_anki:
            mock_anki.delete_notes = MagicMock()
            result = flush_pending_sync("en")

        assert result["synced"] >= 1
        assert db.get_word("apple", "en") is None

    def test_pending_delete_counted_in_failed_when_anki_down(self):
        _insert_word("apple", status="pending_delete")
        _insert_word("banana", status="pending_sync")

        with patch("backend.pipeline._check_anki_once", return_value=False):
            result = flush_pending_sync("en")

        assert result["failed"] == 2  # both apple (delete) and banana (sync)
