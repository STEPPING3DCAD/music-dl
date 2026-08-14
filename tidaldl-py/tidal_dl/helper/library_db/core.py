"""Connection lifecycle and schema migrations."""

from tidal_dl.helper.library_db._common import *


class LibraryDBCore:
    """Thin wrapper around a SQLite scan ledger."""

    _SCHEMA_VERSION = 8

    def __init__(self, db_path: pathlib.Path) -> None:
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        try:
            self._open_existing_or_new()
        except sqlite3.DatabaseError as exc:
            if not _is_sqlite_corruption(exc):
                raise
            self.close()
            _quarantine_corrupt_db(self._path)
            self._open_existing_or_new()

    def _open_existing_or_new(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < self._SCHEMA_VERSION:
            self._migrate()
            self._conn.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
            self._conn.commit()

    def _migrate(self) -> None:
        assert self._conn
        # Check if table exists at all
        exists = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scanned'"
        ).fetchone()

        if not exists:
            self._conn.execute(
                """CREATE TABLE scanned (
                    path       TEXT PRIMARY KEY,
                    isrc       TEXT,
                    status     TEXT NOT NULL,
                    artist     TEXT,
                    title      TEXT,
                    album      TEXT,
                    album_artist TEXT,
                    release_date TEXT,
                    track_number INTEGER,
                    track_total INTEGER,
                    disc_number INTEGER,
                    disc_total INTEGER,
                    musicbrainz_release_id TEXT,
                    musicbrainz_release_group_id TEXT,
                    provider_namespace TEXT,
                    provider_album_id TEXT,
                    barcode TEXT,
                    duration   INTEGER,
                    quality    TEXT,
                    format     TEXT,
                    codec      TEXT,
                    metadata_complete INTEGER,
                    play_count INTEGER DEFAULT 0,
                    last_played INTEGER,
                    genre      TEXT,
                    waveform   TEXT,
                    waveform_hires TEXT,
                    art_available INTEGER,
                    scanned_at INTEGER NOT NULL
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scanned_status ON scanned(status)"
            )
        else:
            # Migrate v1 → v2: add missing columns
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(scanned)")}
            for col, coltype in [
                ("isrc", "TEXT"),
                ("artist", "TEXT"),
                ("title", "TEXT"),
                ("album", "TEXT"),
                ("duration", "INTEGER"),
                ("quality", "TEXT"),
                ("format", "TEXT"),
                ("scanned_at", "INTEGER DEFAULT 0"),
            ]:
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE scanned ADD COLUMN {col} {coltype}")

            # v2 → v3: play tracking + genre
            for col, coltype, default in [
                ("play_count", "INTEGER", "0"),
                ("last_played", "INTEGER", None),
                ("genre", "TEXT", None),
            ]:
                if col not in cols:
                    if default is not None:
                        self._conn.execute(
                            f"ALTER TABLE scanned ADD COLUMN {col} {coltype} DEFAULT {default}"
                        )
                    else:
                        self._conn.execute(
                            f"ALTER TABLE scanned ADD COLUMN {col} {coltype}"
                        )

            # v3 → v4: waveform peaks (JSON array of floats)
            if "waveform" not in cols:
                self._conn.execute("ALTER TABLE scanned ADD COLUMN waveform TEXT")
            if "waveform_hires" not in cols:
                self._conn.execute("ALTER TABLE scanned ADD COLUMN waveform_hires TEXT")

            # v4 -> v5: local embedded or sibling cover-art availability.
            # NULL preserves legacy rows until art is checked on demand.
            if "art_available" not in cols:
                self._conn.execute("ALTER TABLE scanned ADD COLUMN art_available INTEGER")

            # v5 -> v6: inspected codec and completed metadata resolution.
            if "codec" not in cols:
                self._conn.execute("ALTER TABLE scanned ADD COLUMN codec TEXT")
            if "metadata_complete" not in cols:
                self._conn.execute(
                    "ALTER TABLE scanned ADD COLUMN metadata_complete INTEGER"
                )

            # v6 -> v7: release identity fields used by album grouping.
            release_columns_added = False
            for col, coltype in [
                ("album_artist", "TEXT"),
                ("release_date", "TEXT"),
                ("track_number", "INTEGER"),
                ("track_total", "INTEGER"),
                ("disc_number", "INTEGER"),
                ("disc_total", "INTEGER"),
                ("musicbrainz_release_id", "TEXT"),
                ("musicbrainz_release_group_id", "TEXT"),
                ("provider_namespace", "TEXT"),
                ("provider_album_id", "TEXT"),
                ("barcode", "TEXT"),
            ]:
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE scanned ADD COLUMN {col} {coltype}")
                    release_columns_added = True
            if release_columns_added:
                self._conn.execute(
                    "UPDATE scanned SET metadata_complete = 0 WHERE status != 'unreadable'"
                )

        # Backfill codecs that are unambiguous from their native file type.
        self._conn.execute(
            """UPDATE scanned
               SET codec = CASE
                   WHEN lower(path) LIKE '%.flac' THEN 'flac'
                   WHEN lower(path) LIKE '%.mp3' THEN 'mp3'
                   WHEN lower(path) LIKE '%.aac' THEN 'aac'
                   WHEN lower(path) LIKE '%.ogg' THEN 'ogg'
                   WHEN lower(path) LIKE '%.wav' THEN 'pcm'
               END
               WHERE codec IS NULL
                 AND (lower(path) LIKE '%.flac'
                      OR lower(path) LIKE '%.mp3'
                      OR lower(path) LIKE '%.aac'
                      OR lower(path) LIKE '%.ogg'
                      OR lower(path) LIKE '%.wav')"""
        )
        self._conn.execute(
            """UPDATE scanned SET metadata_complete = 1
               WHERE metadata_complete IS NULL
                 AND NULLIF(TRIM(title), '') IS NOT NULL
                 AND NULLIF(TRIM(artist), '') IS NOT NULL
                 AND NULLIF(TRIM(album), '') IS NOT NULL
                 AND lower(TRIM(artist)) != 'unknown artist'
                 AND lower(TRIM(album)) != 'unknown album'
                 AND lower(TRIM(title)) NOT LIKE 'track %'"""
        )

        # play_events table (time-series for activity charts)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS play_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                path       TEXT,
                artist     TEXT,
                genre      TEXT,
                duration   INTEGER,
                played_at  INTEGER NOT NULL
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_play_events_at ON play_events(played_at)"
        )

        # artist_images cache (Tidal artist photos)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS artist_images (
                artist    TEXT PRIMARY KEY,
                image_url TEXT,
                fetched_at INTEGER
            )"""
        )

        # playlist_covers cache (Tidal playlist cover URLs)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS playlist_covers (
                playlist_id TEXT PRIMARY KEY,
                cover_url   TEXT,
                fetched_at  INTEGER
            )"""
        )

        # quality_probes cache (Tidal quality lookup results)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quality_probes (
                isrc           TEXT PRIMARY KEY,
                tidal_track_id INTEGER,
                max_quality    TEXT,
                probed_at      INTEGER
            )"""
        )

        # Index on scanned.isrc for upgrade lookups
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scanned_isrc ON scanned(isrc)"
        )

        # library_meta table (scan fingerprints, etc.)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS library_meta (key TEXT PRIMARY KEY, value TEXT)"
        )

        # download_history table
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS download_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id    INTEGER,
                name        TEXT,
                artist      TEXT,
                album       TEXT,
                status      TEXT NOT NULL,
                error       TEXT,
                started_at  REAL,
                finished_at REAL,
                cover_url   TEXT,
                quality     TEXT
            )"""
        )
        # Migrate: add cover_url and quality columns if missing
        try:
            self._conn.execute("SELECT cover_url FROM download_history LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE download_history ADD COLUMN cover_url TEXT")
        try:
            self._conn.execute("SELECT quality FROM download_history LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE download_history ADD COLUMN quality TEXT")

        # persisted download/upgrade job queue
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS download_jobs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                kind          TEXT NOT NULL,
                status        TEXT NOT NULL,
                track_id      INTEGER NOT NULL,
                name          TEXT,
                artist        TEXT,
                album         TEXT,
                cover_url     TEXT,
                quality       TEXT,
                progress      REAL DEFAULT 0,
                error         TEXT,
                old_path      TEXT,
                new_path      TEXT,
                metadata_json TEXT,
                created_at    REAL NOT NULL,
                started_at    REAL,
                finished_at   REAL
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_download_jobs_status_created ON download_jobs(status, created_at)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_download_jobs_track_id ON download_jobs(track_id)"
        )

        # favorites table
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS favorites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT,
                tidal_id    INTEGER,
                artist      TEXT,
                title       TEXT,
                album       TEXT,
                isrc        TEXT,
                cover_url   TEXT,
                favorited_at INTEGER NOT NULL,
                UNIQUE(path),
                UNIQUE(tidal_id)
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorites_at ON favorites(favorited_at)"
        )

        # Explainable album-release assessments and current user choices.
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS album_grouping_assessments (
                pair_key TEXT PRIMARY KEY,
                left_signature TEXT NOT NULL,
                right_signature TEXT NOT NULL,
                score INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                vetoes_json TEXT NOT NULL,
                contradictions_json TEXT NOT NULL,
                user_decision TEXT,
                canonical_title TEXT,
                catalog_json TEXT NOT NULL DEFAULT '{}',
                evaluated_at REAL NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_album_grouping_signatures
               ON album_grouping_assessments(left_signature, right_signature)"""
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
