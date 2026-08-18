"""Lyrics API: local files first, then Tidal session fallback."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from tidal_dl.gui.api.library import _path_in_library, _trusted_library_path
from tidal_dl.gui.api.playback import get_download_paths
from tidal_dl.gui.lyrics_local import empty_lyrics_payload, read_local_lyrics
from tidal_dl.gui.lyrics_tidal import TidalLyricsError, lyrics_for_now_playing
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


def _library_identity(
    path: str | None, isrc: str | None
) -> tuple[int | None, str | None, str, str]:
    resolved_isrc = (isrc or "").strip().upper() or None
    title = ""
    artist = ""
    try:
        from tidal_dl.gui.services.db import get_library_db

        db = get_library_db()
    except Exception:
        return None, resolved_isrc, title, artist
    try:
        row = db.get(path) if path else None
        if row:
            resolved_isrc = resolved_isrc or (row.get("isrc") or "").strip().upper() or None
            title = (row.get("title") or "").strip()
            artist = (row.get("artist") or "").strip()
        if resolved_isrc:
            probe = db.get_probe(resolved_isrc)
            if probe and probe.get("tidal_track_id"):
                return int(probe["tidal_track_id"]), resolved_isrc, title, artist
    except Exception:
        return None, resolved_isrc, title, artist
    return None, resolved_isrc, title, artist


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
    return int(value * 1000)


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
    title: str | None = Query(None, description="Track title for ISRC search"),
    artist: str | None = Query(None, description="Artist name for ISRC search"),
    duration: float | None = Query(None, description="Track duration in seconds"),
):
    raw_path = (path or "").strip() or None
    if not raw_path and tidal_track_id is None and not (isrc or "").strip():
        raise HTTPException(status_code=400, detail="Missing track identity")

    local_path = None
    local_none = None
    if raw_path:
        resolution = _resolve_audio_path(raw_path)
        _raise_resolution(resolution)
        local_path = resolution.path
        local = read_local_lyrics(local_path)
        if local.get("mode") != "none":
            return local
        local_none = empty_lyrics_payload(str(local.get("track_path") or local_path.resolve()))

    probe_id, resolved_isrc, lib_title, lib_artist = _library_identity(
        str(local_path) if local_path else raw_path, isrc
    )
    session, logged_in = _tidal_session_state()
    try:
        return lyrics_for_now_playing(
            path=local_path,
            tidal_track_id=tidal_track_id or probe_id,
            isrc=resolved_isrc or isrc,
            title=(title or "").strip() or lib_title,
            artist=(artist or "").strip() or lib_artist,
            session=session,
            logged_in=logged_in,
            duration_ms=_duration_ms(duration),
            read_local=(lambda _audio_path: local_none) if local_none is not None else None,
        )
    except TidalLyricsError as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Could not load lyrics from Tidal") from exc
