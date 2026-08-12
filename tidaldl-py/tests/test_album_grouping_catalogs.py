"""Optional catalog enrichment remains cached and off the render path."""

import inspect


def test_source_eligibility_is_independent_and_retries_failures_after_24_hours():
    from tidal_dl.gui.api.library import _catalog_source_eligible

    stored = {
        "user_decision": None,
        "vetoes": [],
        "catalog": {
            "tidal": {"status": "matched", "attempted_at": 10},
            "musicbrainz": {"status": "failed", "attempted_at": 100},
        },
    }

    assert _catalog_source_eligible(stored, "tidal", now=100_000) is False
    assert _catalog_source_eligible(stored, "musicbrainz", now=100 + 86_399) is False
    assert _catalog_source_eligible(stored, "musicbrainz", now=100 + 86_400) is True


def test_source_eligibility_skips_user_choice_veto_and_direct_identity():
    from tidal_dl.gui.api.library import _catalog_source_eligible

    assert _catalog_source_eligible({"user_decision": "keep_separate"}, "tidal", now=1) is False
    assert _catalog_source_eligible({"vetoes": [{"code": "conflict"}]}, "tidal", now=1) is False
    assert _catalog_source_eligible(None, "tidal", now=1, direct_identity=True) is False


def test_musicbrainz_transport_identifies_client_and_waits_one_second():
    from tidal_dl.gui.api.library import _musicbrainz_json

    calls = []
    sleeps = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"releases": []}

    def request_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    times = iter((10.25, 11.0))
    _musicbrainz_json._last_request = 10.0
    result = _musicbrainz_json(
        "https://musicbrainz.org/ws/2/release/",
        request_get=request_get,
        clock=lambda: next(times),
        sleeper=sleeps.append,
    )

    assert result == {"releases": []}
    assert sleeps == [0.75]
    assert calls[0][1]["headers"]["User-Agent"].startswith("music-dl/")
    assert calls[0][1]["timeout"] == 10


def test_catalog_track_coverage_requires_90_percent_and_three_slots():
    from tidal_dl.gui.api.library import _catalog_group_matches
    from tidal_dl.helper.album_grouping import build_local_album_groups

    rows = [
        {
            "path": f"/{track}.flac", "artist": "Artist", "album_artist": "Artist",
            "album": "Album", "title": f"Song {track}", "track_number": track,
            "disc_number": 1, "duration": 180,
        }
        for track in range(1, 5)
    ]
    group = build_local_album_groups(rows)[0]

    assert _catalog_group_matches(group, "Artist", [f"Song {track}" for track in range(1, 5)])
    assert not _catalog_group_matches(group, "Artist", ["Song 1", "Song 2", "Song 3"])
    assert not _catalog_group_matches(group, "Other", [f"Song {track}" for track in range(1, 5)])


def test_catalog_failures_become_cached_unavailable_evidence():
    from tidal_dl.gui.api.library import _safe_catalog_lookup

    def offline():
        raise TimeoutError("offline")

    assert _safe_catalog_lookup(offline) == {"status": "failed", "error": "TimeoutError"}


def test_enrichment_is_coalesced_after_scan_and_absent_from_rendering():
    from tidal_dl.gui.api.library import (
        _album_cards,
        _album_enrichment_lock,
        _background_album_enrichment,
        _background_scan,
        _finish_album_scan,
    )

    scan_source = inspect.getsource(_background_scan)
    finish_source = inspect.getsource(_finish_album_scan)
    render_source = inspect.getsource(_album_cards)
    assert scan_source.count("_finish_album_scan(db)") == 2
    assert finish_source.index("db.close()") < finish_source.index("_schedule_album_enrichment()")
    assert "_musicbrainz_catalog_lookup" not in render_source
    assert "_tidal_catalog_lookup" not in render_source

    assert _album_enrichment_lock.acquire(blocking=False)
    try:
        assert _background_album_enrichment() is None
    finally:
        _album_enrichment_lock.release()
