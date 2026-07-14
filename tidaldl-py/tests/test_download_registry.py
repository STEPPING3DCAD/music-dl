from tidal_dl.download.registry import register_downloaded_track
from tidal_dl.helper.library_db import LibraryDB


def test_register_downloaded_track_persists_inspection_facts(tmp_path, monkeypatch):
    import tidal_dl.download.registry as registry
    import tidal_dl.gui.api.library as library_api

    audio_path = tmp_path / "song.m4a"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(registry, "path_config_base", lambda: str(tmp_path))
    monkeypatch.setattr(
        library_api,
        "_read_metadata",
        lambda path: {
            "path": str(path),
            "name": "Song",
            "artist": "Artist",
            "album": "Album",
            "duration": 180,
            "isrc": "ABC",
            "genre": "",
            "quality": "44100Hz/16bit",
            "format": "M4A",
            "codec": "flac",
            "metadata_complete": True,
            "is_local": True,
        },
    )

    register_downloaded_track(audio_path)

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    try:
        row = db.get(str(audio_path))
    finally:
        db.close()

    assert row["codec"] == "flac"
    assert row["metadata_complete"] == 1


def test_register_downloaded_track_skips_excluded_path(tmp_path, monkeypatch):
    import tidal_dl.download.registry as registry

    audio_path = tmp_path / "#recycle" / "song.flac"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(registry, "path_config_base", lambda: str(tmp_path))

    register_downloaded_track(audio_path)

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    try:
        assert db.get(str(audio_path)) is None
    finally:
        db.close()
