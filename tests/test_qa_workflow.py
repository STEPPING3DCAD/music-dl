import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "qa.yml"
JOB_NAMES = (
    "python",
    "bot",
    "contracts",
    "performance",
    "supply_chain",
    "affected_build",
    "live",
    "qa",
)


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def job_block(text: str, name: str) -> str:
    start = text.index(f"  {name}:\n")
    following = [
        text.find(f"  {candidate}:\n", start + 1)
        for candidate in JOB_NAMES
        if text.find(f"  {candidate}:\n", start + 1) != -1
    ]
    end = min(following, default=len(text))
    return text[start:end]


def test_qa_workflow_has_safe_triggers_and_permissions():
    text = workflow_text()
    assert "name: qa" in text
    assert "pull_request_target" not in text
    assert "pull_request:" in text
    assert "branches: [master]" in text
    assert "types: [opened, synchronize, reopened, labeled]" in text
    assert not re.search(r"^\s{2}push:\s*$", text, re.MULTILINE)
    assert "permissions:\n  contents: read\n  pull-requests: read" in text


def test_diff_and_scan_jobs_have_full_history():
    text = workflow_text()
    for name in ("python", "contracts", "supply_chain", "affected_build"):
        assert "fetch-depth: 0" in job_block(text, name)


def test_gitleaks_is_commit_pinned_and_receives_no_secret():
    block = job_block(workflow_text(), "supply_chain")
    assert "gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7" in block
    assert "GITHUB_TOKEN: ${{ github.token }}" in block
    assert "GITLEAKS_LICENSE" not in block
    assert re.search(
        r"uses: gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7"
        r"[\s\S]*?continue-on-error: true",
        block,
    )


def test_dependency_review_is_high_severity_and_independently_collected():
    block = job_block(workflow_text(), "supply_chain")
    assert "actions/dependency-review-action@" in block
    assert "fail-on-severity: high" in block
    assert re.search(
        r"uses: actions/dependency-review-action@[^\n]+"
        r"[\s\S]*?continue-on-error: true",
        block,
    )
    assert "gitleaks=${{ steps.gitleaks.outcome }}" in block
    assert "dependency_review=${{ steps.dependency_review.outcome }}" in block


def test_live_job_is_internal_labelled_protected_and_ephemeral():
    block = job_block(workflow_text(), "live")
    assert "contains(github.event.pull_request.labels.*.name, 'qa-live')" in block
    assert "github.event.pull_request.head.repo.full_name == github.repository" in block
    assert "environment: qa-live" in block
    assert "MUSIC_DL_TIDAL_TOKEN_JSON" in block
    assert "DISCORD_TOKEN" in block
    assert "$RUNNER_TEMP/music-dl/token.json" in block
    assert "MUSIC_DL_CONFIG_DIR: ${{ runner.temp }}/music-dl" in block
    assert 'chmod 600 "$RUNNER_TEMP/music-dl/token.json"' in block
    assert "if: always()" in block
    assert 'rm -f "$RUNNER_TEMP/music-dl/token.json"' in block


def test_all_jobs_have_ten_minute_timeouts():
    text = workflow_text()
    for name in JOB_NAMES:
        assert "timeout-minutes: 10" in job_block(text, name)


def test_python_job_uses_uv_and_keeps_security_contract_hard():
    block = job_block(workflow_text(), "python")
    for path in (
        "tests/test_gui_security.py",
        "tests/test_bot_api.py",
        "tests/test_bot_control_api.py",
        "tests/test_qa_workflow.py",
    ):
        assert path in block
    assert "uv run --extra test python -m pytest" in block
    assert "ruff check --no-fix --select E9,F63,F7,F82" in block
    assert "origin/${{ github.base_ref }}...HEAD" in block
    assert "uv build --project tidaldl-py" in block
    assert "security_tests=${{ steps.security_tests.outcome }}" in block


def test_bot_contract_and_performance_jobs_run_required_checks():
    text = workflow_text()
    bot = job_block(text, "bot")
    contracts = job_block(text, "contracts")
    performance = job_block(text, "performance")
    assert "bun install --frozen-lockfile" in bot
    assert "bun test" in bot
    assert "bun run typecheck" in bot
    for path in (
        "tests/test_release_version.py",
        "tests/test_edge_channel.py",
        "tests/test_macos_local_installer.sh",
        "tests/test_macos_release_installer.sh",
        "tests/test_windows_local_installer.sh",
        "tests/test_edge_installers.sh",
        "tests/test_edge_workflow.sh",
        "tests/test_one_line_install_docs.sh",
        "tests/test_stable_release_workflow.sh",
    ):
        assert path in contracts
    assert "git diff --check" in contracts
    for junk in ("__pycache__", ".pytest_cache", "dist", "target", "output"):
        assert junk in contracts
    assert (
        'scripts/qa_performance.py --output "$RUNNER_TEMP/performance.json"'
        in performance
    )
    assert "json.load" in performance
    for output in (
        "library_performance",
        "pagination_p95_ms",
        "search_p95_ms",
        "artists_p95_ms",
    ):
        assert output in performance


def test_affected_build_has_explicit_path_rules_and_commands():
    block = job_block(workflow_text(), "affected_build")
    for path in (
        "tidaldl-py/src-tauri/",
        "docker/",
        "docker-compose.yml",
        "tidaldl-py/pyproject.toml",
        "tidaldl-py/package.json",
    ):
        assert path in block
    assert "cargo check --manifest-path tidaldl-py/src-tauri/Cargo.toml" in block
    assert "docker build -f docker/Dockerfile -t music-dl:qa ." in block
    assert "bun install" in block
    assert "bunx tauri --version" in block
    assert "bun install --frozen-lockfile" not in block
    assert "affected_build=not_applicable" in block


def test_final_qa_always_aggregates_all_evidence_in_advisory_mode():
    block = job_block(workflow_text(), "qa")
    assert "if: always()" in block
    assert (
        "needs: [python, bot, contracts, performance, supply_chain, affected_build, live]"
        in block
    )
    assert "scripts/qa_score.py" in block
    assert "GITHUB_STEP_SUMMARY" in block
    assert "--enforce" not in block
    for name in (
        "python_smoke",
        "bun_tests",
        "release_installers",
        "typescript",
        "ruff",
        "security_tests",
        "gitleaks",
        "dependency_review",
        "library_performance",
        "uv_build",
        "affected_build",
        "docs_contracts",
        "diff_hygiene",
    ):
        assert f'--result "{name}=' in block
    for name in (
        "python",
        "bot",
        "contracts",
        "performance",
        "supply_chain",
        "affected_build",
    ):
        assert f'"{name}:' in block
    assert "--duration live=" not in block
    for name in ("pagination_p95_ms", "search_p95_ms", "artists_p95_ms"):
        assert f'"{name}:' in block
    assert "--live-requested" in block
    assert "--live-trusted" in block
    assert "--live-status" in block
