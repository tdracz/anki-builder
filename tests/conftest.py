"""
Shared fixtures for all tests.
Uses a temporary SQLite DB and media dir so tests never touch the real user data.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Redirect database paths to a temp directory before any backend module loads
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Redirect DB_PATH and MEDIA_DIR to a temp directory for every test.
    This prevents tests from touching ~/.local/share/anki-builder/.
    """
    import backend.database as db_module

    test_db = tmp_path / "test_words.db"
    test_media = tmp_path / "media"
    test_media.mkdir()

    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    monkeypatch.setattr(db_module, "MEDIA_DIR", test_media)
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)

    db_module.init_db()
    yield test_db
