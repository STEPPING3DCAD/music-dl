"""Scanned-track ledger CRUD and ISRC helpers."""

from tidal_dl.helper.library_db._common import *  # noqa: F403

class ScannedMixin:
    def is_known(self, path: str) -> bool:
        """Return True if *path* has already been scanned."""
        assert self._conn
        row = self._conn.execute(
            "SELECT 1 FROM scanned WHERE path = ?", (path,)
        ).fetchone()
        return row is not None

    def known_paths(self) -> set[str]:
        """Return the set of all scanned paths (for bulk skip checks)."""
        assert self._conn
        rows = self._conn.execute("SELECT path FROM scanned").fetchall()
        return {r["path"] for r in rows}

    def complete_paths(self) -> set[str]:
        """Return paths with complete core metadata and duration."""
        assert self._conn
        rows = self._conn.execute(
            """SELECT path FROM scanned
               WHERE NULLIF(TRIM(artist), '') IS NOT NULL
                 AND NULLIF(TRIM(title), '') IS NOT NULL
                 AND NULLIF(TRIM(album), '') IS NOT NULL
                 AND duration IS NOT NULL"""
        ).fetchall()
        return {r["path"] for r in rows}

    def get(self, path: str) -> dict | None:
        """Return full cached metadata for a single path, or None."""
        assert self._conn
        row = self._conn.execute("SELECT * FROM scanned WHERE path = ?", (path,)).fetchone()
        if not row:
            return None
        return dict(row)

    def tracks_by_isrc(self, isrc: str) -> list[dict]:
        """Return all scanned rows for one ISRC."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM scanned WHERE isrc = ? AND status != 'unreadable' ORDER BY path ASC",
            (isrc,),
        ).fetchall()
        return [dict(r) for r in rows]

    def has_live_isrc(self, isrc: str) -> bool:
        if not isrc:
            return False
        for row in self.tracks_by_isrc(isrc):
            if pathlib.Path(row["path"]).is_file():
                return True
        return False

    def primary_path_for_isrc(self, isrc: str) -> str | None:
        if not isrc:
            return None
        fallback: str | None = None
        for row in self.tracks_by_isrc(isrc):
            path = row["path"]
            fallback = fallback or path
            if pathlib.Path(path).is_file():
                return path
        return fallback

    def register_isrc_path(self, isrc: str, path: str | pathlib.Path, *, commit: bool = False) -> None:
        if not isrc or not path:
            return
        path_str = str(pathlib.Path(path).resolve())
        self.record(path=path_str, status="downloaded", isrc=isrc)
        if commit:
            self.commit()

    def isrc_entry_count(self) -> int:
        assert self._conn
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT isrc) FROM scanned WHERE isrc IS NOT NULL AND isrc != ''"
        ).fetchone()
        return int(row[0] if row else 0)

    def import_legacy_isrc_index(self, json_path: pathlib.Path) -> int:
        """One-time import from legacy isrc_index.json. Returns rows imported."""
        import json

        if not json_path.is_file():
            return 0
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        if not isinstance(payload, dict):
            return 0
        imported = 0
        for isrc, path_str in payload.items():
            if not isrc or not path_str:
                continue
            if not pathlib.Path(path_str).is_file():
                continue
            self.register_isrc_path(str(isrc), path_str)
            imported += 1
        if imported:
            self.commit()
            try:
                json_path.rename(json_path.with_suffix(".json.migrated"))
            except OSError:
                pass
        return imported

    def all_tracks(self) -> list[dict]:
        """Return all cached tracks with status != 'unreadable'."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM scanned WHERE status != 'unreadable'"
        ).fetchall()
        return [dict(r) for r in rows]

    def canonical_tracks(self) -> list[dict]:
        """Return one preferred active row per logical track."""
        rows = [row for row in self.all_tracks() if not _is_excluded_library_path(row)]
        return _canonicalize_tracks(rows)

    def metadata_repair_worklist(self, *, rescan: bool = False) -> list[dict]:
        """Return rows needing file inspection, without holding a read cursor open."""
        assert self._conn
        where = "1 = 1" if rescan else (
            "metadata_complete IS NULL OR codec IS NULL OR status = 'unreadable'"
        )
        rows = self._conn.execute(
            f"SELECT * FROM scanned WHERE {where} ORDER BY path ASC"
        ).fetchall()
        return [dict(row) for row in rows if not _is_excluded_library_path(dict(row))]

    def prune_excluded_rows(self) -> int:
        """Remove excluded scanned rows after preserving favorites and play history."""
        assert self._conn
        all_rows = [dict(row) for row in self._conn.execute("SELECT * FROM scanned")]
        excluded = [row for row in all_rows if _is_excluded_library_path(row)]
        active = [
            row for row in all_rows
            if row.get("status") != "unreadable" and not _is_excluded_library_path(row)
        ]
        by_identity: dict[tuple, list[dict]] = {}
        for row in active:
            by_identity.setdefault(_canonical_track_identity(row), []).append(row)

        for row in excluded:
            path = row["path"]
            candidates = by_identity.get(_canonical_track_identity(row), [])
            replacement = (
                min(candidates, key=_canonical_track_preference)["path"]
                if candidates else None
            )
            favorite = self._conn.execute(
                "SELECT id FROM favorites WHERE path = ?", (path,)
            ).fetchone()
            if favorite:
                if replacement and self._conn.execute(
                    "SELECT 1 FROM favorites WHERE path = ?", (replacement,)
                ).fetchone():
                    self._conn.execute("DELETE FROM favorites WHERE id = ?", (favorite["id"],))
                else:
                    self._conn.execute(
                        "UPDATE favorites SET path = ? WHERE id = ?",
                        (replacement, favorite["id"]),
                    )
            if replacement:
                self._conn.execute(
                    "UPDATE play_events SET path = ? WHERE path = ?",
                    (replacement, path),
                )
            self._conn.execute("DELETE FROM scanned WHERE path = ?", (path,))
        return len(excluded)

    def tracks_page(
        self,
        sort: str = "artist",
        limit: int = 50,
        offset: int = 0,
        query: str = "",
        ) -> tuple[list[dict], int]:
        """Return a canonical page of tracks and its logical total."""
        rows = self.canonical_tracks()
        if query:
            needle = query.casefold()
            rows = [
                row
                for row in rows
                if any(
                    needle in str(row.get(field) or "").casefold()
                    for field in ("title", "artist", "album")
                )
            ]

        def text(field: str):
            return lambda row: (
                str(row.get(field) or "").casefold(), row.get("path") or ""
            )

        if sort == "random":
            import random

            random.shuffle(rows)
        elif sort == "recent":
            rows.sort(
                key=lambda row: (-(row.get("scanned_at") or 0), row.get("path") or "")
            )
        elif sort == "plays":
            rows.sort(
                key=lambda row: (
                    -(row.get("play_count") or 0),
                    -(row.get("last_played") or 0),
                    row.get("path") or "",
                )
            )
        else:
            rows.sort(key=text(sort if sort in {"artist", "album", "title"} else "artist"))

        total = len(rows)
        return rows[offset:offset + limit], total

    def untagged(self, *, limit: int = 0) -> list[tuple[str, str, str]]:
        """Return (path, artist, title) for files needing ISRC lookup."""
        assert self._conn
        query = "SELECT path, artist, title FROM scanned WHERE status = 'needs_isrc'"
        if limit > 0:
            query += f" LIMIT {limit}"
        rows = self._conn.execute(query).fetchall()
        return [(r["path"], r["artist"], r["title"]) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        """Return {status: count} summary."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM scanned GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    def record(
        self,
        path: str,
        *,
        status: str,
        isrc: str | None = None,
        artist: str | None = None,
        title: str | None = None,
        album: str | None = None,
        duration: int | None = None,
        quality: str | None = None,
        fmt: str | None = None,
        genre: str | None = None,
        waveform: str | None = None,
        waveform_hires: str | None = None,
        art_available: bool | None = None,
        codec: str | None = None,
        metadata_complete: bool | None = None,
        ) -> None:
        """Insert or update a scan result."""
        assert self._conn
        now = time.time()
        self._conn.execute(
            """INSERT INTO scanned (path, isrc, status, artist, title, album,
                                    duration, quality, format, genre, waveform,
                                    waveform_hires, art_available, codec,
                                    metadata_complete, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                   isrc = excluded.isrc,
                   status = excluded.status,
                   artist = excluded.artist,
                   title = excluded.title,
                   album = excluded.album,
                   duration = excluded.duration,
                   quality = excluded.quality,
                   format = excluded.format,
                   genre = excluded.genre,
                   waveform = COALESCE(excluded.waveform, scanned.waveform),
                   waveform_hires = COALESCE(excluded.waveform_hires, scanned.waveform_hires),
                   art_available = COALESCE(excluded.art_available, scanned.art_available),
                   codec = COALESCE(excluded.codec, scanned.codec),
                   metadata_complete = COALESCE(
                       excluded.metadata_complete, scanned.metadata_complete
                   ),
                   scanned_at = excluded.scanned_at""",
            (
                path, isrc, status, artist, title, album, duration, quality, fmt,
                genre, waveform, waveform_hires, art_available, codec,
                metadata_complete, now,
            ),
        )

    def remove(self, path: str) -> None:
        """Remove a path from the ledger (e.g. file deleted)."""
        assert self._conn
        self._conn.execute("DELETE FROM scanned WHERE path = ?", (path,))

    def commit(self) -> None:
        assert self._conn
        self._conn.commit()
