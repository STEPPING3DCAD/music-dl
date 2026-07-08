"""Post-download library registration."""

from __future__ import annotations

import pathlib

from tidal_dl.helper.library_db import LibraryDB
from tidal_dl.helper.path import path_config_base


def register_downloaded_track(file_path: pathlib.Path | str) -> None:
    """Register a newly downloaded track in the library DB."""
    try:
        from tidal_dl.gui.api.library import _read_metadata

        fp = pathlib.Path(file_path) if not isinstance(file_path, pathlib.Path) else file_path
        if not fp.is_file():
            return

        meta = _read_metadata(fp)
        if not meta:
            return

        db = LibraryDB(pathlib.Path(path_config_base()) / "library.db")
        db.open()
        try:
            db.record(
                str(fp),
                status="tagged" if meta["isrc"] else "needs_isrc",
                isrc=meta["isrc"] or None,
                artist=meta["artist"],
                title=meta["name"],
                album=meta["album"],
                duration=meta["duration"],
                genre=meta.get("genre"),
                quality=meta["quality"],
                fmt=meta["format"],
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        pass