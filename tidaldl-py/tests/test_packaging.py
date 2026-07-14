import json
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
TAURI_CONFIG_PATH = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"


def test_pyproject_readme_points_to_existing_file():
    with PYPROJECT_PATH.open("rb") as f:
        project = tomllib.load(f)["project"]
    readme_path = PROJECT_ROOT / project["readme"]

    assert readme_path.is_file(), f"Missing package README: {readme_path}"


def test_tauri_build_checks_qol_static_markers():
    config = TAURI_CONFIG_PATH.read_text()
    build_command = json.loads(config)["build"]["beforeBuildCommand"]

    assert '"withGlobalTauri": true' in config
    assert "tidal_dl/gui/static/app.js" not in build_command
    assert '\\"api.js\\", \\"views.js\\", \\"player.js\\"' in build_command
    assert "Continue Listening" in build_command
    assert "Smart Shuffle" in build_command
    assert "_libraryAlbumCache" in build_command
