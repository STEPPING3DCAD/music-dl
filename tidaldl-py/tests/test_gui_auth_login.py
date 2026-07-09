import threading
from types import SimpleNamespace


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
