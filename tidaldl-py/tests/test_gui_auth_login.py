import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class _NeverCompletes:
    def result(self, timeout=None):
        threading.Event().wait(60)


def test_gui_auth_login_refreshes_api_keys_before_oauth(monkeypatch):
    from tidal_dl.gui.api import settings as settings_api

    calls = []

    class Session:
        def check_login(self):
            return False

        def login_oauth(self):
            calls.append("login_oauth")
            return (
                SimpleNamespace(
                    verification_uri_complete="login.tidal.com/device",
                    user_code="ABCD",
                    expires_in=300,
                ),
                _NeverCompletes(),
            )

    class Tidal:
        session = Session()

        def refresh_api_keys(self):
            calls.append("refresh_api_keys")

        def login_finalize(self):
            return False

    settings_api._login_state.clear()
    settings_api._login_state.update({"status": "idle"})
    monkeypatch.setattr(settings_api, "get_tidal_instance", lambda: Tidal())

    result = settings_api.auth_login()

    assert result["status"] == "pending"
    assert calls == ["refresh_api_keys", "login_oauth"]


class _ImmediateFuture:
    def result(self, timeout=None):
        return None


class _ResetTidal:
    def __init__(self, *, logout_error=None, finalize=True):
        self.logout_error = logout_error
        self.finalize = finalize
        self.calls = []

    def logout(self):
        self.calls.append("logout")
        if self.logout_error:
            raise self.logout_error
        return True

    def login_finalize(self):
        self.calls.append("login_finalize")
        return self.finalize


def test_auth_reset_is_local_and_replaces_login_state():
    from tidal_dl.gui.api import settings as settings_api

    tidal = _ResetTidal()
    tidal.session = SimpleNamespace(
        check_login=lambda: pytest.fail("reset called check_login"),
        token_refresh=lambda *_: pytest.fail("reset refreshed token"),
        login_oauth=lambda: pytest.fail("reset started OAuth"),
    )
    settings_api._login_generation = 4
    settings_api._login_state.clear()
    settings_api._login_state.update({"status": "pending", "user_code": "OLD"})

    result = settings_api.auth_reset(tidal)

    assert result == {"status": "reset", "auth_state": "not_configured"}
    assert settings_api._login_generation == 5
    assert settings_api._login_state == {"status": "idle"}
    assert tidal.calls == ["logout"]


def test_stale_oauth_worker_cannot_restore_reset_credentials():
    from tidal_dl.gui.api import settings as settings_api

    tidal = _ResetTidal()
    settings_api._login_generation = 8
    settings_api._login_state.clear()
    settings_api._login_state.update({"status": "idle"})

    settings_api._wait_for_login(tidal, _ImmediateFuture(), generation=7)

    assert tidal.calls == []
    assert settings_api._login_state == {"status": "idle"}


def test_failed_reset_preserves_pending_login_generation_and_worker():
    from tidal_dl.gui.api import settings as settings_api

    tidal = _ResetTidal(logout_error=PermissionError("read-only"))
    settings_api._login_generation = 11
    settings_api._login_state.clear()
    settings_api._login_state.update({"status": "pending", "user_code": "ABCD"})

    with pytest.raises(HTTPException) as exc_info:
        settings_api.auth_reset(tidal)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Could not reset Tidal connection"
    assert settings_api._login_generation == 11
    assert settings_api._login_state == {"status": "pending", "user_code": "ABCD"}

    tidal.logout_error = None
    settings_api._wait_for_login(tidal, _ImmediateFuture(), generation=11)
    assert tidal.calls == ["logout", "login_finalize"]
    assert settings_api._login_state == {"status": "success"}
