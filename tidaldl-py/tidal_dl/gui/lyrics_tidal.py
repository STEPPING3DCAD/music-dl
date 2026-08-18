"""Tidal lyrics fallback for the now-playing panel and download tagging."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tidal_dl.gui.lyrics_local import empty_lyrics_payload, lyrics_payload_from_tidal, read_local_lyrics
from tidal_dl.helper.cache import TTLCache

_CACHE = TTLCache(ttl_sec=3600)
ReadLocal = Callable[[Path], dict]


class TidalLyricsError(Exception):
    """Tidal session failed while resolving or fetching lyrics."""


def clear_tidal_lyrics_cache() -> None:
    _CACHE.clear()


def _cache_key(tidal_track_id: int | None, isrc: str | None) -> str | None:
    if tidal_track_id:
        return f"tid:{int(tidal_track_id)}"
    if isrc:
        return f"isrc:{isrc.strip().upper()}"
    return None


def _tidal_track_key(tidal_track_id: int | None, isrc: str | None) -> str:
    if tidal_track_id:
        return f"tidal:{int(tidal_track_id)}"
    if isrc:
        return f"isrc:{isrc.strip().upper()}"
    return "tidal:unknown"


def _remember(payload: dict, tidal_track_id: int | None, isrc: str | None) -> None:
    for key in (_cache_key(tidal_track_id, None), _cache_key(None, isrc)):
        if key:
            _CACHE.set(key, payload)


def _lyrics_empty(obj: Any) -> bool:
    if obj is None:
        return True
    return not ((getattr(obj, "text", None) or "") or (getattr(obj, "subtitles", None) or ""))


def lyrics_obj_from_track(track: Any, session: Any = None) -> Any:
    """Return `track.lyrics()`, retrying via the OAuth session when Hi-Fi stubs it."""
    lyrics_fn = getattr(track, "lyrics", None)
    obj = lyrics_fn() if callable(lyrics_fn) else lyrics_fn
    if not _lyrics_empty(obj):
        return obj
    track_id = getattr(track, "id", None)
    if session is None or track_id is None:
        return obj
    try:
        oauth_track = session.track(str(track_id))
    except Exception:
        return obj
    oauth_fn = getattr(oauth_track, "lyrics", None)
    oauth_obj = oauth_fn() if callable(oauth_fn) else oauth_fn
    return oauth_obj if not _lyrics_empty(oauth_obj) else obj


def _search_track_id_by_isrc(
    session: Any,
    isrc: str,
    title: str = "",
    artist: str = "",
) -> int | None:
    target = isrc.strip().upper()
    if not target:
        return None
    query = f"{title} {artist}".strip() or target
    try:
        from tidalapi.media import Track

        results = session.search(query, models=[Track], limit=20)
        tracks = results.get("tracks", []) if isinstance(results, dict) else []
        if not tracks:
            tracks = getattr(results, "tracks", []) or []
        for track in tracks:
            track_isrc = str(getattr(track, "isrc", "") or "").strip().upper()
            if track_isrc == target and getattr(track, "id", None) is not None:
                return int(track.id)
    except TidalLyricsError:
        raise
    except Exception as exc:
        raise TidalLyricsError("Could not resolve Tidal track") from exc
    return None


def fetch_tidal_lyrics(
    *,
    session: Any,
    tidal_track_id: int | None = None,
    isrc: str | None = None,
    title: str = "",
    artist: str = "",
    track_path: str = "",
    duration_ms: int | None = None,
) -> dict:
    """Fetch Tidal lyrics once per track/ISRC and return the player payload."""
    cache_key = _cache_key(tidal_track_id, isrc)
    if cache_key:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached

    identity = track_path or _tidal_track_key(tidal_track_id, isrc)
    track_id = int(tidal_track_id) if tidal_track_id else None
    if track_id is None and isrc:
        track_id = _search_track_id_by_isrc(session, isrc, title=title, artist=artist)

    if track_id is None:
        payload = empty_lyrics_payload(identity)
        _remember(payload, None, isrc)
        return payload

    try:
        track = session.track(track_id)
        lyrics_obj = lyrics_obj_from_track(track, session=session)
        if duration_ms is None:
            seconds = getattr(track, "duration", 0) or 0
            if seconds:
                duration_ms = int(float(seconds) * 1000)
        payload = lyrics_payload_from_tidal(
            track_path=identity,
            text=getattr(lyrics_obj, "text", "") or "",
            subtitles=getattr(lyrics_obj, "subtitles", "") or "",
            duration_ms=duration_ms,
        )
    except TidalLyricsError:
        raise
    except Exception as exc:
        raise TidalLyricsError("Could not load lyrics from Tidal") from exc

    _remember(payload, track_id, isrc)
    return payload


def lyrics_for_now_playing(
    *,
    path: str | Path | None = None,
    tidal_track_id: int | None = None,
    isrc: str | None = None,
    title: str = "",
    artist: str = "",
    session: Any = None,
    logged_in: bool = False,
    read_local: ReadLocal | None = None,
    duration_ms: int | None = None,
) -> dict:
    """Local sidecar/tags first; Tidal `track.lyrics()` only when local is `none`."""
    track_path = ""
    if path:
        audio_path = Path(path)
        reader = read_local or read_local_lyrics
        local = reader(audio_path)
        if local.get("mode") != "none":
            return local
        track_path = str(local.get("track_path") or audio_path.resolve())

    identity = track_path or _tidal_track_key(tidal_track_id, isrc)
    if not logged_in or session is None:
        return empty_lyrics_payload(identity)
    return fetch_tidal_lyrics(
        session=session,
        tidal_track_id=tidal_track_id,
        isrc=isrc,
        title=title,
        artist=artist,
        track_path=identity,
        duration_ms=duration_ms,
    )
