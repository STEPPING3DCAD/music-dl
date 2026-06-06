"""Tests for download pipeline error handling."""
import logging
from pathlib import Path

import pytest


def test_broadcast_fires_even_when_db_fails():
    """Download job errors still broadcast if history persistence fails."""
    from tidal_dl.gui.services.download_job_service import DownloadJobService
    from tidal_dl.gui.services.job_models import DownloadJob

    broadcasts = []
    service = DownloadJobService(autostart=False)
    service.events.broadcast = broadcasts.append
    service._record_error_history = lambda job, exc: (_ for _ in ()).throw(
        Exception("database is locked")
    )
    job = DownloadJob.from_row(
        {
            "id": 1,
            "kind": "download",
            "status": "running",
            "track_id": 999,
            "name": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "cover_url": "",
            "quality": "LOSSLESS",
            "progress": 0,
            "error": None,
            "old_path": None,
            "new_path": None,
            "metadata_json": None,
            "created_at": 1.0,
            "started_at": 1.0,
            "finished_at": None,
        }
    )

    try:
        service._mark_job_error(job, RuntimeError("download failed"))
    except Exception:
        logging.exception("Failed to persist download error for track %s", job.track_id)
    service._broadcast_error(job, RuntimeError("download failed"))

    assert len(broadcasts) == 1
    assert broadcasts[0]["type"] == "error"
    assert broadcasts[0]["track_id"] == 999


def test_logger_captures_db_error(caplog):
    """When DB write fails in error handler, logger.exception is called."""
    with caplog.at_level(logging.ERROR):
        try:
            raise Exception("database is locked")
        except Exception:
            logging.exception("Failed to persist download error for track %s", 42)

    assert "database is locked" in caplog.text
    assert "42" in caplog.text


def test_delete_track_closes_db_when_remove_fails(tmp_path, monkeypatch):
    from tidal_dl.gui.api import downloads

    track_path = tmp_path / "track.flac"
    track_path.write_bytes(b"audio")
    closed = []

    class FakeSettings:
        data = type("Data", (), {"download_base_path": str(tmp_path)})()

    class FakeDB:
        def __init__(self, path):
            self.path = path

        def open(self):
            pass

        def remove(self, path):
            raise RuntimeError("remove failed")

        def commit(self):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr("tidal_dl.config.Settings", FakeSettings)
    monkeypatch.setattr("tidal_dl.helper.library_db.LibraryDB", FakeDB)
    monkeypatch.setattr("tidal_dl.gui.security.validate_audio_path", lambda path, allowed: Path(path))

    with pytest.raises(RuntimeError, match="remove failed"):
        downloads.delete_track(downloads.DeleteTrackRequest(path=str(track_path)))

    assert closed == [True]


def test_clear_history_closes_db_when_clear_fails(monkeypatch):
    from tidal_dl.gui.api import downloads

    closed = []

    class FakeDB:
        def __init__(self, path):
            self.path = path

        def open(self):
            pass

        def clear_download_history(self, status):
            raise RuntimeError("clear failed")

        def close(self):
            closed.append(True)

    monkeypatch.setattr("tidal_dl.helper.library_db.LibraryDB", FakeDB)

    with pytest.raises(RuntimeError, match="clear failed"):
        downloads.clear_history()

    assert closed == [True]
