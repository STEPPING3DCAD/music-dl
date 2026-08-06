import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")


def _tracked_docs() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md", "*.mdx", "*.rst"],
        cwd=REPO_ROOT,
    ).decode()
    return list(filter(None, output.split("\0")))


def test_tracked_documentation_local_links_resolve():
    broken = []

    for relative in _tracked_docs():
        document = REPO_ROOT / relative
        for line_number, line in enumerate(document.read_text().splitlines(), 1):
            for raw_target in MARKDOWN_LINK.findall(line):
                target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
                parsed = urlsplit(target)
                if parsed.scheme or not parsed.path:
                    continue
                linked = (document.parent / unquote(parsed.path)).resolve()
                if not linked.exists():
                    broken.append(f"{relative}:{line_number} -> {target}")

    assert not broken, "Broken local documentation links:\n" + "\n".join(broken)


def test_live_guides_do_not_reference_retired_files_or_flows():
    retired_by_document = {
        "README.md": ("DESIGN.md", "app.js", "library_db.py", "download.py"),
        "CONTRIBUTING.md": ("app.js",),
        "tidaldl-py/README.md": ("Terminal onboarding remains available", "wizard flow"),
        "tidaldl-py/docs/backend-guide.md": (
            "download.py",
            "gui/bot_first_run.py",
            "helper/library_db.py",
            "helper/decorator.py",
            "helper/isrc_index.py",
            "helper/wrapper.py",
        ),
    }
    stale = []

    for relative, retired in retired_by_document.items():
        text = (REPO_ROOT / relative).read_text()
        for value in retired:
            if value in text:
                stale.append(f"{relative}: {value}")

    assert not stale, "Retired documentation references:\n" + "\n".join(stale)
