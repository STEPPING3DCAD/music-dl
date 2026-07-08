"""Shared LibraryDB accessor for GUI API routes."""
from __future__ import annotations

import threading
from pathlib import Path

from tidal_dl.helper.library_db import LibraryDB
from tidal_dl.helper.path import path_config_base

_db: LibraryDB | None = None
_lock = threading.Lock()


def get_library_db() -> LibraryDB:
    global _db
    with _lock:
        if _db is None:
            db = LibraryDB(Path(path_config_base()) / "library.db")
            db.open()
            db.import_legacy_isrc_index(Path(path_config_base()) / "isrc_index.json")
            _db = db
        return _db