"""Album and artist browsing queries."""

from tidal_dl.helper.library_db._common import *  # noqa: F403

class BrowseMixin:
    def artists_page(
        self,
        limit: int = 50,
        offset: int = 0,
        query: str = "",
        ) -> tuple[list[dict], int]:
        """Return paginated artists with track/album counts."""
        assert self._conn
        where = "status != 'unreadable' AND artist IS NOT NULL"
        params: list = []
        if query:
            where += " AND artist LIKE ?"
            params.append(f"%{query}%")

        total = self._conn.execute(
            f"SELECT COUNT(DISTINCT artist) FROM scanned WHERE {where}", params
        ).fetchone()[0]

        rows = self._conn.execute(
            f"""SELECT artist, COUNT(*) as track_count,
                       COUNT(DISTINCT album) as album_count,
                       MIN(path) as cover_path
                FROM scanned
                WHERE {where}
                GROUP BY artist
                ORDER BY artist COLLATE NOCASE ASC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total

    def all_albums(self, query: str = "") -> list[dict]:
        """Return all albums grouped by album name. Multi-artist albums show 'Various Artists'."""
        assert self._conn
        where = "album IS NOT NULL AND status != 'unreadable'"
        params: list = []
        if query:
            where += " AND (album LIKE ? OR artist LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like])
        rows = self._conn.execute(
            f"""SELECT album, COUNT(*) as track_count, MIN(path) as cover_path,
                       MAX(quality) as best_quality,
                       COUNT(DISTINCT artist) as artist_count,
                       MIN(artist) as first_artist
                FROM scanned
                WHERE {where}
                GROUP BY album
                ORDER BY album COLLATE NOCASE ASC""",
            params,
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["artist"] = d["first_artist"] if d["artist_count"] == 1 else "Various Artists"
            result.append(d)
        return result

    def recent_albums_page(self, limit: int = 12, offset: int = 0) -> tuple[list[dict], int]:
        """Return recent local albums, preferring download recency over scan recency.

        Albums are grouped by name only (not by artist) so compilations and
        greatest-hits collections appear as a single entry with the artist
        shown as "Various Artists" when multiple artists are present.
        """
        assert self._conn

        # Downloads: group by album name only — collapse multi-artist compilations
        downloaded: dict[str, dict] = {}
        for row in self._conn.execute(
            """SELECT dh.album,
                      COUNT(DISTINCT s.path) AS track_count,
                      MIN(s.path) AS cover_path,
                      MAX(dh.finished_at) AS recent_at,
                      COUNT(DISTINCT dh.artist) AS artist_count,
                      MIN(dh.artist) AS first_artist
               FROM download_history dh
               JOIN scanned s
                 ON s.album = dh.album
               WHERE dh.status = 'done'
                 AND dh.finished_at IS NOT NULL
                 AND s.status != 'unreadable'
                 AND dh.album IS NOT NULL
               GROUP BY dh.album"""
        ).fetchall():
            artist = row["first_artist"] if row["artist_count"] == 1 else "Various Artists"
            downloaded[row["album"]] = {
                "album": row["album"],
                "artist": artist,
                "track_count": row["track_count"],
                "cover_path": row["cover_path"],
                "recent_at": int(row["recent_at"]),
                "recent_source": "download",
            }

        # Scanned: group by album name only
        scanned: dict[str, dict] = {}
        for row in self._conn.execute(
            """SELECT album,
                      COUNT(*) AS track_count,
                      MIN(path) AS cover_path,
                      MAX(scanned_at) AS recent_at,
                      COUNT(DISTINCT artist) AS artist_count,
                      MIN(artist) AS first_artist
               FROM scanned
               WHERE album IS NOT NULL
                 AND status != 'unreadable'
               GROUP BY album"""
        ).fetchall():
            artist = row["first_artist"] if row["artist_count"] == 1 else "Various Artists"
            scanned[row["album"]] = {
                "album": row["album"],
                "artist": artist,
                "track_count": row["track_count"],
                "cover_path": row["cover_path"],
                "recent_at": int(row["recent_at"]),
                "recent_source": "scan",
            }

        # Download recency wins over scan recency
        merged = dict(scanned)
        merged.update(downloaded)

        rows = sorted(
            merged.values(),
            key=lambda row: (-row["recent_at"], row["artist"].casefold(), row["album"].casefold()),
        )
        total = len(rows)
        return rows[offset:offset + limit], total

    def albums_by_artist(self, artist: str) -> list[dict]:
        """Return albums for an artist with track count and a representative path for art."""
        assert self._conn
        rows = self._conn.execute(
            """SELECT album, COUNT(*) as track_count, MIN(path) as cover_path,
                      GROUP_CONCAT(DISTINCT genre) as genres,
                      MAX(quality) as best_quality
               FROM scanned
               WHERE artist = ? AND album IS NOT NULL AND status != 'unreadable'
               GROUP BY album ORDER BY album COLLATE NOCASE ASC""",
            (artist,),
        ).fetchall()
        return [dict(r) for r in rows]

    def album_tracks(self, artist: str, album: str) -> list[dict]:
        """Return album tracks deduplicated by normalized title+artist.

        Prefers the best-quality row for each song, then a canonical path without
        a uniquify suffix like ``_01``, then the shortest path.
        """
        assert self._conn
        if artist == "Various Artists":
            rows = self._conn.execute(
                """SELECT * FROM scanned
                   WHERE album = ? AND status != 'unreadable'""",
                (album,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM scanned
                   WHERE artist = ? AND album = ? AND status != 'unreadable'""",
                (artist, album),
            ).fetchall()

        ordered = sorted((dict(r) for r in rows), key=_album_track_preference)
        seen: set[tuple[str, str]] = set()
        result = []
        for row in ordered:
            key = _album_track_key(row)
            if key in seen:
                continue
            seen.add(key)
            result.append(row)

        result.sort(key=lambda t: t.get("path", ""))
        return result
