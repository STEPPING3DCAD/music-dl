"""Key-value library metadata."""

from tidal_dl.helper.library_db._common import *  # noqa: F403

class MetaMixin:
    def get_meta(self, key: str) -> str | None:
        """Read a value from the library_meta table."""
        assert self._conn
        row = self._conn.execute(
            "SELECT value FROM library_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """Write a value to the library_meta table."""
        assert self._conn
        self._conn.execute(
            "INSERT OR REPLACE INTO library_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
