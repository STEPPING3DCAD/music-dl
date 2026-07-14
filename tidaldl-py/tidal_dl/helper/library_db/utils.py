"""Library DB helpers and constants."""

from __future__ import annotations

import datetime
import pathlib
import re
import sqlite3

_SQLITE_CORRUPTION_MESSAGES = (
    "file is not a database",
    "database disk image is malformed",
)


def _is_sqlite_corruption(exc: sqlite3.DatabaseError) -> bool:
    message = str(exc).casefold()
    return any(fragment in message for fragment in _SQLITE_CORRUPTION_MESSAGES)


def _corrupt_backup_path(path: pathlib.Path) -> pathlib.Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.corrupt-{stamp}")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.corrupt-{stamp}-{index}")
        index += 1
    return candidate


def _quarantine_corrupt_db(path: pathlib.Path) -> None:
    if not path.exists():
        return

    backup = _corrupt_backup_path(path)
    path.replace(backup)
    for suffix in ("-wal", "-shm"):
        sidecar = path.with_name(f"{path.name}{suffix}")
        if sidecar.exists():
            sidecar.replace(backup.with_name(f"{backup.name}{suffix}"))


def _normalize_track_text(value: str | None) -> str:
    return (value or "").strip().casefold()


_EXCLUDED_LIBRARY_COMPONENTS = {
    "#recycle",
    ".trash",
    ".trashes",
    "undo-staging",
}


def _is_excluded_library_path(row_or_path: dict | str | pathlib.Path) -> bool:
    path = row_or_path.get("path", "") if isinstance(row_or_path, dict) else row_or_path
    components = str(path).replace("\\", "/").split("/")
    return any(part.casefold() in _EXCLUDED_LIBRARY_COMPONENTS for part in components)


def _local_quality_rank(
    quality: str | None,
    fmt: str | None,
    codec: str | None = None,
) -> int:
    codec_family = (codec or "").casefold()
    if codec_family in {"aac", "mp3", "ogg", "opus", "vorbis"}:
        return 1
    if not codec and fmt and fmt.upper() in {"MP3", "AAC", "OGG", "M4A"}:
        return 1
    if not quality:
        return 2 if codec_family in {"flac", "alac", "pcm"} else 0

    direct = {
        "LOW": 0,
        "HIGH": 1,
        "LOSSLESS": 2,
        "HI_RES": 3,
        "HI_RES_LOSSLESS": 4,
        "FLAC": 2,
    }.get(quality.upper())
    if direct is not None:
        return direct

    match = re.match(r"(\d+)Hz/(\d+)bit", quality, re.IGNORECASE)
    if not match:
        return 0

    sample_rate = int(match.group(1))
    bit_depth = int(match.group(2))
    if bit_depth >= 24 and sample_rate > 48000:
        return 4
    if bit_depth >= 24:
        return 3
    if bit_depth >= 16:
        return 2
    return 0


def _path_suffix_rank(path: str | None) -> int:
    stem = pathlib.Path(path or "").stem
    return 1 if re.search(r"_\d{2}$", stem) else 0


def _album_track_key(row: dict) -> tuple[str, str]:
    return (
        _normalize_track_text(row.get("title")),
        _normalize_track_text(row.get("artist")),
    )


def _album_track_preference(row: dict) -> tuple[int, int, int, str]:
    path = row.get("path") or ""
    return (
        -_local_quality_rank(
            row.get("quality"), row.get("format"), row.get("codec")
        ),
        _path_suffix_rank(path),
        len(path),
        path,
    )


def _metadata_is_complete(row: dict) -> bool:
    explicit = row.get("metadata_complete")
    if explicit is not None:
        return bool(explicit)
    values = [
        _normalize_track_text(row.get("title")),
        _normalize_track_text(row.get("artist")),
        _normalize_track_text(row.get("album")),
    ]
    return all(values) and values[1] != "unknown artist" and values[2] != "unknown album"


def _metadata_track_identity(row: dict) -> tuple | None:
    if not _metadata_is_complete(row):
        return None
    try:
        duration = int(round(float(row.get("duration") or 0)))
    except (TypeError, ValueError):
        duration = 0
    return (
        "metadata",
        _normalize_track_text(row.get("title")),
        _normalize_track_text(row.get("artist")),
        _normalize_track_text(row.get("album")),
        duration,
    )


def _canonical_track_identity(row: dict) -> tuple:
    isrc = _normalize_track_text(row.get("isrc"))
    if isrc:
        return ("isrc", isrc)
    metadata_identity = _metadata_track_identity(row)
    if metadata_identity:
        return metadata_identity
    return ("path", row.get("path") or "")


def _canonical_track_preference(row: dict) -> tuple[int, int, int, int, int, str]:
    path = row.get("path") or ""
    return (
        int(_is_excluded_library_path(row)),
        int(not _metadata_is_complete(row)),
        -_local_quality_rank(
            row.get("quality"), row.get("format"), row.get("codec")
        ),
        _path_suffix_rank(path),
        len(path),
        path.casefold(),
    )


def _canonicalize_tracks(rows: list[dict]) -> list[dict]:
    seen_isrcs: set[str] = set()
    seen_metadata: set[tuple] = set()
    seen_paths: set[str] = set()
    result: list[dict] = []
    for row in sorted(rows, key=_canonical_track_preference):
        isrc = _normalize_track_text(row.get("isrc"))
        metadata_identity = _metadata_track_identity(row)
        path = row.get("path") or ""
        duplicate = (
            bool(isrc and isrc in seen_isrcs)
            or bool(metadata_identity and metadata_identity in seen_metadata)
            or bool(not isrc and not metadata_identity and path in seen_paths)
        )
        if not duplicate:
            result.append(row)
        if isrc:
            seen_isrcs.add(isrc)
        if metadata_identity:
            seen_metadata.add(metadata_identity)
        if not isrc and not metadata_identity:
            seen_paths.add(path)
    return result


DOWNLOAD_JOB_FIELDS = {
    "kind",
    "status",
    "track_id",
    "name",
    "artist",
    "album",
    "cover_url",
    "quality",
    "progress",
    "error",
    "old_path",
    "new_path",
    "metadata_json",
    "created_at",
    "started_at",
    "finished_at",
}
