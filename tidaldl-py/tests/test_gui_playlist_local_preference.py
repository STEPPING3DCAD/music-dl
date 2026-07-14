from types import SimpleNamespace


def _fake_track(
    track_id=1,
    *,
    isrc="ISRC123",
    name="Song",
    artist="Artist",
    album="Album",
    duration=180,
):
    album_obj = SimpleNamespace(id=99, name=album, image=lambda size: "cover-url")
    artist_obj = SimpleNamespace(name=artist)
    return SimpleNamespace(
        id=track_id,
        name=name,
        full_name=name,
        artists=[artist_obj],
        album=album_obj,
        duration=duration,
        audio_quality="LOSSLESS",
        isrc=isrc,
        media_metadata_tags=[],
    )


class _FakePlaylistDB:
    def __init__(self, rows_by_isrc, all_rows=None):
        self.rows_by_isrc = rows_by_isrc
        self._all_rows = all_rows

    def tracks_by_isrc(self, isrc):
        return list(self.rows_by_isrc.get(isrc, []))

    def has_live_isrc(self, isrc):
        return bool(self.tracks_by_isrc(isrc))

    def all_tracks(self):
        if self._all_rows is not None:
            return list(self._all_rows)
        rows = []
        for vals in self.rows_by_isrc.values():
            rows.extend(vals)
        return rows

    def close(self):
        return None


def _patch_playlist_library_db(monkeypatch, playlists_api, fake_db):
    monkeypatch.setattr(playlists_api, "_get_playlist_db", lambda: fake_db)
    monkeypatch.setattr("tidal_dl.gui.api.search._get_library_db", lambda: fake_db)


def test_playlist_tracks_include_local_path_when_isrc_matches(monkeypatch, clear_singletons):
    from tidal_dl.gui.api import playlists as playlists_api

    fake_track = _fake_track()
    fake_session = SimpleNamespace(
        check_login=lambda: True,
        playlist=lambda playlist_id: SimpleNamespace(tracks=lambda: [fake_track]),
    )

    monkeypatch.setattr(playlists_api, "get_tidal_session", lambda: fake_session)
    _patch_playlist_library_db(
        monkeypatch,
        playlists_api,
        _FakePlaylistDB({"ISRC123": [{"path": "/music/local.flac", "artist": "Artist", "title": "Song", "album": "Album"}]}),
    )

    playlists_api._playlist_tracks_cache.clear()
    data = playlists_api.playlist_tracks("pl-local")

    assert data["tracks"][0]["is_local"] is True
    assert data["tracks"][0]["local_path"] == "/music/local.flac"


def test_playlist_tracks_fall_back_to_stream_when_no_local_match(monkeypatch, clear_singletons):
    from tidal_dl.gui.api import playlists as playlists_api

    fake_track = _fake_track(isrc="ISRC999")
    fake_session = SimpleNamespace(
        check_login=lambda: True,
        playlist=lambda playlist_id: SimpleNamespace(tracks=lambda: [fake_track]),
    )

    monkeypatch.setattr(playlists_api, "get_tidal_session", lambda: fake_session)
    _patch_playlist_library_db(monkeypatch, playlists_api, _FakePlaylistDB({}))

    playlists_api._playlist_tracks_cache.clear()
    data = playlists_api.playlist_tracks("pl-stream")

    assert data["tracks"][0]["is_local"] is False
    assert data["tracks"][0].get("local_path") in (None, "")


def test_playlist_sync_uses_same_local_match_logic_as_playlist_view(monkeypatch, clear_singletons):
    from tidal_dl.gui.api import playlists as playlists_api

    fake_track = _fake_track(track_id=7, isrc="", name="Mas De Ti", artist="Don Moen", album="Más De Ti")
    fake_session = SimpleNamespace(
        check_login=lambda: True,
        playlist=lambda playlist_id: SimpleNamespace(tracks=lambda: [fake_track]),
    )
    queued = []

    monkeypatch.setattr(playlists_api, "get_tidal_session", lambda: fake_session)
    _patch_playlist_library_db(
        monkeypatch,
        playlists_api,
        _FakePlaylistDB(
            {},
            all_rows=[{"path": "/music/mas-de-ti.flac", "artist": "Don Moen", "title": "Mas De Ti", "album": "Más De Ti"}],
        ),
    )
    monkeypatch.setattr(playlists_api, "_enqueue_playlist_downloads", lambda track_ids, request=None: queued.extend(track_ids))

    playlists_api._playlist_tracks_cache.clear()
    result = playlists_api.sync_playlist("pl-local-fallback")

    assert result == {"status": "up_to_date", "missing": 0, "total": 1}
    assert queued == []


def test_playlist_sync_skips_local_track_when_library_db_has_isrc_match(monkeypatch, clear_singletons):
    from tidal_dl.gui.api import playlists as playlists_api

    fake_track = _fake_track(track_id=8, isrc="ISRC123")
    fake_session = SimpleNamespace(
        check_login=lambda: True,
        playlist=lambda playlist_id: SimpleNamespace(tracks=lambda: [fake_track]),
    )
    queued = []

    monkeypatch.setattr(playlists_api, "get_tidal_session", lambda: fake_session)
    _patch_playlist_library_db(
        monkeypatch,
        playlists_api,
        _FakePlaylistDB({"ISRC123": [{"path": "/music/local.flac", "artist": "Artist", "title": "Song", "album": "Album"}]}),
    )
    monkeypatch.setattr(playlists_api, "_enqueue_playlist_downloads", lambda track_ids, request=None: queued.extend(track_ids))

    playlists_api._playlist_tracks_cache.clear()
    result = playlists_api.sync_playlist("pl-stale-index")

    assert result == {"status": "up_to_date", "missing": 0, "total": 1}
    assert queued == []


