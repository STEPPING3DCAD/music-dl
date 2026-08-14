#!/usr/bin/env python3
"""Block private tool artifacts from entering repository history."""

import argparse
import json
import os
import subprocess
import sys
from typing import TextIO

FORBIDDEN_SEGMENTS = frozenset(
    {
        ".agents",
        ".checkpoint",
        ".claude",
        ".codex",
        ".docs",
        ".firecrawl",
        ".history",
        ".playwright",
        ".playwright-cli",
        ".superpowers",
        "context",
        "openspec",
    }
)
class PrivacyCheckError(RuntimeError):
    """A privacy check could not complete safely."""


def is_forbidden(path: str) -> bool:
    parts = tuple(part for part in path.split("/") if part not in {"", "."})
    if not parts:
        return False
    if any(part in FORBIDDEN_SEGMENTS for part in parts):
        return True
    if parts[-1] == ".mcp.json":
        return True
    return any(
        parts[index : index + 2] == ("docs", "superpowers")
        for index in range(len(parts) - 1)
    )


def run_git(*args: str) -> bytes:
    try:
        result = subprocess.run(
            ("git", *args),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = os.fsdecode(error.stderr).strip()
        suffix = f": {detail}" if detail else ""
        raise PrivacyCheckError(f"git {' '.join(args)} failed{suffix}") from error
    return result.stdout


def nul_paths(output: bytes) -> list[str]:
    return [os.fsdecode(path) for path in output.split(b"\0") if path]


def tracked_paths() -> list[str]:
    return nul_paths(run_git("ls-files", "-z"))


def staged_paths() -> list[str]:
    return nul_paths(
        run_git(
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
        )
    )


def tree_paths(revision: str) -> list[str]:
    return nul_paths(run_git("ls-tree", "-r", "-z", "--name-only", revision))


def outgoing_commits(revision: str, remote: str) -> list[str]:
    output = run_git("rev-list", revision, "--not", f"--remotes={remote}")
    return [os.fsdecode(line) for line in output.splitlines() if line]


def is_deletion(sha: str) -> bool:
    return len(sha) in (40, 64) and set(sha) == {"0"}


def pushed_paths(remote: str, stream: TextIO) -> list[str]:
    if not remote:
        raise PrivacyCheckError("pre-push remote name is missing")

    paths: list[str] = []
    revisions: list[str] = []
    seen: set[str] = set()
    for number, raw_line in enumerate(stream, start=1):
        line = raw_line.rstrip("\n")
        fields = line.split()
        if len(fields) != 4:
            raise PrivacyCheckError(f"malformed pre-push input on line {number}")
        _, local_sha, _, _ = fields
        if is_deletion(local_sha):
            continue
        paths.extend(tree_paths(local_sha))
        seen.add(local_sha)
        revisions.extend(outgoing_commits(local_sha, remote))

    for revision in revisions:
        if revision in seen:
            continue
        seen.add(revision)
        paths.extend(tree_paths(revision))
    return paths


def report(paths: list[str]) -> int:
    forbidden = sorted({path for path in paths if is_forbidden(path)})
    if not forbidden:
        return 0
    print("Repository privacy gate blocked forbidden paths:", file=sys.stderr)
    for path in forbidden:
        print(f"  - {json.dumps(path, ensure_ascii=True)}", file=sys.stderr)
    print(
        "Move private files outside the repository, or remove tracked copies with "
        "git rm --cached <path>.",
        file=sys.stderr,
    )
    return 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--tracked", action="store_true")
    modes.add_argument("--staged", action="store_true")
    modes.add_argument("--push", metavar="REMOTE")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, stream: TextIO = sys.stdin) -> int:
    args = parse_args(argv)
    try:
        if args.tracked:
            paths = tracked_paths()
        elif args.staged:
            paths = staged_paths()
        else:
            paths = pushed_paths(args.push, stream)
        return report(paths)
    except PrivacyCheckError as error:
        print(f"Repository privacy check failed closed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
