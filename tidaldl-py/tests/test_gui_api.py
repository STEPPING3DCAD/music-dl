"""Tests for the GUI API layer."""
from fastapi.testclient import TestClient

from tests.gui_js_source import GUI_JS_FILES

_TEST_PORT = 8765
_HOST_HEADER = {"host": f"localhost:{_TEST_PORT}"}


def _fetch_gui_js(client: TestClient) -> str:
    parts: list[str] = []
    for name in GUI_JS_FILES:
        resp = client.get(f"/{name}", headers=_HOST_HEADER)
        assert resp.status_code == 200
        parts.append(resp.text)
    return "".join(parts)


def _make_client():
    from tidal_dl.gui import create_app

    return TestClient(create_app(port=_TEST_PORT))


def test_app_factory_returns_fastapi_instance():
    client = _make_client()
    resp = client.get("/", headers=_HOST_HEADER)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "csrf-token" in resp.text


def test_static_css_served():
    client = _make_client()
    resp = client.get("/style.css", headers=_HOST_HEADER)
    assert resp.status_code == 200


def test_static_js_served():
    client = _make_client()
    for name in GUI_JS_FILES:
        resp = client.get(f"/{name}", headers=_HOST_HEADER)
        assert resp.status_code == 200


def test_static_js_does_not_force_single_tab_playback():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "BroadcastChannel('music-dl-player')" not in js
    assert '_playerChannel.postMessage(\'pause\')' not in js


def test_static_js_syncs_recently_played_from_server_memory():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "async function _syncRecentFromServer()" in js
    assert "api('/home/recent?limit=' + MAX_RECENT)" in js


def test_index_does_not_contain_recently_added_sidebar_entry():
    client = _make_client()
    resp = client.get("/", headers=_HOST_HEADER)

    assert resp.status_code == 200
    assert "Recently Added" not in resp.text
    assert 'data-view="recent-added"' not in resp.text


def test_static_js_contains_recently_added_library_hooks():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "recent-added" in js
    assert "/library/recent-albums" in js
    assert "loadLibraryRecentAlbumsExpanded" in js
    assert "See all" not in js


def test_static_js_contains_recently_added_expanded_states():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "No recently added albums yet" in js
    assert "Download music or sync your library to populate this view." in js
    assert "Could not load recently added albums" in js


def test_static_js_playlist_sync_updates_download_badge_and_sse():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "toast('Downloading ' + result.missing + ' missing tracks', 'success');\n            updateDlBadge(result.missing);\n            _ensureGlobalSSE();" in js


def test_static_js_playlist_auto_upgrade_scan_present():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "Checking upgrades..." in js
    assert "async function _scanPlaylistUpgrades(" in js
    assert "if (!_setPlaylistUpgradeBadge(trackList, track, result.max_quality)) return;" in js
    assert "upgradeBtn.textContent = 'Upgrade ' + allUpgradeable.length + ' Tracks';" in js


def test_static_js_playlist_upgrade_refresh_control_present():
    client = _make_client()
    js = _fetch_gui_js(client)
    assert "album-upgrade-refresh-btn" in js
    assert "Refresh upgrade availability" in js
    assert "force: true" in js
