from pathlib import Path


class DummyInfo:
    def __init__(self, length: float = 0.0):
        self.length = length


class DummyUSLT:
    def __init__(self, text: str, desc: str = "", lang: str = "eng"):
        self.text = text
        self.desc = desc
        self.lang = lang


class DummyAudio:
    def __init__(self, tags=None, length: float = 0.0):
        self.tags = tags or {}
        self.info = DummyInfo(length)


def _audio_file(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"fake")
    return path


def test_sidecar_synced_beats_embedded_unsynced(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.flac")
    track.with_suffix(".lrc").write_text("[00:01.00]Hello\n[00:02.00]World\n", encoding="utf-8")

    monkeypatch.setattr(
        "tidal_dl.gui.lyrics_local.MutagenFile",
        lambda path: DummyAudio(tags={"UNSYNCEDLYRICS": ["embedded plain"]}, length=10.0),
    )

    payload = read_local_lyrics(track)

    assert payload["mode"] == "synced"
    assert payload["source"] == "lrc-synced"
    assert [line["text"] for line in payload["lines"]] == ["Hello", "World"]


def test_plain_lrc_loses_to_valid_embedded_synced(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.m4a")
    track.with_suffix(".lrc").write_text("plain words only\n", encoding="utf-8")

    monkeypatch.setattr(
        "tidal_dl.gui.lyrics_local.MutagenFile",
        lambda path: DummyAudio(tags={"©lyr": ["[00:03.00]Timed line"]}, length=9.0),
    )

    payload = read_local_lyrics(track)

    assert payload["mode"] == "synced"
    assert payload["source"] == "embedded-synced"
    assert payload["lines"][0]["text"] == "Timed line"


def test_empty_unsynced_text_downgrades_to_none(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.flac")
    track.with_suffix(".lrc").write_text("[ar:artist]\n[offset:100]\n[]\n", encoding="utf-8")

    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=0.0))

    payload = read_local_lyrics(track)

    assert payload["mode"] == "none"
    assert payload["source"] == "none"
    assert payload["text"] == ""
    assert payload["lines"] == []


def test_ambiguous_case_insensitive_sidecars_are_ignored(tmp_path, monkeypatch):
    from pathlib import Path

    from tidal_dl.gui.lyrics_local import read_local_lyrics

    class FakeChild:
        def __init__(self, name: str):
            self.name = name

        def is_file(self) -> bool:
            return True

        def is_symlink(self) -> bool:
            return False

    track = _audio_file(tmp_path, "track.flac")
    monkeypatch.setattr(Path, "iterdir", lambda self: [FakeChild("track.LRC"), FakeChild("TRACK.lrc")])
    monkeypatch.setattr(
        "tidal_dl.gui.lyrics_local.MutagenFile",
        lambda path: DummyAudio(tags={"UNSYNCEDLYRICS": ["embedded fallback"]}, length=0.0),
    )

    payload = read_local_lyrics(track)

    assert payload["mode"] == "unsynced"
    assert payload["source"] == "embedded-unsynced"
    assert payload["text"] == "embedded fallback"


def test_decode_order_and_offset_clamp_are_applied():
    from tidal_dl.gui.lyrics_local import decode_lrc_bytes, parse_lrc_text

    text = decode_lrc_bytes("\ufeff[offset:-2000]\r\n[00:01.50]Hello\r\n".encode("utf-8-sig"))
    lines, plain_text = parse_lrc_text(text)

    assert plain_text == "Hello"
    assert lines == [{"start_ms": 0, "text": "Hello"}]


def test_multi_timestamp_lines_expand_and_non_timestamp_lines_are_ignored():
    from tidal_dl.gui.lyrics_local import parse_lrc_text

    lines, plain_text = parse_lrc_text("[00:01.00][00:02.00]Twin\nloose text\n")

    assert lines == [
        {"start_ms": 1000, "text": "Twin"},
        {"start_ms": 2000, "text": "Twin"},
    ]
    assert plain_text == "Twin\nloose text"


def test_mp3_uslt_priority_prefers_empty_desc_english(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.mp3")
    audio = DummyAudio(
        tags={
            "USLT:zzz": DummyUSLT("wrong", desc="comment", lang="zzz"),
            "USLT:eng:comment": DummyUSLT("second", desc="comment", lang="eng"),
            "USLT:eng": DummyUSLT("first", desc="", lang="eng"),
        },
        length=0.0,
    )
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: audio)

    payload = read_local_lyrics(track)

    assert payload["mode"] == "unsynced"
    assert payload["text"] == "first"


def test_m4a_multi_value_atom_selection_and_unsynced_tag(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.m4a")
    audio = DummyAudio(
        tags={
            "©lyr": ["", "[00:03.00]chosen timed"],
            "----:com.apple.iTunes:UNSYNCEDLYRICS": [b"backup plain"],
        },
        length=8.0,
    )
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: audio)

    payload = read_local_lyrics(track)

    assert payload["mode"] == "synced"
    assert payload["source"] == "embedded-synced"
    assert payload["lines"][0]["text"] == "chosen timed"


def test_flac_multi_value_selection_and_unsynced_fallback(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.flac")
    audio = DummyAudio(
        tags={
            "LYRICS": ["", "plain words only"],
            "UNSYNCEDLYRICS": ["picked unsynced"],
        },
        length=0.0,
    )
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: audio)

    payload = read_local_lyrics(track)

    assert payload["mode"] == "unsynced"
    assert payload["source"] == "embedded-unsynced"
    assert payload["text"] == "plain words only"


def test_normalization_merges_duplicates_and_uses_duration_fallback():
    from tidal_dl.gui.lyrics_local import normalize_synced_lines

    lines = normalize_synced_lines(
        [
            {"start_ms": 1000, "text": "A"},
            {"start_ms": 1000, "text": "B"},
            {"start_ms": 3000, "text": "C"},
        ],
        duration_ms=0,
    )

    assert lines == [
        {"start_ms": 1000, "end_ms": 3000, "text": "A\nB"},
        {"start_ms": 3000, "end_ms": 7000, "text": "C"},
    ]


def test_sidecar_over_size_cap_ignored(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import MAX_LRC_BYTES, read_local_lyrics

    track = _audio_file(tmp_path, "track.flac")
    lrc = track.with_suffix(".lrc")
    lrc.write_bytes(b"[00:01.00]Hello\n" + b"x" * MAX_LRC_BYTES)

    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=0.0))

    payload = read_local_lyrics(track)

    assert payload["mode"] == "none"


