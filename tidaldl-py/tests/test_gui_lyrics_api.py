from urllib.parse import quote


def test_get_local_lyrics_returns_synced_payload(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")

    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.read_local_lyrics",
        lambda audio_path: {
            "mode": "synced",
            "track_path": str(path.resolve()),
            "lines": [{"start_ms": 1000, "end_ms": 3000, "text": "Hello"}],
            "text": "",
            "source": "lrc-synced",
        },
    )

    resp = client.get(f"/api/lyrics/local?path={quote(str(path))}", headers=client._host_header)

    assert resp.status_code == 200
    assert resp.json()["mode"] == "synced"
    assert resp.json()["source"] == "lrc-synced"


def test_get_local_lyrics_returns_400_for_blank_path(client):
    resp = client.get("/api/lyrics/local?path=%20%20", headers=client._host_header)

    assert resp.status_code == 400


def test_get_local_lyrics_returns_403_for_forbidden_path(client, monkeypatch):
    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("forbidden"),
    )

    resp = client.get("/api/lyrics/local?path=%2Fetc%2Fpasswd", headers=client._host_header)

    assert resp.status_code == 403


def test_get_local_lyrics_returns_404_for_missing_trusted_path(client, monkeypatch):
    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("not_found"),
    )

    resp = client.get("/api/lyrics/local?path=%2Ftmp%2Fmissing.flac", headers=client._host_header)

    assert resp.status_code == 404


def test_get_local_lyrics_returns_404_for_not_audio(client, monkeypatch):
    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("not_audio"),
    )

    resp = client.get("/api/lyrics/local?path=%2Ftmp%2Fnotes.txt", headers=client._host_header)

    assert resp.status_code == 404


def test_get_local_lyrics_none_payload_keeps_required_fields(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")

    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.read_local_lyrics",
        lambda audio_path: {
            "mode": "none",
            "track_path": str(path.resolve()),
            "lines": [],
            "text": "",
            "source": "none",
        },
    )

    resp = client.get(f"/api/lyrics/local?path={quote(str(path))}", headers=client._host_header)

    assert resp.status_code == 200
    assert resp.json() == {
        "mode": "none",
        "track_path": str(path.resolve()),
        "lines": [],
        "text": "",
        "source": "none",
    }


def test_get_lyrics_prefers_local_and_does_not_call_tidal(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")

    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.read_local_lyrics",
        lambda audio_path: {
            "mode": "synced",
            "track_path": str(path.resolve()),
            "lines": [{"start_ms": 1000, "end_ms": 3000, "text": "Local"}],
            "text": "",
            "source": "lrc-synced",
        },
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("Tidal fallback must not run when local lyrics exist")

    monkeypatch.setattr("tidal_dl.gui.api.lyrics.lyrics_for_now_playing", boom)
    monkeypatch.setattr("tidal_dl.gui.lyrics_tidal.fetch_tidal_lyrics", boom)

    resp = client.get(
        f"/api/lyrics?path={quote(str(path))}&tidal_track_id=9&isrc=USABC",
        headers=client._host_header,
    )

    assert resp.status_code == 200
    assert resp.json()["source"] == "lrc-synced"
    assert resp.json()["lines"][0]["text"] == "Local"


def test_get_lyrics_falls_back_to_tidal_when_local_is_none(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")

    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.read_local_lyrics",
        lambda audio_path: {
            "mode": "none",
            "track_path": str(path.resolve()),
            "lines": [],
            "text": "",
            "source": "none",
        },
    )
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.lyrics_for_now_playing",
        lambda **kwargs: {
            "mode": "unsynced",
            "track_path": str(path.resolve()),
            "lines": [],
            "text": "Huelepega",
            "source": "tidal-unsynced",
        },
    )

    resp = client.get(
        f"/api/lyrics?path={quote(str(path))}&tidal_track_id=44&isrc=USXYZ",
        headers=client._host_header,
    )

    assert resp.status_code == 200
    assert resp.json()["mode"] == "unsynced"
    assert resp.json()["source"] == "tidal-unsynced"
    assert resp.json()["text"] == "Huelepega"


def test_get_lyrics_tidal_only_now_playing_has_no_path(client, monkeypatch):
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.lyrics_for_now_playing",
        lambda **kwargs: {
            "mode": "synced",
            "track_path": "tidal:321",
            "lines": [{"start_ms": 0, "end_ms": 4000, "text": "Streamed"}],
            "text": "",
            "source": "tidal-synced",
        },
    )

    resp = client.get("/api/lyrics?tidal_track_id=321", headers=client._host_header)

    assert resp.status_code == 200
    assert resp.json()["track_path"] == "tidal:321"
    assert resp.json()["source"] == "tidal-synced"


def test_get_lyrics_without_identity_is_400(client):
    resp = client.get("/api/lyrics", headers=client._host_header)

    assert resp.status_code == 400


