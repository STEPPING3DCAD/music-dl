from types import SimpleNamespace


def test_lossless_m4a_transcodes_once_and_reuses_cache(tmp_path, monkeypatch):
    import tidal_dl.gui.api.playback as playback

    source = tmp_path / "song.m4a"
    source.write_bytes(b"lossless source")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        with open(command[-1], "wb") as output:
            output.write(b"flac cache")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(playback, "path_config_base", lambda: str(tmp_path))
    monkeypatch.setattr(playback, "_find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(playback.subprocess, "run", run)

    first = playback._browser_compatible_path(source, "alac")
    second = playback._browser_compatible_path(source, "alac")

    assert first == second
    assert first.suffix == ".flac"
    assert first.read_bytes() == b"flac cache"
    assert len(calls) == 1


def test_browser_compatible_codec_is_served_without_transcode(tmp_path, monkeypatch):
    import tidal_dl.gui.api.playback as playback

    source = tmp_path / "song.m4a"
    source.write_bytes(b"aac source")
    monkeypatch.setattr(
        playback.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transcoded")),
    )

    assert playback._browser_compatible_path(source, "aac") == source
