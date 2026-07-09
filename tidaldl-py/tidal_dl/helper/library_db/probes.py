"""Tidal quality probe cache."""

from tidal_dl.helper.library_db._common import *  # noqa: F403

class ProbesMixin:
    def _latest_scanned_at_by_isrc(self, isrcs: list[str]) -> dict[str, int]:
        assert self._conn
        if not isrcs:
            return {}
        placeholders = ",".join("?" for _ in isrcs)
        rows = self._conn.execute(
            f"SELECT isrc, MAX(scanned_at) AS scanned_at FROM scanned WHERE isrc IN ({placeholders}) GROUP BY isrc",
            isrcs,
        ).fetchall()
        return {r["isrc"]: float(r["scanned_at"] or 0) for r in rows if r["isrc"]}

    def get_probe(self, isrc: str) -> dict | None:
        """Return cached Tidal quality probe for an ISRC, or None.

        Probes older than the latest scanned metadata for the same ISRC are
        treated as stale and ignored.
        """
        if not isrc:
            return None
        batch = self.get_probes_batch([isrc])
        return batch.get(isrc)

    def get_probes_batch(self, isrcs: list[str]) -> dict[str, dict]:
        """Return fresh cached probes for a list of ISRCs.

        Stale probes whose `probed_at` predates the latest `scanned_at` for the
        same ISRC are excluded so callers can re-probe them.
        """
        assert self._conn
        if not isrcs:
            return {}
        placeholders = ",".join("?" for _ in isrcs)
        rows = self._conn.execute(
            f"SELECT * FROM quality_probes WHERE isrc IN ({placeholders})", isrcs
        ).fetchall()
        latest_scanned = self._latest_scanned_at_by_isrc(isrcs)
        fresh: dict[str, dict] = {}
        for row in rows:
            data = dict(row)
            latest = latest_scanned.get(data["isrc"], 0)
            if latest and float(data.get("probed_at") or 0) < latest:
                continue
            fresh[data["isrc"]] = data
        return fresh

    def set_probe(
        self,
        isrc: str,
        tidal_track_id: int,
        max_quality: str,
        ) -> None:
        """Cache a Tidal quality probe result."""
        assert self._conn
        self._conn.execute(
            "INSERT OR REPLACE INTO quality_probes (isrc, tidal_track_id, max_quality, probed_at) VALUES (?, ?, ?, ?)",
            (isrc, tidal_track_id, max_quality, time.time()),
        )

    def upgradeable_tracks(self) -> list[dict]:
        """Return all local tracks with a non-empty ISRC.

        Tier filtering is done in Python since quality strings are heterogeneous.
        """
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM scanned WHERE isrc IS NOT NULL AND isrc != '' AND status != 'unreadable'"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_probe(self, isrc: str) -> None:
        """Remove a cached probe (for re-probing)."""
        assert self._conn
        self._conn.execute("DELETE FROM quality_probes WHERE isrc = ?", (isrc,))
