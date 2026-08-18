"""Reproduce SQLite writer-lock deaths between library grouping and the worker."""

from __future__ import annotations

import sqlite3
import threading
import wave
from pathlib import Path
from types import SimpleNamespace

from tidal_dl.gui.services.download_job_service import DownloadJobService
from tidal_dl.helper.library_db import LibraryDB
from tidal_dl.model.downloader import DownloadOutcome


def _seed_compatible_albums(db: LibraryDB, *, count: int = 3) -> None:
    suffixes = ("", " (Live)", " (Deluxe)", " (Remastered)")
    for index in range(count):
        album = "Album" + suffixes[index]
        prefix = chr(ord("a") + index)
        for track in range(1, 5):
            db.record(
                f"/music/{prefix}{track}.flac",
                status="tagged",
                artist="Artist",
                album_artist="Artist",
                title=f"Song {track}",
                album=album,
                duration=180 + track,
                isrc=f"USAAA20{track:05d}",
                track_number=track,
                track_total=10,
                disc_number=1,
                disc_total=1,
                art_available=False,
            )
    db.commit()


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b"\x00\x00" * 100)


def _claim_with_short_busy(db_path: Path):
    db = LibraryDB(db_path)
    db.open()
    assert db._conn is not None
    db._conn.execute("PRAGMA busy_timeout=50")
    try:
        return db.claim_next_download_job()
    finally:
        db.close()


def _download_fakes(output_path: Path):
    class FakeTrack:
        id = 123
        name = "Song"
        full_name = "Song"
        duration = 1
        artists = ()
        album = None

    class FakeSession:
        def track(self, track_id):
            assert track_id == 123
            return FakeTrack()

    class FakeTidal:
        session = FakeSession()

    class FakeSettings:
        data = SimpleNamespace(
            download_base_path=str(output_path.parent),
            skip_existing=True,
            format_track="{track_title}",
            quality_audio="LOSSLESS",
        )

    class FakeDownload:
        def __init__(self, **kwargs):
            pass

        def item(self, **kwargs):
            return DownloadOutcome.DOWNLOADED, output_path

    return FakeSettings, FakeTidal, FakeDownload


def test_worker_begin_immediate_survives_overlapping_album_card_write(tmp_path, monkeypatch):
    """A full regroup must not hold the writer lock across remaining pair assessments.

    Mac gate: worker died at BEGIN IMMEDIATE while library API grouping wrote.
    The second assess_pair is the overlapping CPU window after the first persist.
    """
    from tidal_dl.gui.api.library import _album_cards
    from tidal_dl.helper import album_grouping

    db_path = tmp_path / "library.db"
    db = LibraryDB(db_path)
    db.open()
    _seed_compatible_albums(db, count=3)
    job_id = db.create_download_job_if_not_active(kind="download", track_id=123)
    db.close()
    assert job_id is not None

    second_assess_started = threading.Event()
    claim_finished = threading.Event()
    claim_result: dict[str, object] = {}
    assess_calls = 0
    real_assess = album_grouping.assess_pair

    def hooked_assess(*args, **kwargs):
        nonlocal assess_calls
        assess_calls += 1
        result = real_assess(*args, **kwargs)
        if assess_calls == 2:
            second_assess_started.set()
            assert claim_finished.wait(timeout=5)
        return result

    monkeypatch.setattr(album_grouping, "assess_pair", hooked_assess)

    def claim_while_grouping() -> None:
        assert second_assess_started.wait(timeout=5)
        try:
            claim_result["row"] = _claim_with_short_busy(db_path)
        except sqlite3.OperationalError as exc:
            claim_result["error"] = exc
        finally:
            claim_finished.set()

    claimer = threading.Thread(target=claim_while_grouping)
    claimer.start()
    grouping_db = LibraryDB(db_path)
    grouping_db.open()
    try:
        cards = _album_cards(grouping_db)
    finally:
        grouping_db.close()
        if not claim_finished.is_set():
            claim_finished.set()
        claimer.join(timeout=5)

    assert assess_calls >= 2
    assert "error" not in claim_result, repr(claim_result.get("error"))
    claimed = claim_result.get("row")
    assert isinstance(claimed, dict)
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"
    assert len(cards) >= 1

    output = tmp_path / "music" / "Song.wav"
    _write_wav(output)
    service = DownloadJobService(db_path=db_path, autostart=False)
    fakes = _download_fakes(output)
    job_mod = __import__(
        "tidal_dl.gui.services.download_job_service", fromlist=["Settings"]
    )
    monkeypatch.setattr(job_mod, "Settings", fakes[0])
    monkeypatch.setattr(job_mod, "Tidal", fakes[1])
    monkeypatch.setattr(job_mod, "Download", fakes[2])
    from tidal_dl.gui.services.job_models import DownloadJob

    service.execute_job_for_test(DownloadJob.from_row(claimed))
    stored = service.get_job_for_test(job_id)
    assert stored is not None
    assert stored.status.value == "done"


