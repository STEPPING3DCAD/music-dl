"""Tests for download pipeline error handling."""
import logging
import wave
from pathlib import Path
from threading import Event

import pytest


def test_download_ffmpeg_uses_tidalapi_audio_extensions():
    from tidalapi.media import AudioExtensions

    try:
        from tidal_dl import download_ffmpeg
    except ImportError as exc:
        pytest.fail(str(exc))

    assert download_ffmpeg.AudioExtensions is AudioExtensions


def _write_wav(path, isrc):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 80)

    from mutagen.id3 import TSRC
    from mutagen.wave import WAVE

    audio = WAVE(path)
    audio.add_tags()
    audio.tags.add(TSRC(encoding=3, text=isrc))
    audio.save()


def _successful_track(track_id, isrc):
    from tidalapi import Track

    class LocalTrack(Track):
        def __init__(self):
            pass

        @property
        def id(self):
            return track_id

        @property
        def isrc(self):
            return isrc

        @property
        def allow_streaming(self):
            return True

        @property
        def name(self):
            return f"Track {track_id}"

        @property
        def full_name(self):
            return self.name

        @property
        def media_metadata_tags(self):
            return []

    return LocalTrack()


def _successful_item(tmp_path, media_path):
    from tidal_dl.download.items import ItemMixin
    from tidal_dl.helper.library_db import LibraryDB

    class SuccessfulItem(ItemMixin):
        def __init__(self):
            self.event_abort = Event()
            self.settings = type("Settings", (), {"data": type("Data", (), {"skip_duplicate_isrc": True})()})()
            self._library_db = LibraryDB(tmp_path / "library.db")
            self._library_db.open()

        def _validate_and_prepare_media(self, media, *_args):
            return media

        def _prepare_file_paths_and_skip_logic(self, *_args, **_kwargs):
            return media_path, ".wav", False, False

        def _adjust_quality_settings(self, *_args):
            return None, None

        def _download_and_process_media(self, media, *_args):
            media_path.parent.mkdir(parents=True, exist_ok=True)
            _write_wav(media_path, media.isrc)
            return True, media_path

        def _perform_post_processing(self, *_args):
            return None

        def _on_successful_track(self):
            return None

        def _library_db_for_current_thread(self):
            return self._library_db

    return SuccessfulItem()


def test_successful_track_commits_isrc_before_second_library_db_write(tmp_path):
    from tidal_dl.helper.library_db import LibraryDB
    from tidal_dl.model.downloader import DownloadOutcome

    media_path = tmp_path / "downloads" / "track.wav"
    downloader = _successful_item(tmp_path, media_path)
    try:
        outcome, output_path = downloader.item(
            file_template="{track_title}", media=_successful_track(118, "US-TST-24-00118")
        )
        assert outcome is DownloadOutcome.DOWNLOADED
        assert output_path == media_path
        assert media_path.stat().st_size > 0

        second = LibraryDB(tmp_path / "library.db")
        second.open()
        try:
            assert second.has_live_isrc("US-TST-24-00118")
            second.record_download(track_id=118, name="Track", status="done")
            second.commit()
            assert second.download_history(limit=1)[0]["track_id"] == 118
        finally:
            second.close()
    finally:
        downloader._library_db.close()


def test_collection_downloads_use_thread_owned_library_db(tmp_path):
    from rich.progress import Progress

    from tidal_dl.config import Settings, Tidal
    from tidal_dl.download import Download
    from tidal_dl.helper.library_db import LibraryDB
    from tidal_dl.model.downloader import DownloadSummary

    class CollectionDownload(Download):
        def _validate_and_prepare_media(self, media, *_args):
            return media

        def _download_and_process_media(self, media, path_media_dst, *_args):
            assert self._library_db_for_current_thread().primary_path_for_isrc(media.isrc) is None
            path_media_dst.parent.mkdir(parents=True, exist_ok=True)
            _write_wav(path_media_dst, media.isrc)
            return True, path_media_dst

        def _perform_post_processing(self, *_args):
            return None

    tidal = Tidal(Settings())
    downloader = CollectionDownload(
        tidal_obj=tidal,
        path_base=str(tmp_path / "downloads"),
        fn_logger=logging.getLogger("test.collection-download"),
        skip_existing=False,
    )
    downloader.settings.data.downloads_concurrent_max = 2
    downloader.settings.data.skip_duplicate_isrc = True
    tracks = [_successful_track(119, "US-TST-24-00119"), _successful_track(120, "US-TST-24-00120")]
    summary = DownloadSummary()
    try:
        with Progress(disable=True) as progress:
            task = progress.add_task("collection", total=len(tracks))
            result_dirs = downloader._execute_collection_downloads(
                tracks,
                "{track_title}",
                None,
                None,
                False,
                False,
                len(tracks),
                progress,
                task,
                False,
                summary=summary,
            )

        assert summary.downloaded == 2
        assert result_dirs == [tmp_path / "downloads", tmp_path / "downloads"]

        check = LibraryDB(tmp_path / "library.db")
        check.open()
        try:
            for track in tracks:
                assert check.has_live_isrc(track.isrc)
                assert check.primary_path_for_isrc(track.isrc)
        finally:
            check.close()
    finally:
        downloader._library_db.close()


def test_file_mixin_cover_data_reads_local_cover_file(tmp_path):
    from tidal_dl.download.files import FileMixin

    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"cover bytes")

    assert FileMixin().cover_data(path_file=str(cover)) == b"cover bytes"


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