def test_sidecar_under_size_cap_read_normally(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    track = _audio_file(tmp_path, "track.flac")
    track.with_suffix(".lrc").write_text("[00:01.00]Hello\n[00:02.00]World\n", encoding="utf-8")

    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=10.0))

    payload = read_local_lyrics(track)

    assert payload["mode"] == "synced"
    assert payload["source"] == "lrc-synced"
    assert payload["lines"][0]["text"] == "Hello"


def test_sidecar_symlink_ignored(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics

    real_lrc = tmp_path / "external.lrc"
    real_lrc.write_text("[00:01.00]Secret\n", encoding="utf-8")

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    track = audio_dir / "track.flac"
    track.write_bytes(b"fake")

    lrc_symlink = audio_dir / "track.lrc"
    lrc_symlink.symlink_to(real_lrc)

    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=0.0))

    payload = read_local_lyrics(track)

    assert payload["mode"] == "none"


def test_tidal_subtitles_become_synced_payload():
    from tidal_dl.gui.lyrics_local import lyrics_payload_from_tidal

    payload = lyrics_payload_from_tidal(
        track_path="tidal:99",
        text="plain fallback",
        subtitles="[00:01.00]Hello\n[00:02.00]World\n",
        duration_ms=10000,
    )

    assert payload["mode"] == "synced"
    assert payload["source"] == "tidal-synced"
    assert payload["track_path"] == "tidal:99"
    assert payload["text"] == ""
    assert [line["text"] for line in payload["lines"]] == ["Hello", "World"]
    assert payload["lines"][0]["end_ms"] == 2000
    assert payload["lines"][1]["end_ms"] == 10000


def test_tidal_text_becomes_unsynced_when_subtitles_missing():
    from tidal_dl.gui.lyrics_local import lyrics_payload_from_tidal

    payload = lyrics_payload_from_tidal(
        track_path="tidal:7",
        text="Line one\nLine two\n",
        subtitles="",
    )

    assert payload["mode"] == "unsynced"
    assert payload["source"] == "tidal-unsynced"
    assert payload["lines"] == []
    assert payload["text"] == "Line one\nLine two"


