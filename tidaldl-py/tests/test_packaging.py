import json
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
TAURI_CONFIG_PATH = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
LOOPBACK_CAPABILITY_PATH = PROJECT_ROOT / "src-tauri" / "capabilities" / "loopback.json"
TAURI_BUILD_PATH = PROJECT_ROOT / "src-tauri" / "build.rs"

DESKTOP_COMMANDS = {
    "get-updater-state",
    "check-for-updates",
    "install-update",
    "sidecar-status",
    "stop-sidecar",
    "start-sidecar",
    "restart-sidecar",
}


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
    assert "from tests.gui_js_source import read_gui_js" in build_command
    assert "js=read_gui_js()" in build_command
    assert "Continue Listening" in build_command
    assert "Smart Shuffle" in build_command
    assert "_libraryAlbumCache" in build_command


def test_loopback_ui_has_only_required_desktop_permissions():
    capability = json.loads(LOOPBACK_CAPABILITY_PATH.read_text(encoding="utf-8"))
    permissions = set(capability["permissions"])

    assert capability["local"] is False
    assert capability["windows"] == ["main"]
    assert capability["remote"] == {"urls": ["http://127.0.0.1:*"]}
    assert permissions == {
        "core:event:default",
        "shell:allow-open",
        *(f"allow-{command}" for command in DESKTOP_COMMANDS),
    }
    assert "process:allow-restart" not in permissions
    assert "shell:allow-spawn" not in permissions


def test_tauri_build_registers_all_desktop_commands_for_acl():
    build_source = TAURI_BUILD_PATH.read_text(encoding="utf-8")

    assert "AppManifest::new().commands" in build_source
    for command in DESKTOP_COMMANDS:
        assert f'"{command.replace("-", "_")}"' in build_source
