"""Album and artist browsing queries."""

from tidal_dl.helper.library_db._common import *  # noqa: F403

class BrowseMixin:
    def artists_page(
        self,
        limit: int = 50,
        offset: int = 0,
        query: str = "",
        ) -> tuple[list[dict], int]:
        """Return paginated artists with canonical track and album counts."""
        needle = query.casefold()
        grouped: dict[str, list[dict]] = {}
        for row in self.canonical_tracks():
            artist = row.get("artist")
            if not artist or (needle and needle not in artist.casefold()):
                continue
            grouped.setdefault(artist, []).append(row)

        result = []
        for artist, tracks in grouped.items():
            cover = min(tracks, key=lambda row: row.get("path") or "")
            result.append({
                "artist": artist,
                "track_count": len(tracks),
                "album_count": len({row.get("album") for row in tracks if row.get("album")}),
                "cover_path": cover.get("path"),
                "cover_art_available": cover.get("art_available"),
            })
        result.sort(key=lambda row: row["artist"].casefold())
        total = len(result)
        return result[offset:offset + limit], total

    def all_albums(self, query: str = "") -> list[dict]:
        """Return albums built from canonical tracks."""
        needle = query.casefold()
        grouped: dict[str, list[dict]] = {}
        for row in self.canonical_tracks():
            album = row.get("album")
            artist = row.get("artist") or ""
            if not album or (needle and needle not in album.casefold() and needle not in artist.casefold()):
                continue
            grouped.setdefault(album, []).append(row)

        result = []
        for album, tracks in grouped.items():
            artists = {row.get("artist") for row in tracks if row.get("artist")}
            cover = min(tracks, key=lambda row: row.get("path") or "")
            best = min(tracks, key=_canonical_track_preference)
            result.append({
                "album": album,
                "track_count": len(tracks),
                "cover_path": cover.get("path"),
                "cover_art_available": cover.get("art_available"),
                "best_quality": best.get("quality"),
                "artist_count": len(artists),
                "first_artist": min(artists) if artists else None,
                "artist": next(iter(artists)) if len(artists) == 1 else "Various Artists",
            })
        result.sort(key=lambda row: row["album"].casefold())
        return result

    def recent_albums_page(self, limit: int = 12, offset: int = 0) -> tuple[list[dict], int]:
        """Return recent local albums, preferring download recency over scan recency.

        Albums are grouped by name only (not by artist) so compilations and
        greatest-hits collections appear as a single entry with the artist
        shown as "Various Artists" when multiple artists are present.
        """
        assert self._conn
        albums = {row["album"]: row for row in self.all_albums()}
        canonical = self.canonical_tracks()
        download_times = {
            row["album"]: row["recent_at"]
            for row in self._conn.execute(
                """SELECT album, MAX(finished_at) AS recent_at
                   FROM download_history
                   WHERE status = 'done' AND finished_at IS NOT NULL AND album IS NOT NULL
                   GROUP BY album"""
            ).fetchall()
        }
        rows = []
        for album, summary in albums.items():
            scan_time = max(
                (row.get("scanned_at") or 0 for row in canonical if row.get("album") == album),
                default=0,
            )
            download_time = download_times.get(album)
            summary = dict(summary)
            summary["recent_at"] = int(download_time if download_time is not None else scan_time)
            summary["recent_source"] = "download" if download_time is not None else "scan"
            rows.append(summary)

        rows.sort(
            key=lambda row: (-row["recent_at"], row["artist"].casefold(), row["album"].casefold()),
        )
        total = len(rows)
        return rows[offset:offset + limit], total

    def albums_by_artist(self, artist: str) -> list[dict]:
        """Return albums for an artist with track count and a representative path for art."""
        grouped: dict[str, list[dict]] = {}
        for row in self.canonical_tracks():
            if row.get("artist") == artist and row.get("album"):
                grouped.setdefault(row["album"], []).append(row)
        result = []
        for album, tracks in grouped.items():
            cover = min(tracks, key=lambda row: row.get("path") or "")
            best = min(tracks, key=_canonical_track_preference)
            genres = sorted({row.get("genre") for row in tracks if row.get("genre")})
            result.append({
                "album": album,
                "track_count": len(tracks),
                "cover_path": cover.get("path"),
                "cover_art_available": cover.get("art_available"),
                "genres": ",".join(genres),
                "best_quality": best.get("quality"),
            })
        result.sort(key=lambda row: row["album"].casefold())
        return result

    def album_tracks(self, artist: str, album: str) -> list[dict]:
        """Return album tracks deduplicated by normalized title+artist.

        Prefers the best-quality row for each song, then a canonical path without
        a uniquify suffix like ``_01``, then the shortest path.
        """
        rows = [
            row for row in self.canonical_tracks()
            if row.get("album") == album
            and (artist == "Various Artists" or row.get("artist") == artist)
        ]
        result = _canonicalize_tracks(rows)
        result.sort(key=lambda t: t.get("path", ""))
        return result
