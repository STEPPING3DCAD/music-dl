import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_repository_privacy.py"
WORKFLOW = ROOT / ".github" / "workflows" / "privacy.yml"
HOOKS = ROOT / ".githooks"


def run(*args: str, cwd: Path, input_text: str | None = None, env=None):
    return subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def git(repo: Path, *args: str, check: bool = True):
    result = run("git", *args, cwd=repo)
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result


def init_repo(path: Path):
    git(path, "init", "-q")
    git(path, "config", "user.name", "Privacy Test")
    git(path, "config", "user.email", "privacy@example.invalid")


def write(path: Path, content: str = "test\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def install_gate(repo: Path):
    shutil.copytree(HOOKS, repo / ".githooks")
    (repo / "scripts").mkdir()
    shutil.copy2(SCRIPT, repo / "scripts" / SCRIPT.name)
    git(repo, "config", "core.hooksPath", ".githooks")


def checker(repo: Path, *args: str, input_text: str | None = None, env=None):
    return run(
        sys.executable,
        str(SCRIPT),
        *args,
        cwd=repo,
        input_text=input_text,
        env=env,
    )


def load_policy():
    spec = importlib.util.spec_from_file_location("repository_privacy", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("privacy checker cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrivacyPolicyTests(unittest.TestCase):
    def test_explicit_private_paths_are_forbidden_at_any_depth(self):
        policy = load_policy()
        names = (
            ".codex",
            ".claude",
            ".agents",
            ".superpowers",
            ".checkpoint",
            ".docs",
            ".firecrawl",
            ".playwright",
            ".playwright-cli",
            ".history",
            "openspec",
            "context",
        )
        for name in names:
            for path in (f"{name}/plan.md", f"nested/{name}/plan.md", name):
                with self.subTest(path=path):
                    self.assertTrue(policy.is_forbidden(path))
        for path in (
            "docs/superpowers/plan.md",
            "nested/docs/superpowers/plan.md",
            "docs/superpowers",
            ".mcp.json",
            "nested/.mcp.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(policy.is_forbidden(path))

    def test_public_guidance_and_similar_names_are_allowed(self):
        policy = load_policy()
        for path in (
            "AGENTS.md",
            "CLAUDE.md",
            "CONTEXT.md",
            "nested/AGENTS.md",
            "docs/context.md",
            "docs/superpowers.md",
            "codex/notes.md",
            "openspecification/notes.md",
            "app/contextual/model.py",
            "scripts/check_repository_privacy.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(policy.is_forbidden(path))

    def test_gitignore_matches_policy_at_root_and_nested_depth(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            shutil.copy2(ROOT / ".gitignore", repo / ".gitignore")
            denied = (
                ".codex/plan.md",
                "nested/.codex/plan.md",
                ".claude/plan.md",
                "nested/.agents/plan.md",
                ".superpowers/plan.md",
                "nested/.checkpoint/plan.md",
                ".docs/plan.md",
                "nested/.firecrawl/result.json",
                ".playwright/session.json",
                "nested/.playwright-cli/session.json",
                ".history/log",
                "nested/openspec/change.md",
                "context/plan.md",
                "nested/context/plan.md",
                "docs/superpowers/plan.md",
                "nested/docs/superpowers/plan.md",
                ".mcp.json",
                "nested/.mcp.json",
            )
            for path in denied:
                with self.subTest(path=path):
                    self.assertEqual(
                        git(repo, "check-ignore", "-q", path, check=False).returncode,
                        0,
                    )
            for path in (
                "AGENTS.md",
                "CLAUDE.md",
                "CONTEXT.md",
                "docs/context.md",
                "scripts/check_repository_privacy.py",
            ):
                with self.subTest(path=path):
                    self.assertEqual(
                        git(repo, "check-ignore", "-q", path, check=False).returncode,
                        1,
                    )


class PrivacyCliTests(unittest.TestCase):
    def test_tracked_mode_rejects_forbidden_path_and_accepts_clean_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            write(repo / "AGENTS.md")
            git(repo, "add", "AGENTS.md")
            self.assertEqual(checker(repo, "--tracked").returncode, 0)
            write(repo / ".codex" / "plan.md")
            git(repo, "add", "-f", ".codex/plan.md")
            result = checker(repo, "--tracked")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".codex/plan.md", result.stderr)

    def test_staged_mode_rejects_addition_but_allows_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            write(repo / ".codex" / "plan.md")
            git(repo, "add", "-f", ".codex/plan.md")
            self.assertNotEqual(checker(repo, "--staged").returncode, 0)
            git(repo, "commit", "-qm", "seed", "--no-verify")
            git(repo, "rm", "-q", ".codex/plan.md")
            self.assertEqual(checker(repo, "--staged").returncode, 0)

    def test_git_failure_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = checker(Path(directory), "--tracked")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("privacy check failed", result.stderr.lower())

    def test_push_mode_rejects_malformed_input_and_bad_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            malformed = checker(repo, "--push", "origin", input_text="too few\n")
            self.assertNotEqual(malformed.returncode, 0)
            self.assertIn("malformed", malformed.stderr.lower())
            bad_tree = checker(
                repo,
                "--push",
                "origin",
                input_text=f"refs/heads/topic {'f' * 40} refs/heads/topic {'0' * 40}\n",
            )
            self.assertNotEqual(bad_tree.returncode, 0)
            self.assertIn("privacy check failed", bad_tree.stderr.lower())

    def test_push_scans_tip_before_rev_list_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            fake_bin = root / "bin"
            repo.mkdir()
            fake_bin.mkdir()
            init_repo(repo)
            write(repo / "README.md")
            git(repo, "add", "README.md")
            git(repo, "commit", "-qm", "base")
            revision = git(repo, "rev-parse", "HEAD").stdout.strip()
            fake_git = fake_bin / "git"
            write(
                fake_git,
                "#!/bin/sh\n"
                'printf "%s\\n" "$1" >> "$PRIVACY_GIT_LOG"\n'
                'if [ "$1" = "rev-list" ]; then exit 23; fi\n'
                'exec "$PRIVACY_REAL_GIT" "$@"\n',
            )
            fake_git.chmod(0o755)
            log = root / "git.log"
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["PRIVACY_GIT_LOG"] = str(log)
            env["PRIVACY_REAL_GIT"] = shutil.which("git") or "git"
            result = checker(
                repo,
                "--push",
                "origin",
                input_text=(
                    f"refs/heads/topic {revision} refs/heads/topic {'0' * 40}\n"
                ),
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines()[0], "ls-tree")


class PrivacyHookTests(unittest.TestCase):
    def test_real_pre_commit_hook_blocks_forbidden_staged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            install_gate(repo)
            write(repo / ".codex" / "plan.md")
            git(repo, "add", "-f", ".codex/plan.md")
            result = git(repo, "commit", "-m", "leak", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".codex/plan.md", result.stderr)
            self.assertNotEqual(
                git(repo, "rev-parse", "--verify", "HEAD", check=False).returncode,
                0,
            )

    def test_real_pre_push_blocks_commit_created_without_commit_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "work"
            remote.mkdir()
            repo.mkdir()
            git(remote, "init", "--bare", "-q")
            init_repo(repo)
            install_gate(repo)
            git(repo, "remote", "add", "origin", str(remote))
            write(repo / ".codex" / "plan.md")
            git(repo, "add", "-f", ".codex/plan.md")
            git(repo, "commit", "-qm", "leak", "--no-verify")
            result = git(repo, "push", "origin", "HEAD:refs/heads/topic", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".codex/plan.md", result.stderr)
            self.assertNotEqual(
                git(remote, "rev-parse", "--verify", "refs/heads/topic", check=False).returncode,
                0,
            )

    def test_pre_push_scans_add_then_delete_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "work"
            remote.mkdir()
            repo.mkdir()
            git(remote, "init", "--bare", "-q")
            init_repo(repo)
            install_gate(repo)
            git(repo, "remote", "add", "origin", str(remote))
            write(repo / "README.md")
            git(repo, "add", "README.md")
            git(repo, "commit", "-qm", "base")
            write(repo / "openspec" / "plan.md")
            git(repo, "add", "-f", "openspec/plan.md")
            git(repo, "commit", "-qm", "add private plan", "--no-verify")
            git(repo, "rm", "-qr", "openspec")
            git(repo, "commit", "-qm", "remove private plan", "--no-verify")
            result = git(repo, "push", "origin", "HEAD:refs/heads/topic", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("openspec/plan.md", result.stderr)

    def test_pre_push_scans_tip_already_reachable_from_remote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "work"
            remote.mkdir()
            repo.mkdir()
            git(remote, "init", "--bare", "-q")
            init_repo(repo)
            git(repo, "remote", "add", "origin", str(remote))
            write(repo / ".docs" / "plan.md")
            git(repo, "add", "-f", ".docs/plan.md")
            git(repo, "commit", "-qm", "private")
            git(repo, "push", "--no-verify", "origin", "HEAD:refs/heads/existing")
            git(repo, "fetch", "-q", "origin")
            install_gate(repo)
            result = git(repo, "push", "origin", "HEAD:refs/heads/new", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".docs/plan.md", result.stderr)

    def test_deliberate_push_no_verify_bypasses_local_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "work"
            remote.mkdir()
            repo.mkdir()
            git(remote, "init", "--bare", "-q")
            init_repo(repo)
            install_gate(repo)
            git(repo, "remote", "add", "origin", str(remote))
            write(repo / ".mcp.json")
            git(repo, "add", "-f", ".mcp.json")
            git(repo, "commit", "-qm", "private", "--no-verify")
            result = git(
                repo,
                "push",
                "--no-verify",
                "origin",
                "HEAD:refs/heads/bypassed",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                git(remote, "rev-parse", "--verify", "refs/heads/bypassed").returncode,
                0,
            )

    def test_pre_push_allows_clean_push_and_remote_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "work"
            remote.mkdir()
            repo.mkdir()
            git(remote, "init", "--bare", "-q")
            init_repo(repo)
            install_gate(repo)
            git(repo, "remote", "add", "origin", str(remote))
            write(repo / "AGENTS.md")
            git(repo, "add", "AGENTS.md")
            git(repo, "commit", "-qm", "public guidance")
            pushed = git(repo, "push", "origin", "HEAD:refs/heads/topic", check=False)
            self.assertEqual(pushed.returncode, 0, pushed.stderr)
            deleted = git(repo, "push", "origin", ":refs/heads/topic", check=False)
            self.assertEqual(deleted.returncode, 0, deleted.stderr)
            self.assertNotEqual(
                git(remote, "rev-parse", "--verify", "refs/heads/topic", check=False).returncode,
                0,
            )

    def test_pre_push_checks_every_ref_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "work"
            remote.mkdir()
            repo.mkdir()
            git(remote, "init", "--bare", "-q")
            init_repo(repo)
            install_gate(repo)
            git(repo, "remote", "add", "origin", str(remote))
            write(repo / "README.md")
            git(repo, "add", "README.md")
            git(repo, "commit", "-qm", "base")
            git(repo, "branch", "clean")
            write(repo / "nested" / ".agents" / "notes.md")
            git(repo, "add", "-f", "nested/.agents/notes.md")
            git(repo, "commit", "-qm", "private", "--no-verify")
            git(repo, "branch", "private")
            result = git(
                repo,
                "push",
                "origin",
                "clean:refs/heads/clean",
                "private:refs/heads/private",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nested/.agents/notes.md", result.stderr)
            for branch in ("clean", "private"):
                self.assertNotEqual(
                    git(
                        remote,
                        "rev-parse",
                        "--verify",
                        f"refs/heads/{branch}",
                        check=False,
                    ).returncode,
                    0,
                )


class PrivacyWorkflowTests(unittest.TestCase):
    def test_required_workflow_runs_tree_check_and_regressions(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: privacy", text)
        self.assertIn("pull_request:", text)
        self.assertIn("push:\n    branches: [master]", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("  privacy:\n", text)
        self.assertIn("timeout-minutes:", text)
        self.assertIn(
            "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6",
            text,
        )
        self.assertIn("python3 scripts/check_repository_privacy.py --tracked", text)
        self.assertIn(
            "python3 -m unittest discover -s tests -p 'test_repository_privacy.py'",
            text,
        )
        self.assertNotIn("continue-on-error", text)


if __name__ == "__main__":
    unittest.main()
