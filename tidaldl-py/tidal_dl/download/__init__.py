"""TIDAL download pipeline."""

from tidal_dl.helper.path import path_config_base
from tidal_dl.download.collections import CollectionMixin
from tidal_dl.download.core import DownloadCore
from tidal_dl.download.duplicates import DuplicateMixin
from tidal_dl.download.files import FileMixin
from tidal_dl.download.items import ItemMixin
from tidal_dl.download.registry import register_downloaded_track
from tidal_dl.download.segments import SegmentMixin
from tidal_dl.download.streams import StreamMixin
from tidal_dl.download.types import LoggerLike, RequestsClient
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist


class Download(
    CollectionMixin,
    DuplicateMixin,
    FileMixin,
    ItemMixin,
    StreamMixin,
    SegmentMixin,
    DownloadCore,
):
    """Main class for managing TIDAL media downloads."""

    CollectionMedia = Album | Playlist | UserPlaylist | Mix | Artist


__all__ = [
    "Download",
    "LoggerLike",
    "RequestsClient",
    "register_downloaded_track",
    "path_config_base",
]
