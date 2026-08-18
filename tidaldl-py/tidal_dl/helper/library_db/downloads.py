"""Download history and job queue."""

from tidal_dl.helper.library_db._common import *


class DownloadsMixin:
    def record_download(
        self,
        *,
        track_id: int,
        name: str,
        artist: str | None = None,
        album: str | None = None,
        status: str,
        error: str | None = None,
        started_at: float | None = None,
        finished_at: float | None = None,
        cover_url: str | None = None,
        quality: str | None = None,
        ) -> None:
        """Record a download completion (success or failure)."""
        assert self._conn
        self._conn.execute(
            """INSERT INTO download_history (track_id, name, artist, album, status, error, started_at, finished_at, cover_url, quality)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_id, name, artist, album, status, error, started_at, finished_at, cover_url, quality),
        )

    def download_history(self, limit: int = 50) -> list[dict]:
        """Return recent download history."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM download_history ORDER BY finished_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_download_history(self, status: str | None = None) -> int:
        """Delete download history entries. If status is given, only delete that status."""
        assert self._conn
        if status:
            cur = self._conn.execute("DELETE FROM download_history WHERE status = ?", (status,))
        else:
            cur = self._conn.execute("DELETE FROM download_history")
        self._conn.commit()
        return cur.rowcount

    def create_download_job_if_not_active(
        self,
        *,
        kind: str,
        track_id: int,
        name: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        cover_url: str | None = None,
        quality: str | None = None,
        old_path: str | None = None,
        metadata_json: str | None = None,
        ) -> int | None:
        """Create a queued job unless the track already has active work."""
        assert self._conn
        now = time.time()
        with self.write_transaction(immediate=True):
            active = self._conn.execute(
                """SELECT 1 FROM download_jobs
                   WHERE track_id = ?
                     AND status IN ('queued', 'running', 'indexing', 'retrying', 'paused')
                   LIMIT 1""",
                (track_id,),
            ).fetchone()
            if active:
                return None

            cur = self._conn.execute(
                """INSERT INTO download_jobs
                   (kind, status, track_id, name, artist, album, cover_url,
                    quality, old_path, metadata_json, created_at)
                   VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    kind,
                    track_id,
                    name,
                    artist,
                    album,
                    cover_url,
                    quality,
                    old_path,
                    metadata_json,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def get_download_job(self, job_id: int | None) -> dict | None:
        """Return a download job by ID."""
        if job_id is None:
            return None
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_download_job(self, job_id: int, **fields) -> None:
        """Update allowed fields on one download job."""
        assert self._conn
        if not fields:
            return
        unknown = set(fields) - DOWNLOAD_JOB_FIELDS
        if unknown:
            raise ValueError(f"Unknown download job fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.write_transaction():
            self._conn.execute(
                f"UPDATE download_jobs SET {assignments} WHERE id = ?",
                (*fields.values(), job_id),
            )

    def claim_next_download_job(self, *, kind: str | None = None) -> dict | None:
        """Atomically claim the oldest queued job."""
        assert self._conn
        now = time.time()
        where = "status = 'queued'"
        params: list = []
        if kind is not None:
            where += " AND kind = ?"
            params.append(kind)
        with self.write_transaction(immediate=True):
            row = self._conn.execute(
                f"""SELECT id FROM download_jobs
                   WHERE {where}
                   ORDER BY created_at, id
                   LIMIT 1""",
                params,
            ).fetchone()
            if not row:
                return None

            job_id = row["id"]
            cur = self._conn.execute(
                """UPDATE download_jobs
                   SET status = 'running', started_at = COALESCE(started_at, ?)
                   WHERE id = ? AND status = 'queued'""",
                (now, job_id),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                return None

            claimed = self._conn.execute(
                "SELECT * FROM download_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return dict(claimed) if claimed else None

    def recover_download_jobs(self) -> int:
        """Mark jobs that were active during shutdown as interrupted."""
        assert self._conn
        now = time.time()
        cur = self._conn.execute(
            """UPDATE download_jobs
               SET status = 'interrupted', finished_at = COALESCE(finished_at, ?)
               WHERE status IN ('running', 'indexing', 'retrying', 'paused')""",
            (now,),
        )
        self._conn.commit()
        return int(cur.rowcount)

    def has_active_download_job(self, track_id: int) -> bool:
        """Return True if a track has active queued/running work."""
        assert self._conn
        row = self._conn.execute(
            """SELECT 1 FROM download_jobs
               WHERE track_id = ?
                 AND status IN ('queued', 'running', 'indexing', 'retrying', 'paused')
               LIMIT 1""",
            (track_id,),
        ).fetchone()
        return row is not None

    def active_download_job_count(self) -> int:
        """Return count of queued or in-progress jobs."""
        assert self._conn
        row = self._conn.execute(
            """SELECT COUNT(*) FROM download_jobs
               WHERE status IN ('queued', 'running', 'indexing', 'retrying', 'paused')"""
        ).fetchone()
        return int(row[0])

    def cancel_queued_download_jobs(self, track_ids: list[int]) -> int:
        """Cancel queued jobs for specific track IDs."""
        assert self._conn
        if not track_ids:
            return 0
        placeholders = ",".join("?" for _ in track_ids)
        with self.write_transaction(immediate=True):
            cur = self._conn.execute(
                f"""UPDATE download_jobs
                    SET status = 'cancelled', finished_at = ?
                    WHERE status = 'queued' AND track_id IN ({placeholders})""",
                (time.time(), *track_ids),
            )
            return int(cur.rowcount)

    def cancel_all_queued_download_jobs(self) -> int:
        """Cancel every unfinished job so the Active list can go empty."""
        assert self._conn
        with self.write_transaction(immediate=True):
            cur = self._conn.execute(
                """UPDATE download_jobs
                   SET status = 'cancelled', finished_at = ?
                   WHERE status IN ('queued', 'running', 'indexing', 'retrying', 'paused')""",
                (time.time(),),
            )
            return int(cur.rowcount)

    def download_jobs_snapshot(self) -> dict:
        """Return current running jobs and queued count for API snapshots."""
        assert self._conn
        rows = self._conn.execute(
            """SELECT * FROM download_jobs
               WHERE status IN ('running', 'indexing', 'retrying', 'paused')
               ORDER BY created_at, id"""
        ).fetchall()
        queued = self._conn.execute(
            "SELECT COUNT(*) FROM download_jobs WHERE status = 'queued'"
        ).fetchone()[0]
        return {
            "active": [dict(row) for row in rows],
            "queued_count": int(queued),
        }
