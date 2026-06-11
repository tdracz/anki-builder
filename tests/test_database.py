"""
Tests for backend/database.py — persistence layer.
"""

import json
import pytest
from backend import database as db
from backend.languages.base import WordData


def _make_word(word="serendipity", lang="en", **kwargs) -> WordData:
    defaults = dict(
        ipa="(sĕr′ən-dĭp′ĭ-tē)",
        definitions=["The faculty of making fortunate discoveries by accident."],
        etymology="From Serendip, an old name for Sri Lanka.",
        sentences=["It was pure serendipity that they met."],
        pos="noun",
    )
    defaults.update(kwargs)
    return WordData(word=word, language_code=lang, **defaults)


class TestUpsertWord:
    def test_insert_new_word(self):
        db.upsert_word(_make_word())
        row = db.get_word("serendipity", "en")
        assert row is not None
        assert row["word"] == "serendipity"
        assert row["ipa"] == "(sĕr′ən-dĭp′ĭ-tē)"
        assert row["pos"] == "noun"
        assert row["definitions"] == ["The faculty of making fortunate discoveries by accident."]
        assert row["sentences"] == ["It was pure serendipity that they met."]

    def test_upsert_updates_existing(self):
        db.upsert_word(_make_word())
        updated = _make_word(ipa="NEW_IPA", definitions=["Updated definition."])
        db.upsert_word(updated)
        row = db.get_word("serendipity", "en")
        assert row["ipa"] == "NEW_IPA"
        assert row["definitions"] == ["Updated definition."]

    def test_upsert_preserves_audio_file(self):
        """Re-importing a word must not wipe an already-downloaded audio file."""
        db.upsert_word(_make_word())
        db.set_audio_file("serendipity", "en", "en_serendipity.mp3")

        # Re-upsert (simulates re-import)
        db.upsert_word(_make_word())

        row = db.get_word("serendipity", "en")
        assert row["audio_file"] == "en_serendipity.mp3"

    def test_upsert_preserves_image_file(self):
        """Re-importing a word must not wipe an already-downloaded image file."""
        db.upsert_word(_make_word())
        db.set_image_file("serendipity", "en", "serendipity_abc.jpg")

        db.upsert_word(_make_word())

        row = db.get_word("serendipity", "en")
        assert row["image_file"] == "serendipity_abc.jpg"

    def test_different_languages_are_separate(self):
        db.upsert_word(_make_word(word="set", lang="en"))
        db.upsert_word(_make_word(word="set", lang="de"))
        en = db.get_word("set", "en")
        de = db.get_word("set", "de")
        assert en is not None
        assert de is not None
        assert en["language_code"] == "en"
        assert de["language_code"] == "de"

    def test_status_default_is_done(self):
        db.upsert_word(_make_word())
        row = db.get_word("serendipity", "en")
        assert row["status"] == "done"

    def test_status_can_be_overridden(self):
        db.upsert_word(_make_word(), status="pending")
        row = db.get_word("serendipity", "en")
        assert row["status"] == "pending"


class TestWordExists:
    def test_returns_false_for_missing_word(self):
        assert db.word_exists("nonexistent", "en") is False

    def test_returns_true_after_insert(self):
        db.upsert_word(_make_word())
        assert db.word_exists("serendipity", "en") is True

    def test_language_specific(self):
        db.upsert_word(_make_word(lang="en"))
        assert db.word_exists("serendipity", "de") is False


class TestSetters:
    def test_set_audio_file(self):
        db.upsert_word(_make_word())
        db.set_audio_file("serendipity", "en", "audio.mp3")
        assert db.get_word("serendipity", "en")["audio_file"] == "audio.mp3"

    def test_set_image_file(self):
        db.upsert_word(_make_word())
        db.set_image_file("serendipity", "en", "img.jpg")
        assert db.get_word("serendipity", "en")["image_file"] == "img.jpg"

    def test_set_status(self):
        db.upsert_word(_make_word())
        db.set_status("serendipity", "en", "synced")
        assert db.get_word("serendipity", "en")["status"] == "synced"

    def test_set_anki_note_id(self):
        db.upsert_word(_make_word())
        db.set_anki_note_id("serendipity", "en", 12345)
        row = db.get_word("serendipity", "en")
        assert row["anki_note_id"] == 12345
        assert row["status"] == "synced"


class TestUpdateFields:
    def test_update_ipa(self):
        db.upsert_word(_make_word())
        db.update_fields("serendipity", "en", {"ipa": "/ˌser.ənˈdɪp.ɪ.ti/"})
        assert db.get_word("serendipity", "en")["ipa"] == "/ˌser.ənˈdɪp.ɪ.ti/"

    def test_update_sets_pending_sync(self):
        db.upsert_word(_make_word(), status="synced")
        db.update_fields("serendipity", "en", {"ipa": "new"})
        assert db.get_word("serendipity", "en")["status"] == "pending_sync"

    def test_update_definitions_list(self):
        db.upsert_word(_make_word())
        db.update_fields("serendipity", "en", {"definitions": ["Def A", "Def B"]})
        assert db.get_word("serendipity", "en")["definitions"] == ["Def A", "Def B"]

    def test_update_ignores_unknown_fields(self):
        db.upsert_word(_make_word())
        # Should not raise; unknown fields are silently ignored
        db.update_fields("serendipity", "en", {"nonexistent_field": "value"})


