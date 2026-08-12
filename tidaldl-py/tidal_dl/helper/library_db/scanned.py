"""Scanned-track ledger CRUD, ISRC helpers, and album assessments."""

import hashlib
import json

from tidal_dl.helper.library_db._common import *


class ScannedMixin:
    @staticmethod
    def grouping_pair_key(left_signature: str, right_signature: str) -> str:
        payload = json.dumps(
            sorted((left_signature, right_signature)),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save_grouping_assessment(
        self,
        *,
        left_signature: str,
        right_signature: str,
        score: int,
        outcome: str,
        evidence: list[dict],
        vetoes: list[dict],
        contradictions: list[str],
        catalog: dict | None = None,
    ) -> None:
        assert self._conn
        left_signature, right_signature = sorted((left_signature, right_signature))
        pair_key = self.grouping_pair_key(left_signature, right_signature)
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._conn.execute(
            """INSERT INTO album_grouping_assessments (
                   pair_key, left_signature, right_signature, score, outcome,
                   evidence_json, vetoes_json, contradictions_json, catalog_json,
                   evaluated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(pair_key) DO UPDATE SET
                   left_signature = excluded.left_signature,
                   right_signature = excluded.right_signature,
                   score = excluded.score,
                   outcome = excluded.outcome,
                   evidence_json = excluded.evidence_json,
                   vetoes_json = excluded.vetoes_json,
                   contradictions_json = excluded.contradictions_json,
                   catalog_json = CASE
                       WHEN excluded.catalog_json = '{}' THEN album_grouping_assessments.catalog_json
                       ELSE excluded.catalog_json
                   END,
                   evaluated_at = excluded.evaluated_at""",
            (
                pair_key, left_signature, right_signature, int(score), outcome,
                encode(evidence), encode(vetoes), encode(contradictions),
                encode(catalog or {}), time.time(),
            ),
        )

    def get_grouping_assessment(self, left_signature: str, right_signature: str) -> dict | None:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM album_grouping_assessments WHERE pair_key = ?",
            (self.grouping_pair_key(left_signature, right_signature),),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        for stored, exposed in (
            ("evidence_json", "evidence"),
            ("vetoes_json", "vetoes"),
            ("contradictions_json", "contradictions"),
            ("catalog_json", "catalog"),
        ):
            result[exposed] = json.loads(result.pop(stored))
        return result

    def set_grouping_decision(
        self,
        left_signature: str,
        right_signature: str,
        *,
        decision: str,
        canonical_title: str | None = None,
    ) -> bool:
        if decision not in {"group_together", "keep_separate"}:
            raise ValueError("Invalid grouping decision")
        assert self._conn
        cursor = self._conn.execute(
            """UPDATE album_grouping_assessments
               SET user_decision = ?, canonical_title = ?
               WHERE pair_key = ?""",
            (
                decision,
                canonical_title if decision == "group_together" else None,
                self.grouping_pair_key(left_signature, right_signature),
            ),
        )
        return cursor.rowcount == 1

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
        """Return paths that have full metadata (album, duration, quality populated)."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT path FROM scanned WHERE album IS NOT NULL AND duration IS NOT NULL"
        ).fetchall()
        return {r["path"] for r in rows}

    def metadata_repair_worklist(self) -> list[dict]:
        """Return cached rows that need one audio metadata inspection."""
        assert self._conn
        rows = self._conn.execute(
            """SELECT * FROM scanned
               WHERE COALESCE(metadata_complete, 0) != 1 OR codec IS NULL
               ORDER BY path ASC"""
        ).fetchall()
        return [dict(row) for row in rows]

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

    def tracks_page(
        self,
        sort: str = "artist",
        limit: int = 50,
        offset: int = 0,
        query: str = "",
        ) -> tuple[list[dict], int]:
        """Return a page of tracks + total count.  Sorting is done in SQL."""
        assert self._conn
        sort_map = {
            "artist": "artist COLLATE NOCASE ASC",
            "album": "album COLLATE NOCASE ASC",
            "title": "title COLLATE NOCASE ASC",
            "recent": "scanned_at DESC",
            "plays": "play_count DESC, last_played DESC",
            "random": "RANDOM()",
        }
        order = sort_map.get(sort, sort_map["artist"])

        where = "status != 'unreadable'"
        params: list = []
        if query:
            where += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like, like])

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM scanned WHERE {where}", params
        ).fetchone()[0]

        rows = self._conn.execute(
            f"SELECT * FROM scanned WHERE {where} "
            f"ORDER BY {order} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total

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
        album_artist: str | None = None,
        release_date: str | None = None,
        track_number: int | None = None,
        track_total: int | None = None,
        disc_number: int | None = None,
        disc_total: int | None = None,
        musicbrainz_release_id: str | None = None,
        musicbrainz_release_group_id: str | None = None,
        provider_namespace: str | None = None,
        provider_album_id: str | None = None,
        barcode: str | None = None,
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
                                    album_artist, release_date, track_number,
                                    track_total, disc_number, disc_total,
                                    musicbrainz_release_id,
                                    musicbrainz_release_group_id,
                                    provider_namespace, provider_album_id, barcode,
                                    duration, quality, format, genre, waveform,
                                    waveform_hires, art_available, codec,
                                    metadata_complete, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                   isrc = excluded.isrc,
                   status = excluded.status,
                   artist = excluded.artist,
                   title = excluded.title,
                   album = excluded.album,
                   album_artist = excluded.album_artist,
                   release_date = excluded.release_date,
                   track_number = excluded.track_number,
                   track_total = excluded.track_total,
                   disc_number = excluded.disc_number,
                   disc_total = excluded.disc_total,
                   musicbrainz_release_id = excluded.musicbrainz_release_id,
                   musicbrainz_release_group_id = excluded.musicbrainz_release_group_id,
                   provider_namespace = excluded.provider_namespace,
                   provider_album_id = excluded.provider_album_id,
                   barcode = excluded.barcode,
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
                path, isrc, status, artist, title, album, album_artist,
                release_date, track_number, track_total, disc_number, disc_total,
                musicbrainz_release_id, musicbrainz_release_group_id,
                provider_namespace, provider_album_id, barcode, duration, quality,
                fmt, genre, waveform, waveform_hires, art_available, codec,
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
