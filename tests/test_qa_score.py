import json

import pytest

from scripts.qa_score import evaluate, main

RULE_NAMES = (
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
)
PASSING_CHECKS = {name: "pass" for name in RULE_NAMES}


def passing_payload(**overrides):
    checks = {**PASSING_CHECKS, **overrides}
    return {
        "checks": checks,
        "durations_seconds": {
            "python": 60,
            "bot": 20,
            "contracts": 30,
            "performance": 40,
            "supply_chain": 10,
            "affected_build": 20,
        },
        "live": {"requested": False, "trusted": False, "status": "not_requested"},
        "enforce": True,
    }


def test_all_checks_score_100_and_pass():
    result = evaluate(passing_payload())
    assert result.score == 100
    assert result.blockers == ()
    assert result.exit_code == 0
    assert "Performance: 15/15" in result.markdown


def test_hard_blocker_overrides_97_point_score():
    result = evaluate(passing_payload(gitleaks="fail"))
    assert result.score == 97
    assert "gitleaks" in result.blockers
    assert result.exit_code == 1


def test_material_performance_regression_loses_ten_without_hard_blocker():
    result = evaluate(passing_payload(library_performance="regression"))
    assert result.score == 90
    assert result.blockers == ()


def test_affected_build_not_applicable_keeps_points():
    result = evaluate(passing_payload(affected_build="not_applicable"))
    assert result.score == 100


def test_score_79_blocks():
    payload = passing_payload(ruff="fail", docs_contracts="fail", gitleaks="fail")
    payload["durations_seconds"]["python"] = 481
    result = evaluate(payload)
    assert result.score == 79
    assert result.exit_code == 1


def test_blocker_free_score_below_threshold_blocks():
    result = evaluate(
        passing_payload(
            ruff="fail", library_performance="regression", diff_hygiene="fail"
        )
    )
    assert result.score == 78
    assert result.blockers == ()
    assert result.exit_code == 1


def test_ruff_failure_deducts_ten_without_hard_blocker():
    result = evaluate(passing_payload(ruff="fail"))
    assert result.score == 90
    assert result.blockers == ()


def test_dependency_review_failure_blocks():
    result = evaluate(passing_payload(dependency_review="fail"))
    assert result.score == 98
    assert "dependency_review" in result.blockers


def test_missing_required_result_blocks():
    payload = passing_payload()
    del payload["checks"]["python_smoke"]
    result = evaluate(payload)
    assert result.score == 85
    assert "python_smoke" in result.blockers


def test_unexpected_not_applicable_blocks():
    result = evaluate(passing_payload(typescript="not_applicable"))
    assert result.score == 90
    assert "typescript" in result.blockers


@pytest.mark.parametrize(
    ("seconds", "score", "blocked"),
    [(480, 100, False), (481, 95, False), (600, 95, False), (601, 95, True)],
)
def test_shared_duration_boundaries(seconds, score, blocked):
    payload = passing_payload()
    payload["durations_seconds"]["python"] = seconds
    result = evaluate(payload)
    assert result.score == score
    assert ("duration" in result.blockers) is blocked


def test_slow_duration_loses_performance_category_points():
    payload = passing_payload()
    payload["durations_seconds"]["python"] = 481
    result = evaluate(payload)
    assert "Performance: 10/15" in result.markdown


def test_no_durations_loses_points_and_blocks():
    payload = passing_payload()
    payload["durations_seconds"] = {}
    result = evaluate(payload)
    assert result.score == 95
    assert "duration" in result.blockers


def test_one_missing_duration_loses_points_and_blocks():
    payload = passing_payload()
    del payload["durations_seconds"]["supply_chain"]
    result = evaluate(payload)
    assert result.score == 95
    assert "duration" in result.blockers


def test_trusted_requested_live_failure_blocks():
    payload = passing_payload()
    payload["live"] = {"requested": True, "trusted": True, "status": "fail"}
    result = evaluate(payload)
    assert result.score == 100
    assert "live_smoke" in result.blockers


def test_fork_live_request_is_not_applicable():
    payload = passing_payload()
    payload["live"] = {
        "requested": True,
        "trusted": False,
        "status": "not_applicable",
    }
    result = evaluate(payload)
    assert result.score == 100
    assert result.blockers == ()


def test_advisory_mode_exits_zero_and_reports_would_block():
    payload = passing_payload(gitleaks="fail")
    payload["enforce"] = False
    result = evaluate(payload)
    assert result.exit_code == 0
    assert "Would block: yes" in result.markdown


def test_markdown_contains_category_states_duration_blockers_score_and_verdict():
    result = evaluate(passing_payload(gitleaks="fail"))
    assert "Correctness: 35/35" in result.markdown
    assert "gitleaks: fail" in result.markdown
    assert "python: 60" in result.markdown
    assert "Blockers: gitleaks" in result.markdown
    assert "Score: 97/100" in result.markdown
    assert "Verdict: blocked" in result.markdown


def test_metrics_appear_in_json_and_markdown_without_changing_score(tmp_path):
    output = tmp_path / "score.json"
    summary = tmp_path / "summary.md"
    args = []
    for name in RULE_NAMES:
        args.extend(("--result", f"{name}=pass"))
    for name in (
        "python",
        "bot",
        "contracts",
        "performance",
        "supply_chain",
        "affected_build",
    ):
        args.extend(("--duration", f"{name}=60"))
    args.extend(
        (
            "--metric",
            "pagination_p95_ms=7.855",
            "--metric",
            "search_p95_ms=4.071",
            "--metric",
            "artists_p95_ms=6.161",
            "--output",
            str(output),
            "--summary",
            str(summary),
            "--enforce",
        )
    )
    assert main(args) == 0
    data = json.loads(output.read_text())
    assert data["score"] == 100
    assert data["metrics"] == {
        "artists_p95_ms": 6.161,
        "pagination_p95_ms": 7.855,
        "search_p95_ms": 4.071,
    }
    markdown = summary.read_text()
    assert "pagination_p95_ms: 7.855" in markdown
    assert "search_p95_ms: 4.071" in markdown
    assert "artists_p95_ms: 6.161" in markdown


@pytest.mark.parametrize(
    "args",
    [
        ["--result", "unknown=pass"],
        ["--result", "ruff=unexpected"],
        ["--duration", "python=not-a-number"],
        ["--duration", "unknown=1"],
        ["--metric", "unknown=1"],
        ["--result", "typescript=regression"],
        ["--result", "dependency_review=regression"],
        ["--result", "python_smoke=slow"],
    ],
)
def test_cli_rejects_invalid_input(args, capsys, tmp_path):
    assert main([*args, "--output", str(tmp_path / "score.json")]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_github_states_are_normalized(tmp_path):
    output = tmp_path / "score.json"
    args = []
    for name in RULE_NAMES:
        args.extend(("--result", f"{name}=success"))
    for name in (
        "python",
        "bot",
        "contracts",
        "performance",
        "supply_chain",
        "affected_build",
    ):
        args.extend(("--duration", f"{name}=1"))
    args.extend(("--output", str(output), "--enforce"))
    assert main(args) == 0
    assert json.loads(output.read_text())["checks"]["ruff"] == "pass"


def test_cancelled_required_result_is_missing_and_blocks():
    result = evaluate(passing_payload(typescript="cancelled"))
    assert "typescript" in result.blockers


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("typescript", "regression"),
        ("dependency_review", "regression"),
        ("python_smoke", "slow"),
    ],
)
def test_semantically_invalid_check_status_blocks(name, status):
    result = evaluate(passing_payload(**{name: status}))
    assert name in result.blockers
    assert result.exit_code == 1
