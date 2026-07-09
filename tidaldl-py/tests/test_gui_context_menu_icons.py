import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
from tests.gui_js_source import read_gui_js


def test_upgrade_quality_context_menu_has_download_icon_template():
    source = read_gui_js()

    assert "icon: 'download'" in source
    match = re.search(r"const _ctxIcons = \{(.*?)\n\};", source, re.S)
    assert match is not None
    ctx_icons_block = match.group(1)
    assert "download: '<svg" in ctx_icons_block
