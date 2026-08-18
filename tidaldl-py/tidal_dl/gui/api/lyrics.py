"""Lyrics API: local files first, then Tidal session fallback."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from tidal_dl.gui.api.library import _path_in_library, _trusted_library_path
from tidal_dl.gui.api.playback import get_download_paths
from tidal_dl.gui.lyrics_local import read_local_lyrics
from tidal_dl.gui.lyrics_tidal import lyrics_for_now_playing
from tidal_dl.gui.security import resolve_local_audio_path

router = APIRouter(prefix="/lyrics")


def _resolve_audio_path(path: str | None):
    return resolve_local_audio_path(
        path,
        get_download_paths(),
        library_trusts_raw_path=_path_in_library(path) if path else False,
        library_resolved_path=_trusted_library_path(path) if path else None,
    )


def _raise_resolution(resolution) -> None:
    if resolution.kind == "bad_request":
        raise HTTPException(status_code=400, detail="Missing or invalid path")
    if resolution.kind == "forbidden":
        raise HTTPException(status_code=403, detail="Access denied")
    if resolution.kind in {"not_found", "not_audio"}:
        raise HTTPException(status_code=404, detail="Track not found")
    if resolution.kind != "ok" or resolution.path is None:
        raise HTTPException(status_code=500, detail="Unexpected local lyrics resolution failure")


def _library_ids(path: str | None, isrc: str | None) -> tuple[int | None, str | None]:
    resolved_isrc = (isrc or "").strip().upper() or None
    try:
        from tidal_dl.gui.services.db import get_library_db

        db = get_library_db()
    except Exception:
        return None, resolved_isrc
    try:
        if path and not resolved_isrc:
            row = db.get(path)
            if row:
                resolved_isrc = (row.get("isrc") or "").strip().upper() or None
        if resolved_isrc:
            probe = db.get_probe(resolved_isrc)
            if probe and probe.get("tidal_track_id"):
                return int(probe["tidal_track_id"]), resolved_isrc
    except Exception:
        return None, resolved_isrc
    return None, resolved_isrc


def _tidal_session_state() -> tuple[object | None, bool]:
    try:
        from tidal_dl.gui.api.settings import _local_auth_status, get_tidal_instance

        tidal = get_tidal_instance()
        status = _local_auth_status(tidal)
        if status.get("logged_in"):
            return tidal.session, True
        return tidal.session, False
    except Exception:
        return None, False


def _duration_ms(duration: float | None) -> int | None:
    if duration is None:
        return None
    try:
        value = float(duration)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if value < 1000:
        return int(value * 1000)
    return int(value)


@router.get("/local")
def get_local_lyrics(path: str | None = Query(None, description="Absolute path to local audio file")):
    resolution = _resolve_audio_path(path)
    _raise_resolution(resolution)
    return read_local_lyrics(resolution.path)


@router.get("")
def get_lyrics(
    path: str | None = Query(None, description="Absolute path to local audio file"),
    tidal_track_id: int | None = Query(None, description="Tidal track id"),
    isrc: str | None = Query(None, description="ISRC for probe / Tidal resolve"),
    duration: float | None = Query(None, description="Track duration in seconds or milliseconds"),
):
    raw_path = (path or "").strip() or None
    if not raw_path and tidal_track_id is None and not (isrc or "").strip():
        raise HTTPException(status_code=400, detail="Missing track identity")

    local_path = None
    if raw_path:
        resolution = _resolve_audio_path(raw_path)
        _raise_resolution(resolution)
        local_path = resolution.path
        local = read_local_lyrics(local_path)
        if local.get("mode") != "none":
            return local

    probe_id, resolved_isrc = _library_ids(str(local_path) if local_path else raw_path, isrc)
    session, logged_in = _tidal_session_state()
    return lyrics_for_now_playing(
        path=local_path,
        tidal_track_id=tidal_track_id or probe_id,
        isrc=resolved_isrc or isrc,
        session=session,
        logged_in=logged_in,
        duration_ms=_duration_ms(duration),
    )
