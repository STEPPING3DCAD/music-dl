from tidal_dl.gui.api.upgrade import _is_quality_upgrade, _request_upgrade_quality


def test_aac_to_lossless_is_an_upgrade():
    assert _is_quality_upgrade(1, 2) is True


def test_same_tier_is_not_an_upgrade():
    assert _is_quality_upgrade(2, 2) is False


def test_request_quality_uses_probed_when_below_target():
    assert _request_upgrade_quality("LOSSLESS", "HI_RES_LOSSLESS") == "LOSSLESS"


def test_request_quality_caps_at_target():
    assert _request_upgrade_quality("HI_RES_LOSSLESS", "HI_RES") == "HI_RES"


def test_request_quality_falls_back_to_target_when_probe_empty():
    assert _request_upgrade_quality("", "HI_RES_LOSSLESS") == "HI_RES_LOSSLESS"
