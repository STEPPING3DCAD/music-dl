"""Tests for the GUI API layer."""
from types import SimpleNamespace

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


class _FakeTidalSession:
    def __init__(self, logged_in: bool, username: str = ""):
        self.logged_in = logged_in
        self.user = SimpleNamespace(name=username)

    def check_login(self) -> bool:
        return self.logged_in


class _FakeTidal:
    def __init__(self, logged_in: bool, access_token: str | None, username: str = ""):
        self.session = _FakeTidalSession(logged_in, username)
        self.data = SimpleNamespace(access_token=access_token)


def _make_auth_client(tidal: _FakeTidal) -> TestClient:
    from tidal_dl.gui import create_app
    from tidal_dl.gui.api.settings import get_tidal_instance

    app = create_app(port=_TEST_PORT)
    app.dependency_overrides[get_tidal_instance] = lambda: tidal
    return TestClient(app)


def test_app_factory_returns_fastapi_instance():
    client = _make_client()
    resp = client.get("/", headers=_HOST_HEADER)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "csrf-token" in resp.text


def test_auth_state_reports_connected_session():
    client = _make_auth_client(_FakeTidal(logged_in=True, access_token="token", username="Ada"))

    resp = client.get("/api/auth/status", headers=_HOST_HEADER)

    assert resp.status_code == 200
    assert resp.json() == {"logged_in": True, "username": "Ada", "auth_state": "connected"}


def test_auth_state_reports_not_configured_without_persisted_token():
    client = _make_auth_client(_FakeTidal(logged_in=False, access_token=None))

    resp = client.get("/api/auth/status", headers=_HOST_HEADER)

    assert resp.status_code == 200
    assert resp.json()["auth_state"] == "not_configured"


def test_auth_state_reports_expired_with_persisted_token_and_failed_session():
    client = _make_auth_client(_FakeTidal(logged_in=False, access_token="expired-token"))

    resp = client.get("/api/auth/status", headers=_HOST_HEADER)

    assert resp.status_code == 200
    assert resp.json()["auth_state"] == "expired"


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


def test_static_js_leads_onboarding_with_local_music_folders():
    client = _make_client()
    js = _fetch_gui_js(client)
    setup_source = js.split("async function _checkSetup() {")[1].split(
        "function _renderWizard(setupData) {"
    )[0]
    wizard_source = js.split("function _renderWizard(setupData) {")[1].split(
        "function _teardownWizard() {"
    )[0]

    assert "if (!data.scan_paths_configured)" in setup_source
    assert "hasAnySource" not in setup_source
    assert "if (!setupData.scan_paths_configured) {\n    _wizardStepPaths(wizard);" in wizard_source
    assert "_wizardStepLogin" not in wizard_source
    assert "Select your music folders" in js
    assert "Tidal is optional. Connect it later for catalog search, streaming, and downloads." in js


def test_static_js_offers_explicit_optional_tidal_connection_during_path_setup():
    client = _make_client()
    js = _fetch_gui_js(client)
    path_step_source = js.split("function _wizardStepPaths(wizard) {")[1].split(
        "// ---- ERROR BANNERS ----"
    )[0]

    assert "textEl('button', 'Connect Tidal', 'wizard-btn wizard-btn-secondary')" in path_step_source
    assert "connectTidalBtn.addEventListener('click', () => triggerLogin());" in path_step_source


def test_static_js_shows_tidal_session_banner_only_for_expired_auth():
    client = _make_client()
    js = _fetch_gui_js(client)
    banner_source = js.split("async function _checkErrorBanners() {")[1].split(
        "// Library views: check scan_paths"
    )[0]

    assert "if (auth.auth_state === 'expired')" in banner_source
    assert "Tidal session expired." in banner_source


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
