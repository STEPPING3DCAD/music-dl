from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
from tests.gui_js_source import read_gui_js


def test_api_client_recovers_from_stale_csrf_token():
    source = read_gui_js()

    assert "let CSRF_TOKEN =" in source
    assert "async function refreshCsrfToken()" in source
    assert "Forbidden: invalid or missing CSRF token" in source
    assert "_csrfRetried: true" in source