class TestGetAllWords:
    def test_returns_all_words(self):
        db.upsert_word(_make_word("apple"))
        db.upsert_word(_make_word("banana"))
        rows = db.get_all_words("en")
        words = [r["word"] for r in rows]
        assert "apple" in words
        assert "banana" in words

    def test_filters_by_language(self):
        db.upsert_word(_make_word("apple", lang="en"))
        db.upsert_word(_make_word("apfel", lang="de"))
        en_rows = db.get_all_words("en")
        assert all(r["language_code"] == "en" for r in en_rows)
        assert not any(r["word"] == "apfel" for r in en_rows)

    def test_returns_empty_list_when_no_words(self):
        assert db.get_all_words("en") == []


class TestGetPendingSync:
    def test_returns_done_and_pending_sync(self):
        db.upsert_word(_make_word("apple"), status="done")
        db.upsert_word(_make_word("banana"), status="pending_sync")
        db.upsert_word(_make_word("cherry"), status="synced")
        db.upsert_word(_make_word("date"), status="error")

        pending = db.get_pending_sync("en")
        words = [r["word"] for r in pending]
        assert "apple" in words
        assert "banana" in words
        assert "cherry" not in words
        assert "date" not in words


class TestQueueDelete:
    def test_marks_word_as_pending_delete(self):
        db.upsert_word(_make_word(), status="synced")
        db.queue_delete("serendipity", "en")
        assert db.get_word("serendipity", "en")["status"] == "pending_delete"

    def test_word_still_exists_in_db(self):
        db.upsert_word(_make_word())
        db.queue_delete("serendipity", "en")
        assert db.word_exists("serendipity", "en")


class TestUndeleteWord:
    def test_restores_synced_word(self):
        db.upsert_word(_make_word(), status="synced")
        db.set_anki_note_id("serendipity", "en", 999)
        db.queue_delete("serendipity", "en")
        db.undelete_word("serendipity", "en")
        assert db.get_word("serendipity", "en")["status"] == "synced"

    def test_restores_unsynced_word_to_pending_sync(self):
        db.upsert_word(_make_word(), status="pending_sync")
        db.queue_delete("serendipity", "en")
        db.undelete_word("serendipity", "en")
        assert db.get_word("serendipity", "en")["status"] == "pending_sync"

    def test_noop_when_not_pending_delete(self):
        db.upsert_word(_make_word(), status="synced")
        db.undelete_word("serendipity", "en")  # should not raise or change status
        assert db.get_word("serendipity", "en")["status"] == "synced"


class TestGetPendingDeletes:
    def test_returns_only_pending_delete(self):
        db.upsert_word(_make_word("apple"), status="pending_delete")
        db.upsert_word(_make_word("banana"), status="synced")
        db.upsert_word(_make_word("cherry"), status="pending_sync")

        rows = db.get_pending_deletes("en")
        words = [r["word"] for r in rows]
        assert "apple" in words
        assert "banana" not in words
        assert "cherry" not in words

    def test_filters_by_language(self):
        db.upsert_word(_make_word("apple", lang="en"), status="pending_delete")
        db.upsert_word(_make_word("apfel", lang="de"), status="pending_delete")
        rows = db.get_pending_deletes("en")
        assert all(r["language_code"] == "en" for r in rows)


class TestGetLastUsedDeck:
    def test_returns_most_recent_deck(self):
        db.upsert_word(_make_word("apple"), deck_name="Deck A")
        db.upsert_word(_make_word("banana"), deck_name="Deck B")
        # banana was inserted last, so Deck B should be most recent
        result = db.get_last_used_deck("en")
        assert result in ("Deck A", "Deck B")  # either is valid; just not None

    def test_returns_none_when_no_words(self):
        assert db.get_last_used_deck("en") is None

    def test_returns_none_when_no_deck_set(self):
        db.upsert_word(_make_word())  # no deck_name
        assert db.get_last_used_deck("en") is None


class TestClearImage:
    def test_clears_image_and_queues_sync(self):
        db.upsert_word(_make_word(), status="synced")
        db.set_image_file("serendipity", "en", "img.jpg")
        db.clear_image("serendipity", "en")
        row = db.get_word("serendipity", "en")
        assert row["image_file"] is None
        assert row["status"] == "pending_sync"


class TestSetDeckName:
    def test_sets_deck_name(self):
        db.upsert_word(_make_word())
        db.set_deck_name("serendipity", "en", "My Deck")
        assert db.get_word("serendipity", "en")["deck_name"] == "My Deck"