def test_scan_metadata_io_does_not_block_worker_begin_immediate(tmp_path, monkeypatch):
    """Post-download indexing must not hold the writer lock while reading tags."""
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.gui.services.download_job_service import scan_new_downloads

    library_dir = tmp_path / "music"
    first = library_dir / "a.wav"
    second = library_dir / "b.wav"
    _write_wav(first)
    _write_wav(second)

    db_path = tmp_path / "library.db"
    db = LibraryDB(db_path)
    db.open()
    job_id = db.create_download_job_if_not_active(kind="download", track_id=321)
    db.close()
    assert job_id is not None

    second_read_started = threading.Event()
    claim_finished = threading.Event()
    claim_result: dict[str, object] = {}
    reads = 0
    real_read = library_api._read_metadata

    def hooked_read(path, roots):
        nonlocal reads
        result = real_read(path, roots)
        reads += 1
        if reads == 2:
            second_read_started.set()
            assert claim_finished.wait(timeout=5)
        return result

    monkeypatch.setattr(library_api, "_read_metadata", hooked_read)

    def claim_while_scanning() -> None:
        assert second_read_started.wait(timeout=5)
        try:
            claim_result["row"] = _claim_with_short_busy(db_path)
        except sqlite3.OperationalError as exc:
            claim_result["error"] = exc
        finally:
            claim_finished.set()

    claimer = threading.Thread(target=claim_while_scanning)
    claimer.start()
    scan_db = LibraryDB(db_path)
    scan_db.open()
    try:
        scan_new_downloads(
            scan_db,
            SimpleNamespace(data=SimpleNamespace(download_base_path=str(library_dir))),
        )
    finally:
        scan_db.close()
        if not claim_finished.is_set():
            claim_finished.set()
        claimer.join(timeout=5)

    assert reads >= 2
    assert "error" not in claim_result, repr(claim_result.get("error"))
    claimed = claim_result.get("row")
    assert isinstance(claimed, dict)
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"


def test_upgrade_cleanup_trash_io_does_not_block_worker_begin_immediate(tmp_path, monkeypatch):
    """Upgrade cleanup must trash files before opening a reserved write."""
    from tidal_dl.gui.services import upgrade_jobs

    album_dir = tmp_path / "Artist" / "Album"
    album_dir.mkdir(parents=True)
    old_path = album_dir / "old.flac"
    sibling = album_dir / "sibling.flac"
    new_path = album_dir / "new.flac"
    for path in (old_path, sibling, new_path):
        path.write_bytes(b"audio")

    db_path = tmp_path / "library.db"
    db = LibraryDB(db_path)
    db.open()
    for path in (old_path, sibling, new_path):
        db.record(
            str(path),
            status="tagged",
            isrc="USAAA2199999",
            artist="Artist",
            title="Song",
            album="Album",
        )
    db.commit()
    job_id = db.create_download_job_if_not_active(kind="download", track_id=654)
    db.close()
    assert job_id is not None

    second_trash_started = threading.Event()
    claim_finished = threading.Event()
    claim_result: dict[str, object] = {}
    trashes = 0
    real_trash = upgrade_jobs.trash_file

    def hooked_trash(path: str) -> None:
        nonlocal trashes
        real_trash(path)
        trashes += 1
        if trashes == 2:
            second_trash_started.set()
            assert claim_finished.wait(timeout=5)

    monkeypatch.setattr(upgrade_jobs, "trash_file", hooked_trash)

    def claim_while_trashing() -> None:
        assert second_trash_started.wait(timeout=5)
        try:
            claim_result["row"] = _claim_with_short_busy(db_path)
        except sqlite3.OperationalError as exc:
            claim_result["error"] = exc
        finally:
            claim_finished.set()

    claimer = threading.Thread(target=claim_while_trashing)
    claimer.start()
    cleanup_db = LibraryDB(db_path)
    cleanup_db.open()
    try:
        removed = upgrade_jobs.cleanup_replaced_track_files(
            cleanup_db,
            old_path=str(old_path),
            new_path=str(new_path),
        )
    finally:
        cleanup_db.close()
        if not claim_finished.is_set():
            claim_finished.set()
        claimer.join(timeout=5)

    assert trashes >= 2
    assert set(removed) == {str(old_path), str(sibling)}
    assert "error" not in claim_result, repr(claim_result.get("error"))
    claimed = claim_result.get("row")
    assert isinstance(claimed, dict)
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"


