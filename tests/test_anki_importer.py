"""
Tests for backend/anki_importer.py — round-trip parsing of Anki note fields.
All AnkiConnect calls are mocked; no real Anki connection needed.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend import database as db
from backend.languages.base import WordData
from backend.anki_importer import (
    _parse_definitions,
    _parse_sentences,
    _parse_synonyms,
    _parse_source_url,
    _parse_audio_filename,
    _parse_image_filename,
    _extract_pos_from_definitions,
    _note_to_record,
    preview_anki_import,
    execute_anki_import,
)


# ---------------------------------------------------------------------------
# Field parsers
# ---------------------------------------------------------------------------

class TestParseDefinitions:
    def test_structured_with_pos_headers(self):
        html = (
            '<p class="pos-header"><em>noun</em></p>'
            '<ol><li>Sadness.</li><li>Gloom.</li></ol>'
            '<p class="pos-header"><em>adjective</em></p>'
            '<ol><li>Feeling sad.</li></ol>'
        )
        result = _parse_definitions(html)
        assert result == ["__pos:noun__", "Sadness.", "Gloom.", "__pos:adjective__", "Feeling sad."]

    def test_fallback_plain_li_items(self):
        html = "<ol><li>A happy accident.</li><li>Good fortune.</li></ol>"
        result = _parse_definitions(html)
        assert result == ["A happy accident.", "Good fortune."]

    def test_fallback_plain_text(self):
        result = _parse_definitions("Sadness.\nGloom.")
        assert "Sadness." in result

    def test_empty_returns_empty_list(self):
        assert _parse_definitions("") == []
        assert _parse_definitions(None) == []  # type: ignore

    def test_single_pos_group(self):
        html = '<p class="pos-header"><em>verb</em></p><ol><li>To run.</li></ol>'
        result = _parse_definitions(html)
        assert result == ["__pos:verb__", "To run."]


class TestParseSentences:
    def test_ul_li_structure(self):
        html = "<ul><li>A letter with melancholy news.</li><li>He felt melancholy.</li></ul>"
        assert _parse_sentences(html) == ["A letter with melancholy news.", "He felt melancholy."]

    def test_empty(self):
        assert _parse_sentences("") == []

    def test_fallback_plain_text(self):
        result = _parse_sentences("Sentence one.\nSentence two.")
        assert len(result) >= 1


class TestParseSynonyms:
    def test_comma_separated(self):
        assert _parse_synonyms("gloom, sorrow, dejection") == ["gloom", "sorrow", "dejection"]

    def test_strips_whitespace(self):
        assert _parse_synonyms("  happy ,  joyful  ") == ["happy", "joyful"]

    def test_empty(self):
        assert _parse_synonyms("") == []

    def test_single_item(self):
        assert _parse_synonyms("sadness") == ["sadness"]


class TestParseSourceUrl:
    def test_extracts_href(self):
        html = '<a href="https://www.thefreedictionary.com/melancholy">link</a>'
        assert _parse_source_url(html) == "https://www.thefreedictionary.com/melancholy"

    def test_plain_url_fallback(self):
        assert _parse_source_url("https://example.com") == "https://example.com"

    def test_empty(self):
        assert _parse_source_url("") is None

    def test_non_url_text_returns_none(self):
        assert _parse_source_url("not a url") is None


class TestParseAudioFilename:
    def test_extracts_from_sound_tag(self):
        assert _parse_audio_filename("[sound:en_melancholy.mp3]") == "en_melancholy.mp3"

    def test_returns_none_when_no_tag(self):
        assert _parse_audio_filename("") is None
        assert _parse_audio_filename("no sound here") is None

    def test_handles_various_extensions(self):
        assert _parse_audio_filename("[sound:word.ogg]") == "word.ogg"


class TestParseImageFilename:
    def test_extracts_src(self):
        assert _parse_image_filename('<img src="melancholy_abc.jpg">') == "melancholy_abc.jpg"

    def test_returns_none_when_no_img(self):
        assert _parse_image_filename("") is None
        assert _parse_image_filename("no image here") is None


class TestExtractPosFromDefinitions:
    def test_extracts_first_pos(self):
        defs = ["__pos:noun__", "Sadness.", "__pos:adjective__", "Feeling sad."]
        assert _extract_pos_from_definitions(defs) == "noun"

    def test_returns_none_when_no_pos_markers(self):
        assert _extract_pos_from_definitions(["Sadness.", "Gloom."]) is None

    def test_returns_none_for_empty(self):
        assert _extract_pos_from_definitions([]) is None


# ---------------------------------------------------------------------------
# _note_to_record
# ---------------------------------------------------------------------------

class TestNoteToRecord:
    def _make_note(self, word="melancholy", lang="en", **field_overrides):
        fields = {
            "Word": {"value": word, "order": 0},
            "Language": {"value": lang, "order": 1},
            "IPA": {"value": "(mĕl′ən-kŏl′ē)", "order": 2},
            "Audio": {"value": "[sound:en_melancholy.mp3]", "order": 3},
            "Image": {"value": '<img src="melancholy_abc.jpg">', "order": 4},
            "Definitions": {"value": "<ol><li>Sadness.</li></ol>", "order": 5},
            "Synonyms": {"value": "gloom, sorrow", "order": 6},
            "Etymology": {"value": "[Middle English]", "order": 7},
            "Sentences": {"value": "<ul><li>A melancholy mood.</li></ul>", "order": 8},
            "Source": {"value": '<a href="https://tfd.com/melancholy">link</a>', "order": 9},
        }
        for k, v in field_overrides.items():
            fields[k] = {"value": v, "order": 0}
        return {"noteId": 12345, "fields": fields}

    def test_basic_fields_parsed(self):
        note = self._make_note()
        with patch("backend.anki_importer._retrieve_media", return_value=False):
            record = _note_to_record(note, "English Vocabulary")

        assert record["word"] == "melancholy"
        assert record["language_code"] == "en"
        assert record["ipa"] == "(mĕl′ən-kŏl′ē)"
        assert record["audio_file"] == "en_melancholy.mp3"
        assert record["image_file"] == "melancholy_abc.jpg"
        assert record["definitions"] == ["Sadness."]
        assert record["synonyms"] == ["gloom", "sorrow"]
        assert record["etymology"] == "[Middle English]"
        assert record["sentences"] == ["A melancholy mood."]
        assert record["source_url"] == "https://tfd.com/melancholy"
        assert record["anki_note_id"] == 12345
        assert record["status"] == "synced"
        assert record["deck_name"] == "English Vocabulary"

    def test_word_lowercased(self):
        note = self._make_note(word="Melancholy")
        with patch("backend.anki_importer._retrieve_media", return_value=False):
            record = _note_to_record(note, "English Vocabulary")
        assert record["word"] == "melancholy"

    def test_pos_derived_from_definitions(self):
        note = self._make_note()
        note["fields"]["Definitions"]["value"] = (
            '<p class="pos-header"><em>noun</em></p><ol><li>Sadness.</li></ol>'
        )
        with patch("backend.anki_importer._retrieve_media", return_value=False):
            record = _note_to_record(note, "English Vocabulary")
        assert record["pos"] == "noun"

    def test_media_retrieval_attempted(self):
        note = self._make_note()
        with patch("backend.anki_importer._retrieve_media") as mock_retrieve:
            mock_retrieve.return_value = True
            _note_to_record(note, "English Vocabulary")
        # Should have tried to retrieve both audio and image
        calls = [c[0][0] for c in mock_retrieve.call_args_list]
        assert "en_melancholy.mp3" in calls
        assert "melancholy_abc.jpg" in calls


# ---------------------------------------------------------------------------
# preview_anki_import
# ---------------------------------------------------------------------------

class TestPreviewAnkiImport:
    def _mock_notes(self):
        return [
            {
                "noteId": 1,
                "fields": {
                    "Word": {"value": "serendipity", "order": 0},
                    "Language": {"value": "en", "order": 1},
                },
            },
            {
                "noteId": 2,
                "fields": {
                    "Word": {"value": "melancholy", "order": 0},
                    "Language": {"value": "en", "order": 1},
                },
            },
        ]

    def test_all_new_when_db_empty(self):
        with patch("backend.anki_importer.anki") as mock_anki:
            mock_anki.invoke.side_effect = [
                [1, 2],           # findNotes
                self._mock_notes(),  # notesInfo
            ]
            result = preview_anki_import("English Vocabulary")

        assert result["total"] == 2
        assert result["new"] == 2
        assert result["duplicates"] == []

    def test_detects_existing_words_as_duplicates(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="synced")

        with patch("backend.anki_importer.anki") as mock_anki:
            mock_anki.invoke.side_effect = [
                [1, 2],
                self._mock_notes(),
            ]
            result = preview_anki_import("English Vocabulary")

        assert result["new"] == 1
        assert len(result["duplicates"]) == 1
        assert result["duplicates"][0]["word"] == "serendipity"

    def test_empty_deck_returns_zeros(self):
        with patch("backend.anki_importer.anki") as mock_anki:
            mock_anki.invoke.return_value = []  # findNotes returns empty
            result = preview_anki_import("Empty Deck")

        assert result["total"] == 0
        assert result["new"] == 0


# ---------------------------------------------------------------------------
# execute_anki_import
# ---------------------------------------------------------------------------

class TestExecuteAnkiImport:
    def _mock_notes(self, words=("serendipity", "melancholy")):
        return [
            {
                "noteId": i + 1,
                "fields": {
                    "Word": {"value": w, "order": 0},
                    "Language": {"value": "en", "order": 1},
                    "IPA": {"value": "", "order": 2},
                    "Audio": {"value": "", "order": 3},
                    "Image": {"value": "", "order": 4},
                    "Definitions": {"value": "<ol><li>A definition.</li></ol>", "order": 5},
                    "Synonyms": {"value": "", "order": 6},
                    "Etymology": {"value": "", "order": 7},
                    "Sentences": {"value": "", "order": 8},
                    "Source": {"value": "", "order": 9},
                },
            }
            for i, w in enumerate(words)
        ]

    def test_imports_new_words(self):
        with patch("backend.anki_importer.anki") as mock_anki, \
             patch("backend.anki_importer._retrieve_media", return_value=False):
            mock_anki.invoke.side_effect = [
                [1, 2],
                self._mock_notes(),
            ]
            result = execute_anki_import("English Vocabulary")

        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert db.word_exists("serendipity", "en")
        assert db.word_exists("melancholy", "en")
        assert db.get_word("serendipity", "en")["status"] == "synced"

    def test_skips_duplicates_by_default(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="synced")

        with patch("backend.anki_importer.anki") as mock_anki, \
             patch("backend.anki_importer._retrieve_media", return_value=False):
            mock_anki.invoke.side_effect = [
                [1, 2],
                self._mock_notes(),
            ]
            result = execute_anki_import("English Vocabulary", duplicate_action="skip")

        assert result["imported"] == 1
        assert result["skipped"] == 1

    def test_overwrites_duplicates_when_requested(self):
        db.upsert_word(WordData(word="serendipity", language_code="en", ipa="old_ipa"), status="synced")

        with patch("backend.anki_importer.anki") as mock_anki, \
             patch("backend.anki_importer._retrieve_media", return_value=False):
            mock_anki.invoke.side_effect = [
                [1, 2],
                self._mock_notes(),
            ]
            result = execute_anki_import("English Vocabulary", duplicate_action="overwrite")

        assert result["overwritten"] == 1
        assert result["imported"] == 1

    def test_per_word_skip_overrides_global_overwrite(self):
        db.upsert_word(WordData(word="serendipity", language_code="en"), status="synced")
        db.upsert_word(WordData(word="melancholy", language_code="en"), status="synced")

        with patch("backend.anki_importer.anki") as mock_anki, \
             patch("backend.anki_importer._retrieve_media", return_value=False):
            mock_anki.invoke.side_effect = [
                [1, 2],
                self._mock_notes(),
            ]
            result = execute_anki_import(
                "English Vocabulary",
                duplicate_action="overwrite",
                skip_words=["serendipity"],   # skip this one specifically
                overwrite_words=["melancholy"],
            )

        assert result["skipped"] == 1
        assert result["overwritten"] == 1

    def test_empty_deck_returns_zeros(self):
        with patch("backend.anki_importer.anki") as mock_anki:
            mock_anki.invoke.return_value = []
            result = execute_anki_import("Empty Deck")

        assert result == {"imported": 0, "skipped": 0, "overwritten": 0, "errors": []}
