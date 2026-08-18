"""Local lyrics discovery and normalization for the GUI."""

from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile

_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")
_METADATA_LINE_RE = re.compile(r"^\[(ar|ti|al|by):.*\]$", re.IGNORECASE)
_OFFSET_LINE_RE = re.compile(r"^\[offset:([+-]?\d+)\]$", re.IGNORECASE)

MAX_LRC_BYTES = 1 * 1024 * 1024  # no legitimate LRC exceeds this; cap prevents local DoS


class SidecarExistsError(Exception):
    """A good sidecar `.lrc` is already next to the audio file."""

    def __init__(self, payload: dict):
        super().__init__("Sidecar already exists")
        self.payload = payload


def _payload(track_path: Path, mode: str, source: str, lines: list[dict] | None = None, text: str = "") -> dict:
    return {
        "mode": mode,
        "track_path": str(track_path.resolve()),
        "lines": lines or [],
        "text": text,
        "source": source,
    }


def empty_lyrics_payload(track_path: str) -> dict:
    return {
        "mode": "none",
        "track_path": track_path,
        "lines": [],
        "text": "",
        "source": "none",
    }


def lyrics_payload_from_tidal(
    *,
    track_path: str,
    text: str = "",
    subtitles: str = "",
    duration_ms: int | None = None,
) -> dict:
    """Normalize Tidal `lyrics().text` / `.subtitles` into the player payload."""
    subtitles = subtitles or ""
    text = text or ""
    if subtitles and _TIMESTAMP_RE.search(subtitles):
        raw_lines, _plain = parse_lrc_text(subtitles)
        lines = normalize_synced_lines(raw_lines, duration_ms)
        if lines:
            return {
                "mode": "synced",
                "track_path": track_path,
                "lines": lines,
                "text": "",
                "source": "tidal-synced",
            }
    unsynced = _cleanup_unsynced_text(text or subtitles)
    if unsynced:
        return {
            "mode": "unsynced",
            "track_path": track_path,
            "lines": [],
            "text": unsynced,
            "source": "tidal-unsynced",
        }
    return empty_lyrics_payload(track_path)


def discover_sidecar_lrc(audio_path: Path) -> Path | None:
    target_name = f"{audio_path.stem}.lrc"
    siblings = [
        child
        for child in audio_path.parent.iterdir()
        if child.is_file() and not child.is_symlink()  # symlink sidecar → arbitrary file read
    ]

    exact_matches = [child for child in siblings if child.name == target_name]
    if exact_matches:
        return exact_matches[0]

    matches = sorted(
        (child for child in siblings if child.name.lower() == target_name.lower()),
        key=lambda child: child.name,
    )
    if len(matches) == 1:
        return matches[0]
    return None


def decode_lrc_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return raw.decode(encoding).replace("\ufeff", "")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").replace("\ufeff", "")


def _timestamp_to_ms(match: re.Match[str], offset_ms: int) -> int:
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    fraction = (match.group(3) or "").ljust(3, "0")[:3]
    base_ms = ((minutes * 60) + seconds) * 1000 + int(fraction or "0")
    return max(0, base_ms + offset_ms)


def _cleanup_unsynced_line(line: str) -> str | None:
    stripped = line.replace("\r", "").replace("\ufeff", "").strip()
    if not stripped:
        return None
    if _METADATA_LINE_RE.match(stripped) or _OFFSET_LINE_RE.match(stripped):
        return None

    cleaned = _TIMESTAMP_RE.sub("", stripped)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None


