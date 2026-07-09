"""Download HTTP client and logger protocol."""

from typing import Any, Protocol

import requests

from tidal_dl.constants import REQUESTS_TIMEOUT_SEC

class RequestsClient:
    """HTTP client for downloading text content from a URI."""

    def download(
        self, uri: str, timeout: int = REQUESTS_TIMEOUT_SEC, headers: dict | None = None, verify_ssl: bool = True
    ) -> tuple[str, str]:
        """Download the content of a URI as text.

        Args:
            uri (str): The URI to download.
            timeout (int, optional): Timeout in seconds. Defaults to REQUESTS_TIMEOUT_SEC.
            headers (dict | None, optional): HTTP headers. Defaults to None.
            verify_ssl (bool, optional): Whether to verify SSL. Defaults to True.

        Returns:
            tuple[str, str]: Tuple of (text content, final URL).
        """
        if not headers:
            headers = {}

        o = requests.get(uri, timeout=timeout, headers=headers)
        o.raise_for_status()

        return o.text, o.url

class LoggerLike(Protocol):
    def debug(self, msg: object, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, msg: object, *args: Any, **kwargs: Any) -> None: ...
    def info(self, msg: object, *args: Any, **kwargs: Any) -> None: ...
    def error(self, msg: object, *args: Any, **kwargs: Any) -> None: ...
    def critical(self, msg: object, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, msg: object, *args: Any, **kwargs: Any) -> None: ...