def test_tidal_empty_lyrics_are_honest_none():
    from tidal_dl.gui.lyrics_local import lyrics_payload_from_tidal

    payload = lyrics_payload_from_tidal(track_path="tidal:1", text="", subtitles="")

    assert payload["mode"] == "none"
    assert payload["source"] == "none"
    assert payload["lines"] == []
    assert payload["text"] == ""


def test_local_lyrics_win_over_tidal_fetch(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics
    from tidal_dl.gui.lyrics_tidal import lyrics_for_now_playing

    track = _audio_file(tmp_path, "track.flac")
    track.with_suffix(".lrc").write_text("[00:01.00]Local only\n", encoding="utf-8")
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=8.0))

    calls = {"tidal": 0}

    def boom(*_args, **_kwargs):
        calls["tidal"] += 1
        raise AssertionError("Tidal must not run when local lyrics exist")

    monkeypatch.setattr("tidal_dl.gui.lyrics_tidal.fetch_tidal_lyrics", boom)

    payload = lyrics_for_now_playing(
        path=track,
        tidal_track_id=123,
        isrc="USABC1234567",
        session=object(),
        logged_in=True,
        read_local=read_local_lyrics,
    )

    assert payload["mode"] == "synced"
    assert payload["source"] == "lrc-synced"
    assert payload["lines"][0]["text"] == "Local only"
    assert calls["tidal"] == 0


def test_local_none_falls_back_to_tidal(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics
    from tidal_dl.gui.lyrics_tidal import lyrics_for_now_playing

    track = _audio_file(tmp_path, "track.flac")
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=0.0))

    def fake_fetch(**kwargs):
        assert kwargs["tidal_track_id"] == 55
        assert kwargs["isrc"] == "USXYZ0000001"
        return {
            "mode": "unsynced",
            "track_path": str(track.resolve()),
            "lines": [],
            "text": "From Tidal",
            "source": "tidal-unsynced",
        }

    monkeypatch.setattr("tidal_dl.gui.lyrics_tidal.fetch_tidal_lyrics", fake_fetch)

    payload = lyrics_for_now_playing(
        path=track,
        tidal_track_id=55,
        isrc="USXYZ0000001",
        session=object(),
        logged_in=True,
        read_local=read_local_lyrics,
    )

    assert payload["mode"] == "unsynced"
    assert payload["source"] == "tidal-unsynced"
    assert payload["text"] == "From Tidal"


def test_tidal_lyrics_cache_skips_second_session_hit():
    from tidal_dl.gui.lyrics_tidal import clear_tidal_lyrics_cache, fetch_tidal_lyrics

    class Lyrics:
        text = "Once"
        subtitles = ""

    class Track:
        duration = 180

        def lyrics(self):
            calls.append("lyrics")
            return Lyrics()

    class Session:
        def track(self, track_id, with_album=False):
            calls.append(("track", int(track_id)))
            return Track()

    clear_tidal_lyrics_cache()
    calls: list = []
    session = Session()

    first = fetch_tidal_lyrics(session=session, tidal_track_id=42, track_path="tidal:42")
    second = fetch_tidal_lyrics(session=session, tidal_track_id=42, track_path="tidal:42")

    assert first["text"] == "Once"
    assert second == first
    assert calls == [("track", 42), "lyrics"]
    clear_tidal_lyrics_cache()


def test_isrc_resolve_uses_title_artist_search_not_raw_isrc():
    from tidal_dl.gui.lyrics_tidal import clear_tidal_lyrics_cache, fetch_tidal_lyrics

    class Lyrics:
        text = "Resolved"
        subtitles = ""

    class Track:
        id = 81
        isrc = "USXYZ0000001"
        duration = 12

        def lyrics(self):
            return Lyrics()

    class Session:
        def search(self, query, models=None, limit=10):
            queries.append(query)
            return {"tracks": [Track()]}

        def track(self, track_id, with_album=False):
            assert int(track_id) == 81
            return Track()

    clear_tidal_lyrics_cache()
    queries: list[str] = []

    payload = fetch_tidal_lyrics(
        session=Session(),
        isrc="USXYZ0000001",
        title="Huelepega",
        artist="Sandy",
        track_path="/music/Huelepega.flac",
    )

    assert payload["text"] == "Resolved"
    assert queries == ["Huelepega Sandy"]
    clear_tidal_lyrics_cache()


