"""Download streams helpers."""

from tidal_dl.download._common import *  # noqa: F403


class QualityMismatchError(ValueError):
    """The provider cannot satisfy the selected audio-quality contract."""


_LOSSLESS_TIERS = frozenset({"LOSSLESS", "HI_RES", "HI_RES_LOSSLESS"})
_EXPECTED_CODECS = {
    "LOW": ("aac", "mp4a"),
    "HIGH": ("aac", "mp4a"),
    "LOSSLESS": ("flac",),
    "HI_RES": ("flac",),
    "HI_RES_LOSSLESS": ("flac",),
}


def _require_exact_quality(requested: Quality | str, delivered: Quality | str | None, codec: str | None) -> None:
    """Accept the best available delivery that stays in the requested family.

    Settings quality is a ceiling, not an exact-match requirement. A Hi-Res
    preference may fall back to Blue Lossless FLAC when that is all Tidal has.
    Lossy AAC/MP4A is still rejected when a lossless tier was requested.
    """
    requested_name = quality_name(requested).upper()
    delivered_name = quality_name(delivered).upper() if delivered else "unknown"
    codec_name = (codec or "unknown").strip().lower() or "unknown"
    requested_codecs = _EXPECTED_CODECS.get(requested_name)
    delivered_codecs = _EXPECTED_CODECS.get(delivered_name)
    same_family = (
        requested_name in _LOSSLESS_TIERS and delivered_name in _LOSSLESS_TIERS
    ) or requested_name == delivered_name

    if (
        requested_codecs is None
        or delivered_codecs is None
        or not same_family
        or not codec_name.startswith(delivered_codecs)
    ):
        raise QualityMismatchError(
            f"Quality mismatch: requested {requested_name if requested_codecs else 'unknown'} "
            f"but received {delivered_name if delivered_name in _EXPECTED_CODECS else 'unknown'} "
            f"with codec {codec_name}."
        )


