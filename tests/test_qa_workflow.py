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
DETERMINISTIC_JOBS = (
    "python",
    "bot",
    "contracts",
    "performance",
    "supply_chain",
    "affected_build",
)
CHECK_STEPS = {
    "python": (
        "Run GUI and API smoke tests",
        "Run Ruff checks",
        "Run security tests",
        "Build Python package",
    ),
    "bot": ("Run bot tests", "Type-check bot"),
    "contracts": (
        "Validate release and installers",
        "Validate documentation contracts",
        "Check diff hygiene",
    ),
    "performance": ("Run LibraryDB performance probe",),
    "supply_chain": (
        "Scan commits with Gitleaks",
        "Review dependency changes",
    ),
    "affected_build": (
        "Check Tauri Rust",
        "Build Docker image",
        "Check Tauri package metadata",
    ),
}
COLLECTORS = {
    "python": "Collect Python results",
    "bot": "Collect bot results",
    "contracts": "Collect contract results",
    "performance": "Collect performance results",
    "supply_chain": "Collect supply-chain results",
    "affected_build": "Collect affected-build result",
}
JOB_OUTPUTS = {
    "python": ("python_smoke", "ruff", "security_tests", "uv_build", "duration"),
    "bot": ("bun_tests", "typescript", "duration"),
    "contracts": (
        "release_installers",
        "docs_contracts",
        "diff_hygiene",
        "duration",
    ),
    "performance": (
        "library_performance",
        "pagination_p95_ms",
        "search_p95_ms",
        "artists_p95_ms",
        "duration",
    ),
    "supply_chain": ("gitleaks", "dependency_review", "duration"),
    "affected_build": ("affected_build", "duration"),
}
SETUP_STEPS = {
    "python": ("Start timer", "Checkout", "Set up uv"),
    "bot": ("Start timer", "Checkout", "Set up Bun", "Install bot dependencies"),
    "contracts": ("Start timer", "Checkout", "Set up uv"),
    "performance": ("Start timer", "Checkout", "Set up uv"),
    "supply_chain": ("Start timer", "Checkout"),
    "affected_build": (
        "Start timer",
        "Checkout",
        "Detect affected builds",
        "Install Linux system dependencies",
        "Set up Rust",
        "Set up Bun",
    ),
}


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


def step_block(job: str, name: str) -> str:
    start = job.index(f"      - name: {name}\n")
    end = job.find("\n      - name:", start + 1)
    return job[start:] if end == -1 else job[start:end]


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
    text = workflow_text()
    block = job_block(text, "live")
    outside_live = text.replace(block, "")
    assert "contains(github.event.pull_request.labels.*.name, 'qa-live')" in block
    assert "github.event.pull_request.head.repo.full_name == github.repository" in block
    assert "environment: qa-live" in block
    assert (
        "MUSIC_DL_TIDAL_TOKEN_JSON: ${{ secrets.MUSIC_DL_TIDAL_TOKEN_JSON }}" in block
    )
    assert "DISCORD_TOKEN: ${{ secrets.DISCORD_TOKEN }}" in block
    assert "MUSIC_DL_TIDAL_TOKEN_JSON" not in outside_live
    assert "DISCORD_TOKEN" not in outside_live
    assert "${{ secrets." not in outside_live
    assert "$RUNNER_TEMP/music-dl/token.json" in block
    assert "MUSIC_DL_CONFIG_DIR: ${{ runner.temp }}/music-dl" in block
    assert 'chmod 600 "$RUNNER_TEMP/music-dl/token.json"' in block
    cleanup = step_block(block, "Remove ephemeral credentials")
    assert "if: always()" in cleanup
    assert 'rm -f "$RUNNER_TEMP/music-dl/token.json"' in cleanup
    collector = step_block(block, "Collect live result")
    assert 'success) echo "live_status=pass"' in collector
    assert 'failure) echo "live_status=fail"' in collector
    assert '*) echo "live_status=missing"' in collector


