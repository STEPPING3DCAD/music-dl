"""Guard pytest from resolving developer configuration during collection."""

import os
import tempfile
from pathlib import Path


_config_dir = os.environ.get("MUSIC_DL_CONFIG_DIR")
assert _config_dir and Path(_config_dir).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()), (
    "MUSIC_DL_CONFIG_DIR must be temporary before importing tidal_dl.config"
)

from tidal_dl.config import Settings, reset_singletons


def test_settings_use_the_per_test_config_directory(tmp_path):
    config_dir = Path(os.environ["MUSIC_DL_CONFIG_DIR"]).resolve()

    assert config_dir == tmp_path.resolve()
    assert config_dir != (Path.home() / ".config" / "music-dl").resolve()
    assert Path(Settings().file_path).resolve().parent == config_dir


def test_config_directory_can_be_explicitly_overridden(monkeypatch, tmp_path):
    override_dir = tmp_path / "override"
    monkeypatch.setenv("MUSIC_DL_CONFIG_DIR", str(override_dir))
    reset_singletons()

    assert Path(Settings().file_path).resolve().parent == override_dir.resolve()