class StreamMixin:
    def _get_track_stream_info_hifi(self, media: Track) -> TrackStreamInfo:
        """Fetch stream info via the Hi-Fi API client and wrap it in a HiFiStreamManifest.

        Args:
            media (Track): The track to fetch.

        Returns:
            TrackStreamInfo: Stream info with a HiFiStreamManifest as the manifest.

        Raises:
            Exception: Propagates any exception from the Hi-Fi client so the caller
                       can decide whether to fall back to OAuth.
        """
        quality_str = HIFI_QUALITY_MAP.get(quality_name(self.session.audio_quality), "LOSSLESS")
        hifi_client = self.tidal.hifi_client
        if hifi_client is None:
            raise RuntimeError("Hi-Fi client is not configured")
        result = hifi_client.track_stream(media.id, quality_str)
        _require_exact_quality(self.session.audio_quality, result.audio_quality, result.codecs)
        manifest = HiFiStreamManifest(
            urls=result.urls,
            file_extension=result.file_extension,
            codecs=result.codecs,
            is_encrypted=result.encryption_type not in ("NONE", ""),
            encryption_key=None,
        )
        return TrackStreamInfo(
            stream_manifest=manifest,
            file_extension=result.file_extension,
            requires_flac_extraction=False,
            media_stream=None,
        )

    def _get_stream_info(
        self, media: Track | Video
    ) -> tuple[StreamManifest | HiFiStreamManifest | None, str, bool, Stream | None]:
        """Get stream information for media, routing through Hi-Fi API or OAuth path.

        For the Hi-Fi API source the stream lock is intentionally skipped because
        Hi-Fi requests are stateless and do not mutate the tidalapi session.  The
        OAuth path retains the broad lock to prevent the Atmos/Normal credential
        race condition described in the original comments below.

        Args:
            media (Track | Video): Media item.

        Returns:
            tuple[StreamManifest | None, str, bool, Stream | None]: Stream info.
        """
        # ------------------------------------------------------------------
        # Hi-Fi API path (Track only) — stateless, no session lock required
        # ------------------------------------------------------------------
        if (
            isinstance(media, Track)
            and self.tidal.active_source == DownloadSource.HIFI_API
            and self.tidal.hifi_client is not None
        ):
            try:
                track_info = self._get_track_stream_info_hifi(media)
                if track_info.stream_manifest is not None:
                    return (
                        track_info.stream_manifest,
                        track_info.file_extension,
                        track_info.requires_flac_extraction,
                        track_info.media_stream,
                    )
            except QualityMismatchError:
                raise
            except TooManyRequests:
                self._on_rate_limit_hit()
                self.fn_logger.exception(
                    f"Too many requests (Hi-Fi API). Skipping '{name_builder_item(media)}'.  "
                    f"Consider activating download delay."
                )
                return None, "", False, None
            except Exception:
                allow_fallback = getattr(self.settings.data, "download_source_fallback", True)
                if not allow_fallback:
                    self.fn_logger.exception(
                        f"Hi-Fi API failed for '{name_builder_item(media)}'. Fallback is disabled."
                    )
                    return None, "", False, None
                self.fn_logger.warning(f"Hi-Fi API failed for '{name_builder_item(media)}'. Falling back to OAuth.")
                # Fall through to OAuth path below

        # ------------------------------------------------------------------
        # OAuth path — CRITICAL: broad lock serializes session credential changes
        #
        # THE PROBLEM: The shared tidalapi session must switch credentials to
        # serve Atmos vs Hi-Res/Normal streams.  Without this lock a thread
        # could overwrite the credentials mid-flight in another thread.
        #
        # THE TRADEOFF: This creates a "tollbooth" bottleneck on stream-info
        # fetching; actual segment downloads still run in parallel.
        #
        # DO NOT "OPTIMIZE" THIS by making the lock more granular.
        # Correctness > Performance.
        # ------------------------------------------------------------------
        with self.tidal.stream_lock:
            # Proactively refresh a near-expiry OAuth token before the API call.
            self.tidal._ensure_token_fresh()

            try:
                if isinstance(media, Track):
                    track_info = self._get_track_stream_info(media)

                    if track_info.stream_manifest is None:
                        return None, "", False, None

                    return (
                        track_info.stream_manifest,
                        track_info.file_extension,
                        track_info.requires_flac_extraction,
                        track_info.media_stream,
                    )

                elif isinstance(media, Video):
                    # Videos always require the normal session
                    if not self.tidal.restore_normal_session():
                        self.fn_logger.error(f"Failed to restore normal session for video: {media.id}")
                        return None, "", False, None

                    file_extension = str(
                        AudioExtensions.MP4 if self.settings.data.video_convert_mp4 else VideoExtensions.TS
                    )
                    return None, file_extension, False, None

                else:
                    self.fn_logger.error(f"Unknown media type for stream info: {type(media)}")
                    return None, "", False, None

            except TooManyRequests:
                self._on_rate_limit_hit()
                self.fn_logger.exception(
                    f"Too many requests against TIDAL backend. Skipping '{name_builder_item(media)}'. "
                    f"Consider activating delay between downloads."
                )
                return None, "", False, None

            except QualityMismatchError:
                raise
            except Exception:
                self.fn_logger.exception(f"Something went wrong. Skipping '{name_builder_item(media)}'.")
                return None, "", False, None

    def _get_track_stream_info(self, media: Track) -> TrackStreamInfo:
        """Get stream info for a Track, handling Atmos/Normal session switching.

        Args:
            media: The track to get stream information for.

        Returns:
            TrackStreamInfo: Container with stream manifest, file extension,
                            FLAC extraction flag, and media stream object.
                            Returns TrackStreamInfo with None/empty values if fails.
        """
        want_atmos = (
            self.settings.data.download_dolby_atmos
            and hasattr(media, "audio_modes")
            and str(AudioMode.dolby_atmos) in [str(mode) for mode in getattr(media, "audio_modes", [])]
        )

        if want_atmos:
            if not self.tidal.switch_to_atmos_session():
                self.fn_logger.error(f"Failed to switch to Atmos session for track: {media.id}")
                return TrackStreamInfo(None, "", False, None)
        else:
            if not self.tidal.restore_normal_session():
                self.fn_logger.error(f"Failed to restore normal session for track: {media.id}")
                return TrackStreamInfo(None, "", False, None)

        media_stream = self.session.track(str(media.id)).get_stream() if want_atmos else media.get_stream()

        stream_manifest = media_stream.get_stream_manifest()
        if not want_atmos:
            _require_exact_quality(self.session.audio_quality, media_stream.audio_quality, stream_manifest.codecs)
        file_extension = str(stream_manifest.file_extension)
        requires_flac_extraction = False

        if self.settings.data.extract_flac and (
            stream_manifest.codecs.upper() == Codec.FLAC and file_extension != AudioExtensions.FLAC
        ):
            file_extension = AudioExtensions.FLAC
            requires_flac_extraction = True

        return TrackStreamInfo(
            stream_manifest=stream_manifest,
            file_extension=file_extension,
            requires_flac_extraction=requires_flac_extraction,
            media_stream=media_stream,
        )
