"""Tests for cached Tidal account quality."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tidal_dl.model.cfg import Token


def _make_tidal(tmp_path, *, user_id=42, quality="HI_RES"):
    from tidal_dl.config import Tidal

    response = SimpleNamespace(json=lambda: {"highestSoundQuality": quality})
    request = MagicMock(return_value=response)
    tidal = Tidal.__new__(Tidal)
    tidal.data = Token()
    tidal.session = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        request=SimpleNamespace(request=request),
    )
    tidal.file_path = str(tmp_path / "token.json")
    tidal.path_base = str(tmp_path)
    tidal.cls_model = Token
    return tidal, request


def test_refresh_account_quality_caches_highest_sound_quality(tmp_path):
    tidal, request = _make_tidal(tmp_path)

    quality = tidal.refresh_account_quality()

    assert quality == "HI_RES"
    assert tidal.data.account_quality == "HI_RES"
    request.assert_called_once_with("GET", "users/42/subscription")
    saved = Token.from_json((tmp_path / "token.json").read_text())
    assert saved.account_quality == "HI_RES"


def test_refresh_account_quality_returns_cache_when_subscription_unavailable(tmp_path):
    tidal, request = _make_tidal(tmp_path)
    tidal.data.account_quality = "LOSSLESS"
    request.side_effect = RuntimeError("offline")

    quality = tidal.refresh_account_quality()

    assert quality == "LOSSLESS"
    assert tidal.data.account_quality == "LOSSLESS"


def test_refresh_account_quality_returns_cache_without_user_id(tmp_path):
    tidal, request = _make_tidal(tmp_path, user_id=None)
    tidal.data.account_quality = "HIGH"

    quality = tidal.refresh_account_quality()

    assert quality == "HIGH"
    request.assert_not_called()


def test_login_finalize_refreshes_account_quality_after_persist(tmp_path):
    tidal, request = _make_tidal(tmp_path, quality="LOSSLESS")
    tidal.session.check_login = lambda: True
    tidal.session.token_type = "Bearer"
    tidal.session.access_token = "access"
    tidal.session.refresh_token = "refresh"
    tidal.session.expiry_time = 1_700_000_000

    assert tidal.login_finalize() is True
    assert tidal.data.account_quality == "LOSSLESS"
    request.assert_called_once_with("GET", "users/42/subscription")