def _cleanup_unsynced_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        cleaned = _cleanup_unsynced_line(raw_line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def parse_lrc_text(text: str) -> tuple[list[dict], str]:
    lines: list[dict] = []
    plain_lines: list[str] = []
    offset_ms = 0

    for raw_line in text.splitlines():
        line = raw_line.replace("\r", "").replace("\ufeff", "")
        stripped = line.strip()
        if not stripped:
            continue

        offset_match = _OFFSET_LINE_RE.match(stripped)
        if offset_match:
            offset_ms = int(offset_match.group(1))
            continue
        if _METADATA_LINE_RE.match(stripped):
            continue

        cleaned_plain = _cleanup_unsynced_line(stripped)
        if cleaned_plain:
            plain_lines.append(cleaned_plain)

        timestamps = list(_TIMESTAMP_RE.finditer(stripped))
        lyric_text = _TIMESTAMP_RE.sub("", stripped).strip()
        if not timestamps or not lyric_text:
            continue

        for timestamp in timestamps:
            lines.append({"start_ms": _timestamp_to_ms(timestamp, offset_ms), "text": lyric_text})

    return lines, "\n".join(plain_lines)


def normalize_synced_lines(lines: list[dict], duration_ms: int | None) -> list[dict]:
    merged: list[dict] = []
    for line in sorted(lines, key=lambda item: item["start_ms"]):
        text = str(line.get("text", "")).strip()
        start_ms = int(line.get("start_ms", 0))
        if not text or start_ms < 0:
            continue
        if merged and merged[-1]["start_ms"] == start_ms:
            merged[-1]["text"] += "\n" + text
            continue
        merged.append({"start_ms": start_ms, "text": text})

    normalized: list[dict] = []
    for index, line in enumerate(merged):
        start_ms = line["start_ms"]
        if index < len(merged) - 1:
            end_ms = merged[index + 1]["start_ms"]
        else:
            if duration_ms is not None and duration_ms > start_ms:
                end_ms = duration_ms
            else:
                end_ms = start_ms + 4000
        if end_ms <= start_ms:
            continue
        normalized.append({"start_ms": start_ms, "end_ms": end_ms, "text": line["text"]})
    return normalized


def _duration_ms(audio) -> int | None:
    try:
        length = float(audio.info.length)
    except Exception:
        return None
    duration_ms = int(length * 1000)
    return duration_ms if duration_ms > 0 else None


def _decode_embedded_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _first_non_empty_text(values) -> str:
    if isinstance(values, (str, bytes)):
        values = [values]
    for value in values or []:
        decoded = _decode_embedded_value(value).strip()
        if decoded:
            return decoded
    return ""


def _read_mp3_uslt(tags) -> str:
    frames = []
    for value in (tags or {}).values():
        if hasattr(value, "text") and hasattr(value, "desc") and hasattr(value, "lang"):
            frames.append(value)

    def sort_key(frame):
        return (
            0 if getattr(frame, "desc", "") == "" and getattr(frame, "lang", "") == "eng" else 1,
            0 if getattr(frame, "lang", "") == "eng" else 1,
        )

    for frame in sorted(frames, key=sort_key):
        text = _decode_embedded_value(getattr(frame, "text", "")).strip()
        if text:
            return text
    return ""


def _embedded_candidates(audio_path: Path, audio) -> tuple[list[dict], str]:
    if audio is None:
        return [], ""

    tags = getattr(audio, "tags", None) or {}
    suffix = audio_path.suffix.lower()

    if suffix == ".mp3":
        return [], _cleanup_unsynced_text(_read_mp3_uslt(tags))

    if suffix == ".m4a":
        lyric_text = _first_non_empty_text(tags.get("©lyr"))
        if lyric_text and _TIMESTAMP_RE.search(lyric_text):
            return parse_lrc_text(lyric_text)[0], ""
        if lyric_text:
            unsynced = _cleanup_unsynced_text(lyric_text)
            if unsynced:
                return [], unsynced
        unsynced_atom = _cleanup_unsynced_text(_first_non_empty_text(tags.get("----:com.apple.iTunes:UNSYNCEDLYRICS")))
        return [], unsynced_atom

    if suffix == ".flac":
        lyric_text = _first_non_empty_text(tags.get("LYRICS"))
        if lyric_text and _TIMESTAMP_RE.search(lyric_text):
            return parse_lrc_text(lyric_text)[0], ""
        if lyric_text:
            unsynced = _cleanup_unsynced_text(lyric_text)
            if unsynced:
                return [], unsynced
        unsynced_tag = _cleanup_unsynced_text(_first_non_empty_text(tags.get("UNSYNCEDLYRICS")))
        return [], unsynced_tag

    return [], ""


def read_local_lyrics(audio_path: Path) -> dict:
    audio_path = Path(audio_path)
    audio = None
    try:
        audio = MutagenFile(audio_path)
    except Exception:
        audio = None
    duration_ms = _duration_ms(audio)

    sidecar_unsynced = ""
    sidecar = discover_sidecar_lrc(audio_path)
    if sidecar is not None:
        try:
            if sidecar.stat().st_size <= MAX_LRC_BYTES:
                sidecar_text = decode_lrc_bytes(sidecar.read_bytes())
                sidecar_lines_raw, sidecar_plain = parse_lrc_text(sidecar_text)
                sidecar_lines = normalize_synced_lines(sidecar_lines_raw, duration_ms)
                if sidecar_lines:
                    return _payload(audio_path, "synced", "lrc-synced", lines=sidecar_lines)
                sidecar_unsynced = _cleanup_unsynced_text(sidecar_plain)
        except Exception:
            sidecar_unsynced = ""

    try:
        embedded_raw_lines, embedded_unsynced = _embedded_candidates(audio_path, audio)
    except Exception:
        embedded_raw_lines, embedded_unsynced = [], ""
    embedded_lines = normalize_synced_lines(embedded_raw_lines, duration_ms)
    if embedded_lines:
        return _payload(audio_path, "synced", "embedded-synced", lines=embedded_lines)
    if sidecar_unsynced:
        return _payload(audio_path, "unsynced", "lrc-unsynced", text=sidecar_unsynced)
    if embedded_unsynced:
        return _payload(audio_path, "unsynced", "embedded-unsynced", text=embedded_unsynced)
    return _payload(audio_path, "none", "none")


def _ms_to_lrc_stamp(start_ms: int) -> str:
    minutes = max(0, int(start_ms)) // 60000
    seconds = (max(0, int(start_ms)) % 60000) / 1000
    return f"[{minutes:02d}:{seconds:05.2f}]"


def payload_to_lrc_text(*, lines: list[dict] | None = None, text: str = "") -> str:
    if lines:
        out: list[str] = []
        for line in lines:
            raw_text = str(line.get("text", "")).replace("\r", "").strip()
            if not raw_text:
                continue
            try:
                start_ms = int(line.get("start_ms", 0))
            except (TypeError, ValueError):
                continue
            for part in raw_text.split("\n"):
                part = part.strip()
                if part:
                    out.append(_ms_to_lrc_stamp(start_ms) + part)
        if out:
            return "\n".join(out) + "\n"
    cleaned = _cleanup_unsynced_text(text or "")
    if cleaned:
        return cleaned + "\n"
    return ""


def existing_good_sidecar(audio_path: Path) -> dict | None:
    if discover_sidecar_lrc(Path(audio_path)) is None:
        return None
    local = read_local_lyrics(audio_path)
    if local.get("source") in {"lrc-synced", "lrc-unsynced"}:
        return local
    return None


def write_sidecar_lrc(
    audio_path: Path,
    *,
    lines: list[dict] | None = None,
    text: str = "",
    replace: bool = False,
) -> dict:
    """Write `<stem>.lrc` next to a local audio file. Does not overwrite a good sidecar."""
    audio_path = Path(audio_path)
    existing = existing_good_sidecar(audio_path)
    if existing and not replace:
        raise SidecarExistsError(existing)

    body = payload_to_lrc_text(lines=lines, text=text)
    if not body:
        raise ValueError("No lyrics to save")
    raw = body.encode("utf-8")
    if len(raw) > MAX_LRC_BYTES:
        raise ValueError("Lyrics too large")

    dest = audio_path.with_suffix(".lrc")
    discovered = discover_sidecar_lrc(audio_path)
    if replace and discovered is not None:
        dest = discovered
    if dest.exists() and dest.is_symlink():
        raise ValueError("Refusing to write through a symlink")
    dest.write_bytes(raw)
    return read_local_lyrics(audio_path)