def test_all_jobs_have_ten_minute_timeouts():
    text = workflow_text()
    for name in JOB_NAMES:
        assert "timeout-minutes: 10" in job_block(text, name)


def test_python_smoke_preserves_original_gui_and_api_selection():
    smoke = step_block(
        job_block(workflow_text(), "python"), "Run GUI and API smoke tests"
    )
    for selector in (
        "tests/test_gui_command.py::TestGuiCommandHelp::test_gui_help_exits_zero",
        "tests/test_gui_command.py::TestGuiCommandHelp::test_gui_help_mentions_port",
        "tests/test_gui_command.py::TestGuiCommandHelp::test_gui_appears_in_root_help",
        "tests/test_gui_command.py::TestGuiCommandInvocation::test_default_port_and_browser",
        "tests/test_gui_command.py::TestGuiCommandInvocation::test_custom_port",
        "tests/test_gui_command.py::TestGuiCommandInvocation::test_no_browser_flag",
        "tests/test_gui_command.py::TestGuiCommandInvocation::test_custom_port_and_no_browser",
        "tests/test_gui_api.py",
        "tests/test_setup.py",
        "tests/test_api_endpoints.py",
        "tests/test_downloads.py",
        "tests/test_gui_security.py",
    ):
        assert f"          {selector}\n" in smoke


def test_deterministic_checks_continue_but_setup_stays_fail_closed():
    text = workflow_text()
    auxiliary_steps = {"performance": ("Parse performance result",)}
    for name in DETERMINISTIC_JOBS:
        block = job_block(text, name)
        actual_steps = set(re.findall(r"^      - name: (.+)$", block, re.MULTILINE))
        expected_steps = {
            *CHECK_STEPS[name],
            *SETUP_STEPS[name],
            COLLECTORS[name],
            *auxiliary_steps.get(name, ()),
        }
        assert actual_steps == expected_steps
        for step in CHECK_STEPS[name]:
            assert "continue-on-error: true" in step_block(block, step)
        for step in SETUP_STEPS[name]:
            assert "continue-on-error" not in step_block(block, step)


def test_deterministic_job_outputs_only_come_from_final_collectors():
    text = workflow_text()
    duration_line = 'echo "duration=$(($(date +%s) - START_EPOCH))"'
    for name in DETERMINISTIC_JOBS:
        block = job_block(text, name)
        header = block[: block.index("    steps:\n")]
        collector = step_block(block, COLLECTORS[name])
        assert ".outcome" not in header
        assert "if: always()" in collector
        assert duration_line in collector
        assert block.rstrip().endswith(collector.rstrip())
        for output in JOB_OUTPUTS[name]:
            assert f"{output}: ${{{{ steps.results.outputs.{output} }}}}" in header
            if output != "duration":
                assert f'"{output}=' in collector


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


def test_performance_result_is_validated_without_artifact_upload():
    text = workflow_text()
    parsed = step_block(job_block(text, "performance"), "Parse performance result")
    assert 'with open(os.environ["PERFORMANCE_JSON"], encoding="utf-8")' in parsed
    assert "data = json.load(handle)" in parsed
    assert 'data["status"]' in parsed
    assert 'data["p95_ms"]' in parsed
    assert '("pagination", "search", "artists")' in parsed
    assert 'status not in {"pass", "regression", "fail"}' in parsed
    assert "math.isfinite" in parsed
    assert "except (OSError" in parsed
    assert "raise SystemExit(0)" in parsed
    assert parsed.index("raise SystemExit(0)") < parsed.index(
        'os.environ["GITHUB_OUTPUT"]'
    )
    assert parsed.count("_p95_ms={value}") == 1
    assert "actions/upload-artifact" not in text
    assert "artifact upload" not in text.lower()


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
    assert 'if [[ "$LIVE_REQUESTED" == true ]]' in block
    assert 'if [[ "$LIVE_TRUSTED" == true ]]' in block
    assert "live_status=${LIVE_JOB_STATUS:-missing}" in block
    assert "live_status=not_applicable" in block
    assert "live_status=not_requested" in block
