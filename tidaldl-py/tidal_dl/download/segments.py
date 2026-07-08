"""Download segments helpers."""

from tidal_dl.download._common import *  # noqa: F403

class SegmentMixin:
    def _get_media_urls(
        self,
        media: Track | Video,
        stream_manifest: StreamManifest | HiFiStreamManifest | None = None,
    ) -> list[str]:
        """Extract URLs for the given media item.

        Args:
            media (Track | Video): The media item to download.
            stream_manifest (StreamManifest | None, optional): Stream manifest for tracks. Defaults to None.

        Returns:
            list[str]: List of URLs for the media segments.
        """
        # Get urls for media.
        if isinstance(media, Track):
            if stream_manifest is None:
                return []
            return stream_manifest.get_urls()
        elif isinstance(media, Video):
            quality_video = self.settings.data.quality_video
            m3u8_variant: m3u8.M3U8 = m3u8.load(media.get_url())
            # Find the desired video resolution or the next best one.
            m3u8_playlist, _ = self._extract_video_stream(m3u8_variant, int(quality_video))
            if m3u8_playlist is None:
                return []
            return [segment for segment in m3u8_playlist.files if segment is not None]
        else:
            return []

    def _setup_progress(
        self,
        media_name: str,
        urls: list[str],
        progress_to_stdout: bool,
    ) -> tuple[TaskID, float | None, int | None]:
        """Set up the progress bar/task and compute progress total and block size.

        Args:
            media_name (str): Name of the media item.
            urls (list[str]): List of segment URLs.
            progress_to_stdout (bool): Whether to show progress in stdout.

        Returns:
            tuple[TaskID, int | float | None, int | None]: (TaskID, progress_total, block_size)
        """
        urls_count: int = len(urls)
        progress_total: float | None = None
        block_size: int | None = None

        # Compute total iterations for progress
        if urls_count > 1:
            progress_total = float(urls_count)
            block_size = None
        elif urls_count == 1:
            r = None
            try:
                # Get file size and compute progress steps
                r = requests.head(urls[0], timeout=REQUESTS_TIMEOUT_SEC)
                r.raise_for_status()

                total_size_in_bytes = int(r.headers.get("content-length", 0))
                block_size = 1048576
                progress_total = float(total_size_in_bytes) / float(block_size)
            finally:
                if r:
                    r.close()
        else:
            raise ValueError

        # Create progress Task
        p_task: TaskID = self.progress.add_task(
            f"[blue]Item '{media_name[:30]}'",
            total=progress_total,
            visible=progress_to_stdout,
        )
        return p_task, progress_total, block_size

    def _download_segments(
        self,
        urls: list[str],
        path_base: pathlib.Path,
        block_size: int | None,
        p_task: TaskID,
        progress_to_stdout: bool,
        event_stop: Event | None = None,
    ) -> tuple[bool, list[DownloadSegmentResult]]:
        """Download all segments with progress reporting and abort handling.

        Args:
            urls (list[str]): List of segment URLs.
            path_base (pathlib.Path): Base path for segment files.
            block_size (int | None): Block size for streaming.
            p_task (TaskID): Progress bar task ID.
            progress_to_stdout (bool): Whether to show progress in stdout.
            event_stop (Event | None, optional): Event to stop the download. Defaults to None.

        Returns:
            tuple[bool, list[DownloadSegmentResult]]: (result_segments, list of segment results)
        """
        result_segments: bool = True
        dl_segment_results: list[DownloadSegmentResult] = []

        # Download segments until progress is finished.
        while not self.progress.tasks[p_task].finished:
            with futures.ThreadPoolExecutor(
                max_workers=self.settings.data.downloads_simultaneous_per_track_max
            ) as executor:
                # Dispatch all download tasks to worker threads
                l_futures: list[futures.Future] = [
                    executor.submit(self._download_segment, url, path_base, block_size, p_task, progress_to_stdout)
                    for url in urls
                ]

                # Report results as they become available
                for future in futures.as_completed(l_futures):
                    # Retrieve result
                    result_dl_segment: DownloadSegmentResult = future.result()

                    dl_segment_results.append(result_dl_segment)

                    # Check for a link that was skipped
                    if not result_dl_segment.result and (result_dl_segment.url is not urls[-1]):
                        # Sometimes it happens, if a track is very short (< 8 seconds or so), that the last URL
                        # in `urls` is invalid (HTTP Error 500) and not necessary. File won't be corrupt.
                        # If this is NOT the case, but any other URL has resulted in an error,
                        # mark the whole thing as corrupt.
                        result_segments = False

                        self.fn_logger.error("Something went wrong while downloading. File is corrupt!")

                    # If app is terminated (CTRL+C) or item stopped
                    if self.event_abort.is_set() or (event_stop and event_stop.is_set()):
                        # Cancel all not yet started tasks
                        for f in l_futures:
                            f.cancel()

                        return False, dl_segment_results

        return result_segments, dl_segment_results

    def _download_postprocess(
        self,
        result_segments: bool,
        path_file: pathlib.Path,
        dl_segment_results: list[DownloadSegmentResult],
        media: Track | Video,
        stream_manifest: StreamManifest | HiFiStreamManifest | None = None,
    ) -> tuple[bool, pathlib.Path]:
        """Merge segments, decrypt if needed, and return the final file path.

        Args:
            result_segments (bool): Whether all segments downloaded successfully.
            path_file (pathlib.Path): Path to the output file.
            dl_segment_results (list[DownloadSegmentResult]): List of segment download results.
            media (Track | Video): The media item.
            stream_manifest (StreamManifest | None, optional): Stream manifest for tracks. Defaults to None.

        Returns:
            tuple[bool, pathlib.Path]: (Success, path to downloaded or decrypted file)
        """
        tmp_path_file_decrypted: pathlib.Path = path_file
        result_merge: bool = False

        # Only if no error happened while downloading.
        if result_segments:
            # Bring list into right order, so segments can be easily merged.
            dl_segment_results.sort(key=lambda x: x.id_segment)

            result_merge = self._segments_merge(path_file, dl_segment_results)

            if not result_merge:
                self.fn_logger.error(f"Something went wrong while writing to {media.name}. File is corrupt!")
            elif isinstance(media, Track) and stream_manifest is not None and stream_manifest.is_encrypted:
                encryption_key = stream_manifest.encryption_key
                if encryption_key is None:
                    return False, tmp_path_file_decrypted
                key, nonce = decrypt_security_token(encryption_key)
                tmp_path_file_decrypted = path_file.with_suffix(".decrypted")

                decrypt_file(path_file, tmp_path_file_decrypted, key, nonce)

        return result_merge, tmp_path_file_decrypted

    def _download(
        self,
        media: Track | Video,
        path_file: pathlib.Path,
        stream_manifest: StreamManifest | HiFiStreamManifest | None = None,
        event_stop: Event | None = None,
    ) -> tuple[bool, pathlib.Path]:
        """Download a media item (track or video), handling segments and merging.

        Args:
            media (Track | Video): The media item to download.
            path_file (pathlib.Path): Path to the output file.
            stream_manifest (StreamManifest | None, optional): Stream manifest for tracks. Defaults to None.
            event_stop (Event | None, optional): Event to stop the download. Defaults to None.

        Returns:
            tuple[bool, pathlib.Path]: (Success, path to downloaded or decrypted file)
        """
        media_name: str = name_builder_item(media)

        try:
            urls: list[str] = self._get_media_urls(media, stream_manifest)
        except Exception:
            return False, path_file

        # Always output progress to stdout (no GUI)
        progress_to_stdout: bool = True

        try:
            p_task, progress_total, block_size = self._setup_progress(media_name, urls, progress_to_stdout)
        except Exception:
            return False, path_file

        result_segments, dl_segment_results = self._download_segments(
            urls, path_file.parent, block_size, p_task, progress_to_stdout, event_stop
        )

        result_merge, tmp_path_file_decrypted = self._download_postprocess(
            result_segments, path_file, dl_segment_results, media, stream_manifest
        )

        return result_merge, tmp_path_file_decrypted

    def _segments_merge(self, path_file: pathlib.Path, dl_segment_results: list[DownloadSegmentResult]) -> bool:
        """Merge downloaded segments into a single file and clean up segment files.

        Args:
            path_file (pathlib.Path): Path to the output file.
            dl_segment_results (list[DownloadSegmentResult]): List of segment download results.

        Returns:
            bool: True if merge succeeded, False otherwise.
        """
        result: bool = True
        dl_segment_result: DownloadSegmentResult | None = None

        # Copy the content of all segments into one file.
        try:
            with path_file.open("wb") as f_target:
                for dl_segment_result in dl_segment_results:
                    with dl_segment_result.path_segment.open("rb") as f_segment:
                        # Read and write chunks, which gives better HDD write performance
                        while segment := f_segment.read(CHUNK_SIZE):
                            f_target.write(segment)

                    # Delete segment from HDD
                    dl_segment_result.path_segment.unlink()

        except Exception:
            if dl_segment_result is None or dl_segment_result is not dl_segment_results[-1]:
                result = False

        return result

    def _download_segment(
        self, url: str, path_base: pathlib.Path, block_size: int | None, p_task: TaskID, progress_to_stdout: bool
    ) -> DownloadSegmentResult:
        """Download a single segment of a media file.

        Args:
            url (str): URL of the segment.
            path_base (pathlib.Path): Base path for segment file.
            block_size (int | None): Block size for streaming.
            p_task (TaskID): Progress bar task ID.
            progress_to_stdout (bool): Whether to show progress in stdout.

        Returns:
            DownloadSegmentResult: Result of the segment download.
        """
        result: bool = False
        path_segment: pathlib.Path = path_base / url_to_filename(url)
        # Calculate the segment ID based on the file name within the URL.
        filename_stem: str = str(path_segment.stem).split("_")[-1]
        # CAUTION: This is a workaround, so BTS (LOW quality) track will work. They usually have only ONE link.
        id_segment: int = int(filename_stem) if filename_stem.isdecimal() else 0
        error: HTTPError | None = None

        # If app is terminated (CTRL+C)
        if self.event_abort.is_set():
            return DownloadSegmentResult(
                result=False, url=url, path_segment=path_segment, id_segment=id_segment, error=error
            )

        if not self.event_run.is_set():
            self.event_run.wait()

        # Retry download on failed segments, with an exponential delay between retries
        with requests.Session() as s:
            retries = Retry(total=5, backoff_factor=1)

            s.mount("https://", HTTPAdapter(max_retries=retries))

            try:
                # Create the request object with stream=True, so the content won't be loaded into memory at once.
                r = s.get(url, stream=True, timeout=REQUESTS_TIMEOUT_SEC)

                r.raise_for_status()

                # Write the content to disk. If `chunk_size` is set to `None` the whole file will be written at once.
                expected_size: int = int(r.headers.get("content-length", 0))
                with path_segment.open("wb") as f:
                    for data in r.iter_content(chunk_size=block_size):
                        f.write(data)
                        # Advance progress bar.
                        self.progress.advance(p_task)

                # Integrity check: compare actual bytes written to Content-Length.
                if expected_size > 0 and path_segment.is_file():
                    actual_size = path_segment.stat().st_size
                    if actual_size != expected_size:
                        path_segment.unlink(missing_ok=True)
                        self.fn_logger.warning(
                            f"Integrity check failed for '{path_segment.name}': "
                            f"expected {expected_size} B, got {actual_size} B. Segment discarded."
                        )
                        result = False
                    else:
                        result = True
                else:
                    result = True
            except Exception:
                self.progress.advance(p_task)

        return DownloadSegmentResult(
            result=result, url=url, path_segment=path_segment, id_segment=id_segment, error=error
        )
