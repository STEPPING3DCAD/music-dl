"""Regression tests for thread-safe GUI DB access."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import tidal_dl.gui.api.home as home_api
import tidal_dl.gui.api.library as library_api
import tidal_dl.gui.services.db as shared_db_service
from tidal_dl.gui.api.search import _serialize_track
from tidal_dl.helper.library_db import LibraryDB


def _seed_library_db(base_dir: Path) -> None:
    db = LibraryDB(base_dir / "library.db")
    db.open()
    db.record(
        "/music/artist/album/track.flac",
        status="tagged",
        artist="Artist",
        album="Album",
        title="Track",
    )
    db.record_download(
        track_id=1,
        name="Track",
        artist="Artist",
        album="Album",
        status="done",
        finished_at=100.0,
    )
    db.commit()
    db.close()


def _reset_db_cache(module) -> None:
    invalidate = getattr(module, "_invalidate_db_cache", None)
    if callable(invalidate):
        invalidate()
        return

    if hasattr(module, "_db"):
        db = getattr(module, "_db")
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        module._db = None
    if hasattr(module, "_db_opened_at"):
        module._db_opened_at = 0


def _concurrent_get_db_error(module, query, attempts: int = 12):
    for _ in range(attempts):
        _reset_db_cache(module)
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                getter = getattr(module, "_get_db", None) or module.get_library_db
                db = getter()
                query(db)
            except BaseException as exc:  # pragma: no cover - failure path only
                errors.append(exc)

        left = threading.Thread(target=worker)
        right = threading.Thread(target=worker)
        left.start()
        right.start()
        left.join()
        right.join()

        if errors:
            return errors[0]

    return None


def test_library_api_get_db_is_thread_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(library_api, "path_config_base", lambda: str(tmp_path))
    _seed_library_db(tmp_path)

    error = _concurrent_get_db_error(
        library_api,
        lambda db: db.recent_albums_page(limit=1, offset=0),
    )

    assert error is None, repr(error)


def test_home_api_get_db_is_thread_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(home_api, "path_config_base", lambda: str(tmp_path))
    _seed_library_db(tmp_path)

    error = _concurrent_get_db_error(home_api, lambda db: db.all_tracks())

    assert error is None, repr(error)


def test_shared_gui_db_service_is_thread_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_db_service, "path_config_base", lambda: str(tmp_path))
    _seed_library_db(tmp_path)

    error = _concurrent_get_db_error(
        shared_db_service,
        lambda db: db.has_live_isrc("ISRC123"),
    )

    assert error is None, repr(error)


def test_library_api_invalidation_reopens_other_threads_on_next_access(tmp_path, monkeypatch):
    monkeypatch.setattr(library_api, "path_config_base", lambda: str(tmp_path))
    _seed_library_db(tmp_path)
    _reset_db_cache(library_api)

    first = library_api._get_db()

    invalidated = threading.Event()

    def invalidate_from_other_thread() -> None:
        library_api._invalidate_db_cache()
        invalidated.set()

    worker = threading.Thread(target=invalidate_from_other_thread)
    worker.start()
    worker.join()

    assert invalidated.is_set()

    second = library_api._get_db()

    assert second is not first
    assert first._conn is None
    assert second._conn is not None
    rows, total = second.recent_albums_page(limit=1, offset=0)
    assert total == 1
    assert rows[0]["album"] == "Album"


def test_search_serializer_skips_current_schema_migration_under_writer_lock(tmp_path):
    db_path = tmp_path / "library.db"
    db = LibraryDB(db_path)
    db.open()
    assert db._conn is not None
    db._conn.execute(f"PRAGMA user_version = {LibraryDB._SCHEMA_VERSION}")
    db.commit()
    db.close()

    writer_ready = threading.Event()
    release_writer = threading.Event()
    writer_errors: list[BaseException] = []

    def hold_writer() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            writer_ready.set()
            assert release_writer.wait(timeout=10)
        except (sqlite3.Error, AssertionError) as exc:  # pragma: no cover - failure path only
            writer_errors.append(exc)
        finally:
            conn.rollback()
            conn.close()

    writer = threading.Thread(target=hold_writer)
    writer.start()
    assert writer_ready.wait(timeout=5), writer_errors

    try:
        with sqlite3.connect(db_path) as reader:
            assert reader.execute("SELECT COUNT(*) FROM scanned").fetchone() == (0,)

        track = SimpleNamespace(
            id=1,
            name="Track",
            full_name="Artist - Track",
            artists=[SimpleNamespace(name="Artist")],
            album=SimpleNamespace(id=2, name="Album"),
            duration=180,
            isrc="ISRC123",
            media_metadata_tags=[],
            audio_quality="HIGH",
        )
        app = FastAPI()

        @app.get("/serialize")
        def serialize_track() -> dict:
            try:
                return _serialize_track(track)
            except sqlite3.OperationalError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        with TestClient(app) as client:
            response = client.get("/serialize")

        assert response.status_code == 200, response.json()
        assert response.json()["isrc"] == "ISRC123"
    finally:
        release_writer.set()
        writer.join(timeout=5)

    assert not writer_errors
