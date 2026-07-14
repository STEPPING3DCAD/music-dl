import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")


def test_tracked_markdown_local_links_resolve():
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md", "*.mdx"],
        cwd=REPO_ROOT,
    ).decode().split("\0")
    broken = []

    for relative in filter(None, tracked):
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

    assert not broken, "Broken local Markdown links:\n" + "\n".join(broken)
