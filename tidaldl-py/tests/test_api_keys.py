import importlib
import sys
from unittest import mock


def import_api_fresh(monkeypatch, fake_get):
    sys.modules.pop("tidal_dl.api", None)
    monkeypatch.setattr("requests.get", fake_get)
    return importlib.import_module("tidal_dl.api")


def test_api_module_import_does_not_fetch_remote_keys(monkeypatch):
    fake_get = mock.Mock(side_effect=AssertionError("import should not fetch API keys"))

    api = import_api_fresh(monkeypatch, fake_get)

    assert api.getNum() == 2
    assert api.getItem(0)["clientId"] == "4N3n6Q1x95LL5K7p"
    assert api.API_KEYS_GIST_FILE == "tidal-api-key.json"
    fake_get.assert_not_called()


def test_refresh_api_keys_keeps_bundled_keys_when_gist_content_is_bad(monkeypatch):
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"files": {"tidal-api-key.json": {"content": "not-json"}}}
    response.raise_for_status.return_value = None
    fake_get = mock.Mock(return_value=response)
    api = import_api_fresh(monkeypatch, fake_get)

    assert api.refresh_api_keys() is False

    assert api.getVersion() == "1.0.2"
    assert api.getItem(0)["clientId"] == "4N3n6Q1x95LL5K7p"


def test_refresh_api_keys_updates_keys_when_gist_has_content(monkeypatch):
    content = """{
      "version": "9.9.9",
      "keys": [{
        "platform": "test",
        "formats": "HiFi",
        "clientId": "id",
        "clientSecret": "secret",
        "valid": "True",
        "from": "test"
      }]
    }"""
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"files": {"tidal-api-key.json": {"content": content}}}
    response.raise_for_status.return_value = None
    fake_get = mock.Mock(return_value=response)
    api = import_api_fresh(monkeypatch, fake_get)

    assert api.refresh_api_keys() is True

    assert api.getVersion() == "9.9.9"
    assert api.getItem(0)["clientId"] == "id"
    assert any(key["clientId"] == "4N3n6Q1x95LL5K7p" for key in api.getItems())
    fake_get.assert_called_once()


def test_first_valid_index_skips_invalid_keys(monkeypatch):
    content = """{
      "version": "9.9.9",
      "keys": [
        {"platform": "dead", "formats": "", "clientId": "dead", "clientSecret": "x", "valid": "False", "from": "x"},
        {"platform": "ok", "formats": "HiFi", "clientId": "live", "clientSecret": "x", "valid": "True", "from": "x"}
      ]
    }"""
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"files": {"tidal-api-key.json": {"content": content}}}
    response.raise_for_status.return_value = None
    api = import_api_fresh(monkeypatch, mock.Mock(return_value=response))

    assert api.refresh_api_keys() is True
    assert api.first_valid_index() == 1
    assert api.getItem(1)["clientId"] == "live"