def test_playlist_sync_downloads_when_title_artist_match_is_ambiguous(monkeypatch, clear_singletons):
    from tidal_dl.gui.api import playlists as playlists_api

    fake_track = _fake_track(track_id=9, isrc="", name="Song", artist="Artist", album="Wanted Album")
    fake_session = SimpleNamespace(
        check_login=lambda: True,
        playlist=lambda playlist_id: SimpleNamespace(tracks=lambda: [fake_track]),
    )
    queued = []

    monkeypatch.setattr(playlists_api, "get_tidal_session", lambda: fake_session)
    _patch_playlist_library_db(
        monkeypatch,
        playlists_api,
        _FakePlaylistDB(
            {},
            all_rows=[
                {"path": "/music/a.flac", "artist": "Artist", "title": "Song", "album": "Album A"},
                {"path": "/music/b.flac", "artist": "Artist", "title": "Song", "album": "Album B"},
            ],
        ),
    )
    monkeypatch.setattr(playlists_api, "_enqueue_playlist_downloads", lambda track_ids, request=None: queued.extend(track_ids))

    playlists_api._playlist_tracks_cache.clear()
    result = playlists_api.sync_playlist("pl-ambiguous")

    assert result == {"status": "syncing", "missing": 1, "total": 1}
    assert queued == [9]


def test_best_local_row_prefers_actual_lossless_codec_and_excludes_recycle():
    from tidal_dl.gui.api import playlists as playlists_api

    rows = [
        {
            "path": "/music/lossy.m4a",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "quality": "44100Hz/16bit",
            "format": "M4A",
            "codec": "aac",
            "metadata_complete": True,
        },
        {
            "path": "/music/lossless.m4a",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "quality": "44100Hz/16bit",
            "format": "M4A",
            "codec": "flac",
            "metadata_complete": True,
        },
        {
            "path": "/music/#recycle/hires.flac",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "quality": "192000Hz/24bit",
            "format": "FLAC",
            "codec": "flac",
            "metadata_complete": True,
        },
    ]
    db = _FakePlaylistDB({"ISRC123": rows})

    selected = playlists_api._best_local_row(
        {"isrc": "ISRC123", "name": "Song", "artist": "Artist", "album": "Album"},
        db,
        rows,
    )

    assert selected["path"] == "/music/lossless.m4a"


def test_best_local_row_considers_exact_lossless_metadata_beyond_tidal_isrc():
    from tidal_dl.gui.api import playlists as playlists_api

    lossy = {
        "path": "/music/lossy.m4a",
        "artist": "Marco Barrientos",
        "title": "Será Llena la Tierra",
        "album": "Más de Ti",
        "duration": 407,
        "quality": "44100Hz/16bit",
        "format": "M4A",
        "codec": "aac",
        "metadata_complete": True,
    }
    lossless = dict(lossy, path="/music/lossless.m4a", codec="alac")
    rows = [lossy, lossless]
    db = _FakePlaylistDB({"TIDAL-ISRC": [lossy]}, all_rows=rows)

    selected = playlists_api._best_local_row(
        {
            "isrc": "TIDAL-ISRC",
            "name": "Será Llena la Tierra",
            "artist": "Marco Barrientos",
            "album": "Más de Ti",
            "duration": 407,
        },
        db,
        rows,
        fallback_index=playlists_api._build_title_artist_index(rows),
    )

    assert selected["path"] == "/music/lossless.m4a"


def test_fallback_prefers_closest_duration_before_quality():
    from tidal_dl.gui.api import playlists as playlists_api

    rows = [
        {
            "path": "/music/hires.flac",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "duration": 175,
            "quality": "192000Hz/24bit",
            "codec": "flac",
        },
        {
            "path": "/music/close.m4a",
            "artist": "Artist",
            "title": "Song",
            "album": "Album",
            "duration": 181,
            "quality": "44100Hz/16bit",
            "codec": "aac",
        },
    ]
    db = _FakePlaylistDB({}, all_rows=rows)

    selected = playlists_api._best_local_row(
        {
            "isrc": "",
            "name": "Song",
            "artist": "Artist",
            "album": "Album",
            "duration": 180,
        },
        db,
        rows,
        fallback_index=playlists_api._build_title_artist_index(rows),
    )

    assert selected["path"] == "/music/close.m4a"


def test_playlist_keeps_repeated_entries_and_serializes_local_codec(
    monkeypatch, clear_singletons
):
    from tidal_dl.gui.api import playlists as playlists_api

    repeated = _fake_track()
    session = SimpleNamespace(
        check_login=lambda: True,
        playlist=lambda playlist_id: SimpleNamespace(tracks=lambda: [repeated, repeated]),
    )
    row = {
        "path": "/music/song.m4a",
        "artist": "Artist",
        "title": "Song",
        "album": "Album",
        "codec": "flac",
    }
    monkeypatch.setattr(playlists_api, "get_tidal_session", lambda: session)
    _patch_playlist_library_db(monkeypatch, playlists_api, _FakePlaylistDB({"ISRC123": [row]}))
    playlists_api._playlist_tracks_cache.clear()

    data = playlists_api.playlist_tracks("pl-repeated")

    assert data["total"] == 2
    assert [track["codec"] for track in data["tracks"]] == ["flac", "flac"]
