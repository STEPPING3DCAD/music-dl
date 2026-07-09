"""Shared imports for the download package mixins."""

from __future__ import annotations

import os
import pathlib
import random
import re
import shutil
import sys
import tempfile
import time
from concurrent import futures
from threading import Event, Lock
from typing import Any, cast
from uuid import uuid4

import m3u8
import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import HTTPError
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.table import Table
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.exceptions import TooManyRequests
from tidalapi.media import (
    AudioExtensions,
    AudioMode,
    Codec,
    Quality,
    Stream,
    StreamManifest,
    Track,
    Video,
    VideoExtensions,
)
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist
from tidalapi.session import Session

from tidal_dl.config import Settings, Tidal
from tidal_dl.constants import (
    CHUNK_SIZE,
    COVER_NAME,
    EXTENSION_LYRICS,
    HIFI_QUALITY_MAP,
    METADATA_EXPLICIT,
    METADATA_LOOKUP_UPC,
    PLAYLIST_EXTENSION,
    PLAYLIST_PREFIX,
    QUALITY_RANK,
    REQUESTS_TIMEOUT_SEC,
    AudioExtensionsValid,
    CoverDimensions,
    DownloadSource,
    MediaType,
    MetadataTargetUPC,
    QualityVideo,
    quality_name,
)
from tidal_dl.helper.cache import TTLCache
from tidal_dl.helper.camelot import format_initial_key
from tidal_dl.helper.checkpoint import STATUS_DOWNLOADED, STATUS_FAILED, DownloadCheckpoint
from tidal_dl.helper.decryption import decrypt_file, decrypt_security_token
from tidal_dl.helper.exceptions import MediaMissing
from tidal_dl.helper.library_db import LibraryDB
from tidal_dl.helper.path import (
    _sanitize_name,
    check_file_exists,
    format_path_media,
    path_config_base,
    path_file_sanitize,
    url_to_filename,
    win_long_path,
)
from tidal_dl.helper.tidal import (
    instantiate_media,
    items_results_all,
    name_builder_album_artist,
    name_builder_artist,
    name_builder_item,
    name_builder_title,
)
from tidal_dl.metadata import Metadata
from tidal_dl.model.downloader import (
    DownloadOutcome,
    DownloadSegmentResult,
    DownloadSummary,
    HiFiStreamManifest,
    TrackStreamInfo,
)
from tidal_dl.download.types import LoggerLike

__all__ = [
    "Album",
    "Artist",
    "AudioExtensions",
    "AudioExtensionsValid",
    "AudioMode",
    "CHUNK_SIZE",
    "COVER_NAME",
    "Codec",
    "Console",
    "CoverDimensions",
    "DownloadCheckpoint",
    "DownloadOutcome",
    "DownloadSegmentResult",
    "DownloadSource",
    "DownloadSummary",
    "Event",
    "EXTENSION_LYRICS",
    "HTTPAdapter",
    "HTTPError",
    "HIFI_QUALITY_MAP",
    "HiFiStreamManifest",
    "LibraryDB",
    "Lock",
    "LoggerLike",
    "METADATA_EXPLICIT",
    "METADATA_LOOKUP_UPC",
    "MediaMissing",
    "MediaType",
    "Metadata",
    "MetadataTargetUPC",
    "Mix",
    "Panel",
    "PLAYLIST_EXTENSION",
    "PLAYLIST_PREFIX",
    "Progress",
    "QUALITY_RANK",
    "Quality",
    "QualityVideo",
    "REQUESTS_TIMEOUT_SEC",
    "Retry",
    "Session",
    "Settings",
    "STATUS_DOWNLOADED",
    "STATUS_FAILED",
    "Stream",
    "StreamManifest",
    "Table",
    "TaskID",
    "Tidal",
    "TooManyRequests",
    "TTLCache",
    "Track",
    "TrackStreamInfo",
    "UserPlaylist",
    "Video",
    "VideoExtensions",
    "_sanitize_name",
    "annotations",
    "cast",
    "check_file_exists",
    "decrypt_file",
    "decrypt_security_token",
    "format_initial_key",
    "format_path_media",
    "futures",
    "instantiate_media",
    "items_results_all",
    "m3u8",
    "name_builder_album_artist",
    "name_builder_artist",
    "name_builder_item",
    "name_builder_title",
    "os",
    "path_config_base",
    "path_file_sanitize",
    "pathlib",
    "quality_name",
    "random",
    "re",
    "requests",
    "shutil",
    "sys",
    "tempfile",
    "time",
    "url_to_filename",
    "uuid4",
    "win_long_path",
    "Any",
    "Playlist",
]