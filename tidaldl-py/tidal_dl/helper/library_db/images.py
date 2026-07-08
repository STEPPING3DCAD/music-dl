"""Artist image and playlist cover cache."""

from tidal_dl.helper.library_db._common import *  # noqa: F403

class ImagesMixin:
    def get_artist_image(self, artist: str) -> str | None:
        """Return cached artist image URL, or None if not cached."""
        assert self._conn
        row = self._conn.execute(
            "SELECT image_url FROM artist_images WHERE artist = ?", (artist,)
        ).fetchone()
        return row[0] if row else None

    def set_artist_image(self, artist: str, image_url: str | None) -> None:
        """Cache an artist image URL (empty string = confirmed miss)."""
        assert self._conn
        self._conn.execute(
            "INSERT OR REPLACE INTO artist_images (artist, image_url, fetched_at) VALUES (?, ?, ?)",
            (artist, image_url, int(time.time())),
        )

    def get_playlist_cover(self, playlist_id: str) -> str | None:
        """Return cached playlist cover URL, or None if not cached."""
        assert self._conn
        row = self._conn.execute(
            "SELECT cover_url FROM playlist_covers WHERE playlist_id = ?", (playlist_id,)
        ).fetchone()
        return row[0] if row else None

    def set_playlist_cover(self, playlist_id: str, url: str) -> None:
        """Cache a playlist cover URL."""
        assert self._conn
        self._conn.execute(
            "INSERT OR REPLACE INTO playlist_covers (playlist_id, cover_url, fetched_at) VALUES (?, ?, ?)",
            (playlist_id, url, int(time.time())),
        )