def test_worker_loop_survives_transient_lock_and_reaches_done(tmp_path, monkeypatch):
    """A held writer must fail BEGIN IMMEDIATE once; the worker thread must stay alive."""
    from tidal_dl.gui.services import download_job_service as job_mod

    db_path = tmp_path / "library.db"
    output = tmp_path / "music" / "Song.wav"
    _write_wav(output)
    service = DownloadJobService(db_path=db_path, autostart=False)
    queued = service.enqueue_download([123])
    assert queued["status"] == "queued"
    inspect_db = LibraryDB(db_path)
    inspect_db.open()
    assert inspect_db._conn is not None
    job_row = inspect_db._conn.execute("SELECT id FROM download_jobs").fetchone()
    inspect_db.close()
    assert job_row is not None
    job_id = int(job_row["id"])
    fakes = _download_fakes(output)
    monkeypatch.setattr(job_mod, "Settings", fakes[0])
    monkeypatch.setattr(job_mod, "Tidal", fakes[1])
    monkeypatch.setattr(job_mod, "Download", fakes[2])

    real_open = LibraryDB.open

    def short_busy_open(self) -> None:
        real_open(self)
        assert self._conn is not None
        self._conn.execute("PRAGMA busy_timeout=50")

    monkeypatch.setattr(LibraryDB, "open", short_busy_open)

    real_claim = LibraryDB.claim_next_download_job
    first_lock = threading.Event()
    lock_errors: list[BaseException] = []

    def tracking_claim(self, *args, **kwargs):
        try:
            return real_claim(self, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                lock_errors.append(exc)
                first_lock.set()
            raise

    monkeypatch.setattr(LibraryDB, "claim_next_download_job", tracking_claim)

    writer_ready = threading.Event()
    release_writer = threading.Event()
    writer_errors: list[BaseException] = []

    def hold_writer() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            writer_ready.set()
            assert release_writer.wait(timeout=10)
        except (sqlite3.Error, AssertionError) as exc:  # pragma: no cover
            writer_errors.append(exc)
        finally:
            conn.rollback()
            conn.close()

    writer = threading.Thread(target=hold_writer)
    writer.start()
    assert writer_ready.wait(timeout=5), writer_errors

    try:
        service.start_worker()
        assert first_lock.wait(timeout=5), "worker never hit a lock error"
        assert service._worker_thread is not None
        assert service._worker_thread.is_alive()
    finally:
        release_writer.set()
        writer.join(timeout=5)

    deadline = threading.Event()
    finished = False
    for _ in range(40):
        stored = service.get_job_for_test(job_id)
        if stored is not None and stored.status.value == "done":
            finished = True
            break
        deadline.wait(0.05)

    service.stop_worker(join_timeout=2.0)
    assert not writer_errors
    assert lock_errors
    assert finished
    history = service.history(limit=10)["downloads"]
    assert history and history[0]["status"] == "done"
