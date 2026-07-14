"""Tests for LibraryDB — CRUD, pagination, dedup, migration, pragmas."""
import sqlite3
import pytest
from tidal_dl.helper.library_db import LibraryDB
from tidal_dl.helper.library_db.utils import (
    _canonical_track_identity,
    _canonical_track_preference,
    _canonicalize_tracks,
    _is_excluded_library_path,
    _local_quality_rank,
)


@pytest.fixture
def db(tmp_path):
    d = LibraryDB(tmp_path / "test.db")
    d.open()
    yield d
    d.close()


class TestPragmas:
    def test_wal_mode_enabled(self, db):
        mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_busy_timeout_set(self, db):
        timeout = db._conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 5000

    def test_open_quarantines_corrupt_db_and_recreates_schema(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_path.write_text("not sqlite", encoding="utf-8")

        recovered = LibraryDB(db_path)
        recovered.open()
        try:
            tables = {
                row[0]
                for row in recovered._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            recovered.close()

        assert "scanned" in tables
        assert "download_jobs" in tables
        assert list(tmp_path.glob("test.db.corrupt-*"))

    def test_open_migrates_legacy_scanned_schema_missing_isrc(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE scanned (path TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO scanned (path, status) VALUES (?, ?)",
            ("/music/old.flac", "tagged"),
        )
        conn.commit()
        conn.close()

        migrated = LibraryDB(db_path)
        migrated.open()
        try:
            cols = {
                row["name"]
                for row in migrated._conn.execute("PRAGMA table_info(scanned)")
            }
            row = migrated.get("/music/old.flac")
        finally:
            migrated.close()

        assert {
            "isrc",
            "artist",
            "title",
            "scanned_at",
            "art_available",
            "codec",
            "metadata_complete",
        } <= cols
        assert row is not None
        assert row["status"] == "tagged"

    def test_open_backfills_definitive_legacy_inspection_facts(self, tmp_path):
        db_path = tmp_path / "test.db"
        original = LibraryDB(db_path)
        original.open()
        original.record(
            "/music/complete.flac",
            status="tagged",
            artist="Artist",
            title="Song",
            album="Album",
        )
        original.record(
            "/music/ambiguous.m4a",
            status="tagged",
            artist="Artist",
            title="Song",
            album="Album",
        )
        original.commit()
        original.close()

        reopened = LibraryDB(db_path)
        reopened.open()
        try:
            complete = reopened.get("/music/complete.flac")
            ambiguous = reopened.get("/music/ambiguous.m4a")
        finally:
            reopened.close()

        assert complete["metadata_complete"] == 1
        assert complete["codec"] == "flac"
        assert ambiguous["metadata_complete"] == 1
        assert ambiguous["codec"] is None


class TestCRUD:
    def test_record_and_get(self, db):
        db.record("/music/track.flac", status="tagged", artist="Daft Punk",
                  title="One More Time", album="Discovery", duration=320,
                  quality="44100Hz/16bit", fmt="FLAC", genre="Electronic")
        db.commit()
        row = db.get("/music/track.flac")
        assert row is not None
        assert row["artist"] == "Daft Punk"
        assert row["format"] == "FLAC"
        assert row["quality"] == "44100Hz/16bit"

    def test_get_nonexistent_returns_none(self, db):
        assert db.get("/nonexistent.flac") is None

    def test_record_upsert(self, db):
        db.record("/a.flac", status="tagged", artist="A")
        db.commit()
        db.record("/a.flac", status="tagged", artist="B")
        db.commit()
        assert db.get("/a.flac")["artist"] == "B"

    def test_record_persists_art_availability_without_erasing_known_value(self, db):
        db.record("/a.flac", status="tagged", art_available=True)
        db.commit()
        db.record("/a.flac", status="tagged")
        db.commit()

        assert db.get("/a.flac")["art_available"] == 1

    def test_record_persists_inspection_facts_without_erasing_known_values(self, db):
        db.record(
            "/a.m4a",
            status="tagged",
            codec="flac",
            metadata_complete=True,
        )
        db.commit()
        db.record("/a.m4a", status="tagged")
        db.commit()

        row = db.get("/a.m4a")
        assert row["codec"] == "flac"
        assert row["metadata_complete"] == 1

    def test_remove(self, db):
        db.record("/a.flac", status="tagged")
        db.commit()
        db.remove("/a.flac")
        db.commit()
        assert db.get("/a.flac") is None

    def test_is_known(self, db):
        assert not db.is_known("/a.flac")
        db.record("/a.flac", status="tagged")
        db.commit()
        assert db.is_known("/a.flac")

    def test_known_paths(self, db):
        db.record("/a.flac", status="tagged")
        db.record("/b.flac", status="unreadable")
        db.commit()
        assert db.known_paths() == {"/a.flac", "/b.flac"}

    def test_complete_paths_excludes_blank_cached_metadata(self, db):
        db.record(
            "/complete.flac",
            status="tagged",
            artist="Artist",
            title="Title",
            album="Album",
            duration=180,
        )
        db.record(
            "/stale.flac",
            status="tagged",
            artist="",
            title="",
            album="",
            duration=180,
        )
        db.commit()

        assert db.complete_paths() == {"/complete.flac"}


class TestCanonicalTracks:
    def test_excluded_path_requires_whole_case_insensitive_component(self):
        assert _is_excluded_library_path("/Music/#recycle/song.flac")
        assert _is_excluded_library_path("/Music/.TRASHES/song.flac")
        assert _is_excluded_library_path("/Music/undo-staging/song.flac")
        assert not _is_excluded_library_path("/Music/#recycled/song.flac")
        assert not _is_excluded_library_path("/Music/my.Trashes.album/song.flac")

    def test_identity_prefers_isrc(self):
        row = {"path": "/a.flac", "isrc": " US-ABC-12 ", "title": "One"}
        assert _canonical_track_identity(row) == ("isrc", "us-abc-12")

    def test_identity_falls_back_to_complete_metadata_and_exact_duration(self):
        first = {
            "path": "/a.flac",
            "title": " Song ",
            "artist": "ARTIST",
            "album": "Album",
            "duration": 180.4,
            "metadata_complete": True,
        }
        second = dict(first, path="/b.flac", title="song", artist="artist")
        assert _canonical_track_identity(first) == _canonical_track_identity(second)
        assert _canonical_track_identity(first)[-1] == 180

    def test_incomplete_or_placeholder_metadata_stays_unique_by_path(self):
        incomplete = {
            "path": "/a.flac",
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "duration": 180,
            "metadata_complete": False,
        }
        placeholder = {
            "path": "/b.flac",
            "title": "Song",
            "artist": "Unknown Artist",
            "album": "Unknown Album",
            "duration": 180,
        }
        assert _canonical_track_identity(incomplete) == ("path", "/a.flac")
        assert _canonical_track_identity(placeholder) == ("path", "/b.flac")

    def test_codec_controls_quality_before_container(self):
        assert _local_quality_rank("192000Hz/24bit", "M4A", "flac") == 4
        assert _local_quality_rank("44100Hz/16bit", "M4A", "aac") == 1
        assert _local_quality_rank("44100Hz/16bit", "M4A", None) == 1

    def test_preference_favors_complete_quality_canonical_suffix_then_path(self):
        base = {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "duration": 180,
            "metadata_complete": True,
            "quality": "44100Hz/16bit",
            "format": "FLAC",
            "codec": "flac",
        }
        rows = [
            dict(base, path="/music/song_01.flac"),
            dict(base, path="/music/song.flac"),
            dict(base, path="/music/long/path/song.flac", quality="96000Hz/24bit"),
        ]
        assert min(rows, key=_canonical_track_preference)["path"] == (
            "/music/long/path/song.flac"
        )

        tied = [dict(base, path="/b/song.flac"), dict(base, path="/a/song.flac")]
        assert min(tied, key=_canonical_track_preference)["path"] == "/a/song.flac"

    def test_canonicalize_keeps_one_best_row_per_identity(self):
        rows = [
            {
                "path": "/lossy.m4a",
                "isrc": "ABC",
                "metadata_complete": True,
                "quality": "44100Hz/16bit",
                "format": "M4A",
                "codec": "aac",
            },
            {
                "path": "/lossless.m4a",
                "isrc": "ABC",
                "metadata_complete": True,
                "quality": "44100Hz/16bit",
                "format": "M4A",
                "codec": "flac",
            },
        ]
        assert [row["path"] for row in _canonicalize_tracks(rows)] == [
            "/lossless.m4a"
        ]

    def test_canonicalize_joins_isrcless_copy_to_one_exact_isrc_match(self):
        common = {
            "title": "Será Llena la Tierra",
            "artist": "Marco Barrientos",
            "album": "Más de Ti",
            "duration": 407,
            "metadata_complete": True,
            "format": "M4A",
            "quality": "44100Hz/16bit",
        }
        rows = [
            dict(common, path="/lossy.m4a", isrc="ABC", codec="aac"),
            dict(common, path="/lossless.m4a", isrc=None, codec="flac"),
        ]

        canonical = _canonicalize_tracks(rows)

        assert [row["path"] for row in canonical] == ["/lossless.m4a"]

    def test_canonicalize_collapses_exact_metadata_even_when_isrcs_conflict(self):
        common = {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "duration": 180,
            "metadata_complete": True,
        }
        rows = [
            dict(common, path="/a.flac", isrc="AAA"),
            dict(common, path="/b.flac", isrc="BBB"),
            dict(common, path="/unknown.flac", isrc=None),
        ]

        assert len(_canonicalize_tracks(rows)) == 1

    def test_prune_excluded_rows_repoints_related_data_without_losing_history(self, db):
        canonical = "/music/song.flac"
        excluded = "/music/#recycle/song.flac"
        unmatched = "/music/.Trash/orphan.flac"
        common = {
            "status": "tagged",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "duration": 180,
            "isrc": "ABC",
            "metadata_complete": True,
        }
        db.record(canonical, **common)
        db.record(excluded, **common)
        db.record(
            unmatched,
            status="tagged",
            artist="Other",
            title="Orphan",
            album="Other",
            duration=200,
            metadata_complete=True,
        )
        db.add_favorite(path=canonical, artist="Artist", title="Song")
        db.add_favorite(path=excluded, artist="Artist", title="Song")
        db.add_favorite(path=unmatched, artist="Other", title="Orphan")
        db.log_play_event(excluded, artist="Artist", played_at=1)
        db.log_play_event(unmatched, artist="Other", played_at=2)
        db.commit()

        removed = db.prune_excluded_rows()
        db.commit()

        assert removed == 2
        assert db.get(excluded) is None
        assert db.get(unmatched) is None
        favorite_rows = db._conn.execute(
            "SELECT path, title FROM favorites ORDER BY id"
        ).fetchall()
        assert [(row["path"], row["title"]) for row in favorite_rows] == [
            (canonical, "Song"),
            (None, "Orphan"),
        ]
        event_paths = [
            row["path"]
            for row in db._conn.execute("SELECT path FROM play_events ORDER BY id")
        ]
        assert event_paths == [canonical, unmatched]

    def test_repair_worklist_does_not_retry_inspected_incomplete_tags(self, db):
        db.record(
            "/music/untagged.flac",
            status="needs_isrc",
            artist="Unknown Artist",
            title="untagged",
            album="Unknown Album",
            codec="flac",
            metadata_complete=False,
        )
        db.record(
            "/music/pending.flac",
            status="needs_isrc",
            artist="",
            title="",
            album="",
        )
        db.commit()

        assert [row["path"] for row in db.metadata_repair_worklist()] == [
            "/music/pending.flac"
        ]


class TestRecentPlays:
    def test_recent_plays_returns_latest_unique_scanned_tracks(self, db):
        db.record("/music/a.flac", status="tagged", artist="A", title="Alpha", album="One", duration=180, quality="LOSSLESS", fmt="FLAC")
        db.record("/music/b.flac", status="tagged", artist="B", title="Beta", album="Two", duration=240, quality="HI_RES", fmt="FLAC")
        db.log_play_event("/music/a.flac", artist="A", duration=180, played_at=100)
        db.log_play_event("/music/b.flac", artist="B", duration=240, played_at=200)
        db.log_play_event("/music/a.flac", artist="A", duration=180, played_at=300)
        db.commit()

        recent = db.recent_plays(limit=10)

        assert [track["path"] for track in recent] == ["/music/a.flac", "/music/b.flac"]
        assert recent[0]["played_at"] == 300
        assert recent[0]["name"] == "Alpha"
        assert recent[0]["is_local"] is True

    def test_recent_plays_include_codec(self, db):
        db.record(
            "/music/a.m4a",
            status="tagged",
            artist="A",
            title="Alpha",
            album="One",
            codec="flac",
            fmt="M4A",
        )
        db.log_play_event("/music/a.m4a", artist="A", played_at=100)
        db.commit()

        assert db.recent_plays()[0]["codec"] == "flac"

    def test_recent_plays_skips_events_without_scanned_track(self, db):
        db.record("/music/a.flac", status="tagged", artist="A", title="Alpha")
        db.log_play_event("/music/missing.flac", artist="Ghost", played_at=500)
        db.log_play_event("/music/a.flac", artist="A", played_at=400)
        db.commit()

        recent = db.recent_plays(limit=10)

        assert [track["path"] for track in recent] == ["/music/a.flac"]


class TestPagination:
    def _seed(self, db, n=10):
        for i in range(n):
            db.record(f"/track_{i:02d}.flac", status="tagged",
                      artist=f"Artist {i % 3}", title=f"Track {i}",
                      album=f"Album {i % 2}", duration=200 + i)
        db.commit()

    def test_tracks_page_limit_offset(self, db):
        self._seed(db)
        rows, total = db.tracks_page(limit=3, offset=0)
        assert len(rows) == 3
        assert total == 10

    def test_tracks_page_search(self, db):
        self._seed(db)
        rows, total = db.tracks_page(query="Track 5", limit=50, offset=0)
        assert total == 1
        assert rows[0]["title"] == "Track 5"

    def test_artists_page(self, db):
        self._seed(db)
        rows, total = db.artists_page(limit=50, offset=0)
        assert total == 3  # Artist 0, 1, 2

    def test_all_albums(self, db):
        self._seed(db)
        albums = db.all_albums()
        assert len(albums) == 2  # Album 0, Album 1

    def test_tracks_page_canonicalizes_before_total_and_pagination(self, db):
        common = {
            "status": "tagged",
            "artist": "Artist",
            "album": "Album",
            "metadata_complete": True,
            "duration": 180,
            "fmt": "M4A",
        }
        db.record(
            "/music/lossy.m4a",
            title="Alpha",
            isrc="ABC",
            quality="44100Hz/16bit",
            codec="aac",
            **common,
        )
        db.record(
            "/music/lossless.m4a",
            title="Alpha",
            isrc="ABC",
            quality="44100Hz/16bit",
            codec="flac",
            **common,
        )
        db.record(
            "/music/beta.flac",
            title="Beta",
            isrc="DEF",
            quality="44100Hz/16bit",
            codec="flac",
            **common,
        )
        db.record(
            "/music/#recycle/beta.flac",
            title="Beta",
            isrc="DEF",
            quality="96000Hz/24bit",
            codec="flac",
            **common,
        )
        db.commit()

        first, total = db.tracks_page(sort="title", limit=1, offset=0)
        second, second_total = db.tracks_page(sort="title", limit=1, offset=1)

        assert total == second_total == 2
        assert [first[0]["path"], second[0]["path"]] == [
            "/music/lossless.m4a",
            "/music/beta.flac",
        ]

    def test_artist_and_album_aggregates_use_only_canonical_active_rows(self, db):
        common = {
            "status": "tagged",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "duration": 180,
            "isrc": "ABC",
            "metadata_complete": True,
            "quality": "44100Hz/16bit",
            "codec": "flac",
            "fmt": "FLAC",
        }
        db.record("/music/song.flac", **common)
        db.record("/music/copy/song.flac", **common)
        db.record(
            "/music/#recycle/other.flac",
            status="tagged",
            artist="Deleted Artist",
            title="Other",
            album="Deleted Album",
            duration=180,
            metadata_complete=True,
        )
        db.commit()

        artists, artist_total = db.artists_page(limit=50)
        albums = db.all_albums()
        artist_albums = db.albums_by_artist("Artist")

        assert artist_total == 1
        assert artists[0]["track_count"] == 1
        assert artists[0]["album_count"] == 1
        assert len(albums) == 1
        assert albums[0]["track_count"] == 1
        assert artist_albums[0]["track_count"] == 1


class TestAlbumDedup:
    def test_album_tracks_dedup_by_title(self, db):
        """Two copies of same title — keep shortest path."""
        db.record("/short/a.flac", status="tagged", artist="X", title="Song", album="Alb")
        db.record("/very/long/path/a.flac", status="tagged", artist="X", title="Song", album="Alb")
        db.commit()
        tracks = db.album_tracks("X", "Alb")
        assert len(tracks) == 1
        assert tracks[0]["path"] == "/short/a.flac"

    def test_album_tracks_dedup_ignores_title_casing_and_prefers_higher_quality(self, db):
        db.record(
            "/short/old.flac",
            status="tagged",
            artist="X",
            title="Purpose For Pain",
            album="Alb",
            quality="44100Hz/16bit",
            fmt="FLAC",
        )
        db.record(
            "/very/long/path/new.flac",
            status="tagged",
            artist="X",
            title="Purpose for Pain",
            album="Alb",
            quality="96000Hz/24bit",
            fmt="FLAC",
        )
        db.commit()

        tracks = db.album_tracks("X", "Alb")

        assert len(tracks) == 1
        assert tracks[0]["path"] == "/very/long/path/new.flac"


class TestDownloadHistory:
    def test_record_and_retrieve(self, db):
        db.record_download(track_id=123, name="Track", status="done",
                           artist="A", album="B", started_at=1.0, finished_at=2.0)
        db.commit()
        history = db.download_history(limit=10)
        assert len(history) == 1
        assert history[0]["track_id"] == 123
        assert history[0]["status"] == "done"

    def test_clear_history(self, db):
        db.record_download(track_id=1, name="T1", status="done")
        db.record_download(track_id=2, name="T2", status="error")
        db.commit()
        cleared = db.clear_download_history(status="error")
        assert cleared == 1
        assert len(db.download_history()) == 1


class TestDownloadJobs:
    def test_download_jobs_table_created(self, db):
        assert db._conn is not None
        tables = {
            row["name"]
            for row in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "download_jobs" in tables

        indexes = {
            row["name"]
            for row in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "idx_download_jobs_status_created" in indexes
        assert "idx_download_jobs_track_id" in indexes

    def test_download_job_crud_and_claim_oldest(self, db):
        first = db.create_download_job_if_not_active(
            kind="download", track_id=10, name="First"
        )
        second = db.create_download_job_if_not_active(
            kind="upgrade",
            track_id=11,
            name="Second",
            old_path="/tmp/old.flac",
        )

        claimed = db.claim_next_download_job()

        assert claimed is not None
        assert claimed["id"] == first
        assert claimed["status"] == "running"
        assert claimed["track_id"] == 10

        remaining = db.get_download_job(second)
        assert remaining["status"] == "queued"

    def test_claim_download_job_can_filter_by_kind(self, db):
        upgrade = db.create_download_job_if_not_active(
            kind="upgrade",
            track_id=11,
            name="Upgrade",
            old_path="/tmp/old.flac",
        )
        download = db.create_download_job_if_not_active(
            kind="download", track_id=12, name="Download"
        )

        claimed = db.claim_next_download_job(kind="download")

        assert claimed is not None
        assert claimed["id"] == download
        assert db.get_download_job(upgrade)["status"] == "queued"

    def test_download_job_recovery_marks_active_jobs_interrupted(self, db):
        queued = db.create_download_job_if_not_active(kind="download", track_id=1)
        running = db.create_download_job_if_not_active(kind="download", track_id=2)
        retrying = db.create_download_job_if_not_active(kind="download", track_id=3)
        paused = db.create_download_job_if_not_active(kind="download", track_id=4)
        done = db.create_download_job_if_not_active(kind="download", track_id=5)

        db.update_download_job(running, status="running")
        db.update_download_job(retrying, status="retrying")
        db.update_download_job(paused, status="paused")
        db.update_download_job(done, status="done")
        db.recover_download_jobs()

        assert db.get_download_job(queued)["status"] == "queued"
        assert db.get_download_job(running)["status"] == "interrupted"
        assert db.get_download_job(retrying)["status"] == "interrupted"
        assert db.get_download_job(paused)["status"] == "interrupted"
        assert db.get_download_job(done)["status"] == "done"


class TestFavorites:
    def test_add_and_check(self, db):
        db.add_favorite(path="/a.flac", artist="X", title="Y")
        db.commit()
        assert db.is_favorite(path="/a.flac")
        assert "/a.flac" in db.favorite_paths()

    def test_remove_favorite(self, db):
        db.add_favorite(path="/a.flac", artist="X", title="Y")
        db.commit()
        db.remove_favorite(path="/a.flac")
        db.commit()
        assert not db.is_favorite(path="/a.flac")

    def test_duplicate_add_is_noop(self, db):
        db.add_favorite(path="/a.flac", artist="X", title="Y")
        db.commit()
        db.add_favorite(path="/a.flac", artist="X", title="Y")
        db.commit()
        assert len(db.all_favorites()) == 1


class TestRecentAlbums:
    def _record_recent_album(
        self,
        db,
        *,
        track_id,
        artist,
        album,
        finished_at,
        title="Track 01",
    ):
        slug = f"{artist}-{album}".replace(" ", "_")
        db.record(
            f"/music/{slug}/01.flac",
            status="tagged",
            artist=artist,
            album=album,
            title=title,
        )
        db.record_download(
            track_id=track_id,
            name=title,
            artist=artist,
            album=album,
            status="done",
            finished_at=finished_at,
        )

    def test_same_recent_timestamp_uses_case_insensitive_artist_album_tiebreakers(self, db):
        self._record_recent_album(
            db,
            track_id=1,
            artist="Same Artist",
            album="apple",
            finished_at=2000.0,
        )
        self._record_recent_album(
            db,
            track_id=2,
            artist="Same Artist",
            album="Banana",
            finished_at=2000.0,
        )
        db.commit()

        rows, total = db.recent_albums_page(limit=12, offset=0)

        assert total == 2
        assert [(row["artist"], row["album"]) for row in rows] == [
            ("Same Artist", "apple"),
            ("Same Artist", "Banana"),
        ]

    def test_limit_offset_pages_follow_stable_recent_album_order(self, db):
        self._record_recent_album(
            db,
            track_id=1,
            artist="charlie artist",
            album="Gamma",
            finished_at=2000.0,
        )
        self._record_recent_album(
            db,
            track_id=2,
            artist="Bravo Artist",
            album="Beta",
            finished_at=2000.0,
        )
        self._record_recent_album(
            db,
            track_id=3,
            artist="alpha artist",
            album="Alpha",
            finished_at=2000.0,
        )
        self._record_recent_album(
            db,
            track_id=4,
            artist="Delta Artist",
            album="Delta",
            finished_at=2000.0,
        )
        db.commit()

        page_one, total = db.recent_albums_page(limit=2, offset=0)
        page_two, total_page_two = db.recent_albums_page(limit=2, offset=2)

        assert total == 4
        assert total_page_two == 4
        assert [(row["artist"], row["album"]) for row in page_one] == [
            ("alpha artist", "Alpha"),
            ("Bravo Artist", "Beta"),
        ]
        assert [(row["artist"], row["album"]) for row in page_two] == [
            ("charlie artist", "Gamma"),
            ("Delta Artist", "Delta"),
        ]

    def test_download_timestamp_wins_over_scan_timestamp(self, db):
        db.record(
            "/music/discovery/01.flac",
            status="tagged",
            artist="Daft Punk",
            album="Discovery",
            title="One More Time",
        )
        db.record_download(
            track_id=1,
            name="One More Time",
            artist="Daft Punk",
            album="Discovery",
            status="done",
            finished_at=2000.0,
        )
        db.commit()

        rows, total = db.recent_albums_page(limit=12, offset=0)

        assert total == 1
        assert rows[0]["album"] == "Discovery"
        assert rows[0]["recent_source"] == "download"
        assert rows[0]["recent_at"] == 2000

    def test_scan_fallback_used_when_no_download_history_exists(self, db):
        db.record(
            "/music/parachutes/01.flac",
            status="tagged",
            artist="Coldplay",
            album="Parachutes",
            title="Yellow",
        )
        db.commit()

        rows, total = db.recent_albums_page(limit=12, offset=0)

        assert total == 1
        assert rows[0]["album"] == "Parachutes"
        assert rows[0]["recent_source"] == "scan"

    def test_same_album_from_download_and_scan_is_deduped(self, db):
        db.record(
            "/music/discovery/01.flac",
            status="tagged",
            artist="Daft Punk",
            album="Discovery",
            title="One More Time",
        )
        db.record(
            "/music/discovery/02.flac",
            status="tagged",
            artist="Daft Punk",
            album="Discovery",
            title="Aerodynamic",
        )
        db.record_download(
            track_id=1,
            name="One More Time",
            artist="Daft Punk",
            album="Discovery",
            status="done",
            finished_at=2000.0,
        )
        db.commit()

        rows, total = db.recent_albums_page(limit=12, offset=0)

        assert total == 1
        assert rows[0]["track_count"] == 2

    def test_download_only_album_not_in_scanned_is_excluded(self, db):
        db.record_download(
            track_id=1,
            name="Ghost Track",
            artist="Ghost Artist",
            album="Ghost Album",
            status="done",
            finished_at=2000.0,
        )
        db.commit()

        rows, total = db.recent_albums_page(limit=12, offset=0)

        assert rows == []
        assert total == 0


class TestQualityProbeCache:
    def test_get_probe_ignores_stale_probe_when_track_was_rescanned(self, db):
        db.record("/music/track.flac", status="tagged", isrc="US123", artist="A", title="Song")
        db.commit()
        db.set_probe("US123", 123, "HI_RES_LOSSLESS")
        db.commit()

        db._conn.execute("UPDATE scanned SET scanned_at = scanned_at + 60 WHERE isrc = ?", ("US123",))
        db.commit()

        assert db.get_probe("US123") is None
        assert db.get_probes_batch(["US123"]) == {}

    def test_get_probes_batch_keeps_fresh_probe_rows(self, db):
        db.record("/music/track.flac", status="tagged", isrc="US123", artist="A", title="Song")
        db.commit()
        db.set_probe("US123", 123, "HI_RES_LOSSLESS")
        db.commit()

        probe = db.get_probe("US123")
        batch = db.get_probes_batch(["US123"])

        assert probe is not None
        assert probe["tidal_track_id"] == 123
        assert batch["US123"]["max_quality"] == "HI_RES_LOSSLESS"


class TestMigration:
    def test_fresh_db_has_all_tables(self, db):
        tables = {r["name"] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        expected = {"scanned", "play_events", "artist_images", "playlist_covers",
                    "quality_probes", "library_meta", "download_history", "favorites"}
        assert expected.issubset(tables)

    def test_v1_to_v6_migration(self, tmp_path):
        """Create a v1-style DB, then open with LibraryDB to trigger migration."""
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE scanned (
            path TEXT PRIMARY KEY, isrc TEXT, status TEXT NOT NULL,
            artist TEXT, title TEXT, scanned_at INTEGER NOT NULL)""")
        conn.execute("INSERT INTO scanned VALUES ('/a.flac', 'US123', 'tagged', 'X', 'Y', 1000)")
        conn.commit()
        conn.close()

        db = LibraryDB(db_path)
        db.open()
        cols = {r["name"] for r in db._conn.execute("PRAGMA table_info(scanned)")}
        assert "album" in cols
        assert "duration" in cols
        assert "quality" in cols
        assert "format" in cols
        assert "play_count" in cols
        assert "genre" in cols
        assert "waveform" in cols
        assert "waveform_hires" in cols
        assert "art_available" in cols
        assert "codec" in cols
        assert "metadata_complete" in cols
        assert LibraryDB._SCHEMA_VERSION == 6
        row = db.get("/a.flac")
        assert row["artist"] == "X"
        assert row["art_available"] is None
        db.close()

    def test_backup_includes_committed_wal_rows(self, tmp_path):
        from tidal_dl.gui.api.library import _backup_library_db

        db_path = tmp_path / "library.db"
        db = LibraryDB(db_path)
        db.open()
        try:
            db.record("/music/a.flac", status="tagged", artist="A", title="Song")
            db.commit()

            backup_path = _backup_library_db(db_path)

            backup = sqlite3.connect(str(backup_path))
            try:
                row = backup.execute("SELECT artist FROM scanned WHERE path = ?", ("/music/a.flac",)).fetchone()
            finally:
                backup.close()
        finally:
            db.close()

        assert row == ("A",)
