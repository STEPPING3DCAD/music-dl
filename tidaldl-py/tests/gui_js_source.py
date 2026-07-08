"""Helpers for tests that inspect the split GUI JavaScript bundle."""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "tidal_dl" / "gui" / "static"
GUI_JS_FILES = ("api.js", "views.js", "player.js")


def read_gui_js() -> str:
    return "".join((STATIC_DIR / name).read_text(encoding="utf-8") for name in GUI_JS_FILES)