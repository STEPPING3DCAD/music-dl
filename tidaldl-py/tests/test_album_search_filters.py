from types import SimpleNamespace

from tidal_dl.gui.api.search import _serialize_album, _serialize_item


def _album(**overrides):
    values = {
        "id": 42,
        "name": "Edition",
        "artist": SimpleNamespace(name="Artist"),
        "num_tracks": 8,
        "media_metadata_tags": [],
        "audio_modes": [],
        "audio_quality": None,
        "explicit": None,
        "image": lambda size: f"https://example.test/{size}.jpg",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_album_serializer_keeps_hires_atmos_and_explicit_independent():
    result = _serialize_album(
        _album(
            media_metadata_tags=["HIRES_LOSSLESS", "DOLBY_ATMOS"],
            audio_quality="LOSSLESS",
            explicit=True,
        )
    )
    assert result["quality"] == "HI_RES_LOSSLESS"
    assert result["atmos"] is True
    assert result["explicit"] is True


def test_album_serializer_keeps_clean_lossless_state():
    result = _serialize_album(_album(audio_quality="LOSSLESS", explicit=False))
    assert (result["quality"], result["atmos"], result["explicit"]) == (
        "LOSSLESS",
        False,
        False,
    )


def test_album_serializer_marks_missing_metadata_unknown():
    result = _serialize_album(_album())
    assert result["quality"] == "UNKNOWN"
    assert result["atmos"] is False
    assert result["explicit"] is None


def test_generic_item_serializer_does_not_add_album_metadata():
    result = _serialize_item(
        SimpleNamespace(
            id=7,
            name="Artist",
            image=lambda size: "",
            roles=[],
        )
    )
    assert "quality" not in result
    assert "atmos" not in result
    assert "explicit" not in result
