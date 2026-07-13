from unittest.mock import patch

import pytest

from tidal_dl import update_available
from tidal_dl.model.meta import ReleaseLatest


@pytest.mark.parametrize(
    ("current", "latest", "expected"),
    [
        ("1.6.9", "v1.6.8", False),
        ("1.6.9", "v1.6.9", False),
        ("1.6.9", "v1.6.10", True),
        ("1.6.9", "v0.0.0", False),
        ("1.6.9", "unexpected", False),
    ],
)
def test_update_available_only_reports_newer_stable_versions(current, latest, expected):
    release = ReleaseLatest(version=latest, url="https://example.test/release", release_info="")

    with (
        patch("tidal_dl.__version__", current),
        patch("tidal_dl.latest_version_information", return_value=release),
    ):
        available, info = update_available()

    assert available is expected
    assert info is release