def test_get_lyrics_tidal_fallback_uses_real_session_track(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")

    from tidal_dl.gui.lyrics_tidal import clear_tidal_lyrics_cache
    from tidal_dl.gui.security import LocalAudioPathResolution

    class Lyrics:
        text = "Session words"
        subtitles = ""

    class Track:
        duration = 20

        def lyrics(self):
            calls.append("lyrics")
            return Lyrics()

    class Session:
        def track(self, track_id, with_album=False):
            calls.append(("track", int(track_id)))
            return Track()

    clear_tidal_lyrics_cache()
    calls: list = []

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.read_local_lyrics",
        lambda audio_path: {
            "mode": "none",
            "track_path": str(path.resolve()),
            "lines": [],
            "text": "",
            "source": "none",
        },
    )
    monkeypatch.setattr("tidal_dl.gui.api.lyrics._library_identity", lambda *_args: (77, "USABC", "Huelepega", "Sandy"))
    monkeypatch.setattr("tidal_dl.gui.api.lyrics._tidal_session_state", lambda: (Session(), True))

    resp = client.get(f"/api/lyrics?path={quote(str(path))}", headers=client._host_header)

    assert resp.status_code == 200
    assert resp.json()["source"] == "tidal-unsynced"
    assert resp.json()["text"] == "Session words"
    assert calls == [("track", 77), "lyrics"]
    clear_tidal_lyrics_cache()


def test_get_lyrics_tidal_failure_is_502_not_empty(client, monkeypatch):
    from tidal_dl.gui.lyrics_tidal import clear_tidal_lyrics_cache

    class Session:
        def track(self, track_id, with_album=False):
            raise RuntimeError("tidal down")

    clear_tidal_lyrics_cache()
    monkeypatch.setattr("tidal_dl.gui.api.lyrics._tidal_session_state", lambda: (Session(), True))

    resp = client.get("/api/lyrics?tidal_track_id=9", headers=client._host_header)

    assert resp.status_code == 502
    clear_tidal_lyrics_cache()


def test_post_lyrics_save_writes_sidecar_then_local_read_works_offline(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")

    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.lyrics_local.MutagenFile",
        lambda audio_path: type("Info", (), {"info": type("L", (), {"length": 10.0})(), "tags": {}})(),
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("offline reread must not call Tidal")

    save = client.post(
        "/api/lyrics/save",
        headers=client._headers,
        json={
            "path": str(path),
            "lines": [{"start_ms": 1000, "end_ms": 3000, "text": "Saved"}],
            "text": "",
        },
    )
    assert save.status_code == 200
    assert save.json()["source"] == "lrc-synced"
    assert (tmp_path / "track.lrc").read_text(encoding="utf-8")

    monkeypatch.setattr("tidal_dl.gui.api.lyrics.lyrics_for_now_playing", boom)
    monkeypatch.setattr("tidal_dl.gui.api.lyrics._tidal_session_state", lambda: (None, False))

    local = client.get(f"/api/lyrics/local?path={quote(str(path))}", headers=client._host_header)
    assert local.status_code == 200
    assert local.json()["source"] == "lrc-synced"
    assert local.json()["lines"][0]["text"] == "Saved"

    player = client.get(f"/api/lyrics?path={quote(str(path))}", headers=client._host_header)
    assert player.status_code == 200
    assert player.json()["source"] == "lrc-synced"
    assert player.json()["lines"][0]["text"] == "Saved"


def test_post_lyrics_save_keeps_existing_sidecar(client, monkeypatch, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fake")
    path.with_suffix(".lrc").write_text("[00:01.00]Original\n", encoding="utf-8")

    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("ok", path.resolve()),
    )
    monkeypatch.setattr(
        "tidal_dl.gui.lyrics_local.MutagenFile",
        lambda audio_path: type("Info", (), {"info": type("L", (), {"length": 8.0})(), "tags": {}})(),
    )

    resp = client.post(
        "/api/lyrics/save",
        headers=client._headers,
        json={"path": str(path), "text": "Nope"},
    )

    assert resp.status_code == 409
    assert path.with_suffix(".lrc").read_text(encoding="utf-8").startswith("[00:01.00]Original")


def test_post_lyrics_save_rejects_forbidden_path(client, monkeypatch):
    from tidal_dl.gui.security import LocalAudioPathResolution

    monkeypatch.setattr(
        "tidal_dl.gui.api.lyrics.resolve_local_audio_path",
        lambda raw_path, allowed_dirs, **_kwargs: LocalAudioPathResolution("forbidden"),
    )

    resp = client.post(
        "/api/lyrics/save",
        headers=client._headers,
        json={"path": "/etc/passwd", "text": "nope"},
    )

    assert resp.status_code == 403