def test_tidal_lyrics_errors_are_not_cached():
    from tidal_dl.gui.lyrics_tidal import TidalLyricsError, clear_tidal_lyrics_cache, fetch_tidal_lyrics

    class Session:
        def track(self, track_id, with_album=False):
            calls.append(int(track_id))
            raise RuntimeError("tidal down")

    clear_tidal_lyrics_cache()
    calls: list[int] = []

    first_error = None
    second_error = None
    try:
        fetch_tidal_lyrics(session=Session(), tidal_track_id=42, track_path="tidal:42")
    except TidalLyricsError as exc:
        first_error = exc
    try:
        fetch_tidal_lyrics(session=Session(), tidal_track_id=42, track_path="tidal:42")
    except TidalLyricsError as exc:
        second_error = exc

    assert first_error is not None
    assert second_error is not None
    assert calls == [42, 42]
    clear_tidal_lyrics_cache()


def test_hifi_empty_lyrics_fall_back_to_oauth_session():
    from tidal_dl.gui.lyrics_tidal import lyrics_obj_from_track

    class Empty:
        text = ""
        subtitles = ""

    class OAuthLyrics:
        text = "OAuth words"
        subtitles = "[00:01.00]Timed"

    class HifiTrack:
        id = 88

        def lyrics(self):
            return Empty()

    class OAuthTrack:
        def lyrics(self):
            return OAuthLyrics()

    class Session:
        def track(self, track_id, with_album=False):
            assert int(track_id) == 88
            return OAuthTrack()

    lyrics_obj = lyrics_obj_from_track(HifiTrack(), session=Session())

    assert lyrics_obj.text == "OAuth words"
    assert lyrics_obj.subtitles == "[00:01.00]Timed"


def test_write_sidecar_lrc_is_read_back_as_local_synced(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics, write_sidecar_lrc

    track = _audio_file(tmp_path, "track.flac")
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=10.0))

    saved = write_sidecar_lrc(
        track,
        lines=[{"start_ms": 1000, "end_ms": 2500, "text": "Hello"}, {"start_ms": 2500, "end_ms": 4000, "text": "World"}],
    )

    assert saved["source"] == "lrc-synced"
    assert [line["text"] for line in saved["lines"]] == ["Hello", "World"]
    assert (tmp_path / "track.lrc").is_file()
    assert read_local_lyrics(track)["source"] == "lrc-synced"


def test_write_sidecar_lrc_unsynced_text_is_read_offline(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import read_local_lyrics, write_sidecar_lrc

    track = _audio_file(tmp_path, "track.flac")
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=0.0))

    saved = write_sidecar_lrc(track, text="Line one\nLine two")

    assert saved["mode"] == "unsynced"
    assert saved["source"] == "lrc-unsynced"
    assert saved["text"] == "Line one\nLine two"
    assert read_local_lyrics(track)["text"] == "Line one\nLine two"


def test_write_sidecar_lrc_refuses_existing_good_sidecar(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import SidecarExistsError, write_sidecar_lrc

    track = _audio_file(tmp_path, "track.flac")
    track.with_suffix(".lrc").write_text("[00:01.00]Keep me\n", encoding="utf-8")
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=8.0))

    try:
        write_sidecar_lrc(track, text="Overwrite")
    except SidecarExistsError as exc:
        assert exc.payload["source"] == "lrc-synced"
        assert exc.payload["lines"][0]["text"] == "Keep me"
    else:
        raise AssertionError("expected SidecarExistsError")

    assert track.with_suffix(".lrc").read_text(encoding="utf-8").startswith("[00:01.00]Keep me")


def test_write_sidecar_lrc_replace_overwrites_existing(tmp_path, monkeypatch):
    from tidal_dl.gui.lyrics_local import write_sidecar_lrc

    track = _audio_file(tmp_path, "track.flac")
    track.with_suffix(".lrc").write_text("[00:01.00]Old\n", encoding="utf-8")
    monkeypatch.setattr("tidal_dl.gui.lyrics_local.MutagenFile", lambda path: DummyAudio(length=8.0))

    saved = write_sidecar_lrc(track, text="New words", replace=True)

    assert saved["source"] == "lrc-unsynced"
    assert saved["text"] == "New words"
