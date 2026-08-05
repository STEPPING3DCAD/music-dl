"""Score pull request QA results from raw CI states."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

RULES = {
    "python_smoke": ("Correctness", 15, {"fail"}),
    "bun_tests": ("Correctness", 10, {"fail"}),
    "release_installers": ("Correctness", 10, {"fail"}),
    "typescript": ("Static quality", 10, {"fail"}),
    "ruff": ("Static quality", 10, set()),
    "security_tests": ("Security", 10, {"fail"}),
    "gitleaks": ("Security", 3, {"fail"}),
    "dependency_review": ("Security", 2, {"fail"}),
    "library_performance": ("Performance", 10, {"fail"}),
    "uv_build": ("Build/packaging", 5, {"fail"}),
    "affected_build": ("Build/packaging", 5, {"fail"}),
    "docs_contracts": ("Change hygiene", 3, set()),
    "diff_hygiene": ("Change hygiene", 2, set()),
}

_STATUS_ALIASES = {
    "success": "pass",
    "failure": "fail",
    "skipped": "missing",
    "cancelled": "missing",
}
_CHECK_STATUSES = {"pass", "fail", "regression", "slow", "missing", "not_applicable"}
_LIVE_STATUSES = {"pass", "fail", "missing", "not_requested", "not_applicable"}
_METRIC_NAMES = {"pagination_p95_ms", "search_p95_ms", "artists_p95_ms"}


@dataclass(frozen=True)
class Evaluation:
    score: int
    blockers: tuple[str, ...]
    markdown: str
    exit_code: int


def _normalize_status(value: object, allowed: set[str]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"invalid status: {value!r}")
    status = _STATUS_ALIASES.get(value, value)
    if status not in allowed:
        raise ValueError(f"invalid status: {value}")
    return status


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"invalid {label}: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid {label}: {value!r}")
    return number


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _render_markdown(data: dict[str, object]) -> str:
    lines = ["## Pull request QA", "", "### Category totals", ""]
    categories = data["categories"]
    assert isinstance(categories, dict)
    for category, totals in categories.items():
        lines.append(f"- {category}: {totals['earned']}/{totals['possible']}")

    lines.extend(("", "### Raw states", ""))
    checks = data["checks"]
    assert isinstance(checks, dict)
    lines.extend(f"- {name}: {status}" for name, status in checks.items())

    lines.extend(("", "### Duration (seconds)", ""))
    durations = data["durations_seconds"]
    assert isinstance(durations, dict)
    if durations:
        lines.extend(
            f"- {name}: {_format_number(seconds)}"
            for name, seconds in durations.items()
        )
    else:
        lines.append("- none reported")
    lines.append(f"- shared points: {data['duration_points']}/5")

    metrics = data["metrics"]
    assert isinstance(metrics, dict)
    if metrics:
        lines.extend(("", "### Performance metrics", ""))
        lines.extend(
            f"- {name}: {_format_number(value)}" for name, value in metrics.items()
        )

    blockers = data["blockers"]
    assert isinstance(blockers, list)
    blockers_text = ", ".join(blockers) if blockers else "none"
    lines.extend(
        (
            "",
            f"- Live smoke: {data['live_status']}",
            f"- Blockers: {blockers_text}",
            f"- Score: {data['score']}/100",
            f"- Would block: {'yes' if data['would_block'] else 'no'}",
            f"- Verdict: {data['verdict']}",
        )
    )
    return "\n".join(lines) + "\n"


def _evaluate(payload: dict[str, object]) -> tuple[Evaluation, dict[str, object]]:
    raw_checks = payload.get("checks", {})
    if not isinstance(raw_checks, dict):
        raise TypeError("checks must be an object")
    unknown_checks = set(raw_checks) - set(RULES)
    if unknown_checks:
        raise ValueError(f"unknown result: {min(unknown_checks)}")

    checks: dict[str, str] = {}
    blockers: list[str] = []
    score = 0
    categories: dict[str, dict[str, int]] = {}
    for name, (category, points, hard_failures) in RULES.items():
        totals = categories.setdefault(category, {"earned": 0, "possible": 0})
        totals["possible"] += points
        status = _normalize_status(raw_checks.get(name, "missing"), _CHECK_STATUSES)
        checks[name] = status
        if status == "not_applicable" and name != "affected_build":
            blockers.append(name)
        elif status in {"pass", "not_applicable"}:
            score += points
            totals["earned"] += points
        if status == "missing" or status in hard_failures:
            blockers.append(name)

    raw_durations = payload.get("durations_seconds", {})
    if not isinstance(raw_durations, dict):
        raise TypeError("durations_seconds must be an object")
    durations = {
        str(name): _number(seconds, f"duration for {name}")
        for name, seconds in raw_durations.items()
    }
    longest_duration = max(durations.values(), default=0.0)
    duration_points = 5 if longest_duration <= 480 else 0
    score += duration_points
    if longest_duration > 600:
        blockers.append("duration")

    raw_live = payload.get("live", {})
    if not isinstance(raw_live, dict):
        raise TypeError("live must be an object")
    live_requested = raw_live.get("requested", False) is True
    live_trusted = raw_live.get("trusted", False) is True
    default_live_status = "missing" if live_requested else "not_requested"
    live_status = _normalize_status(
        raw_live.get("status", default_live_status), _LIVE_STATUSES
    )
    trusted_live_failed = live_requested and live_trusted and live_status != "pass"
    fork_live_ran = (
        live_requested and not live_trusted and live_status != "not_applicable"
    )
    invalid_not_applicable = live_status == "not_applicable" and not (
        live_requested and not live_trusted
    )
    if trusted_live_failed or fork_live_ran or invalid_not_applicable:
        blockers.append("live_smoke")

    raw_metrics = payload.get("metrics", {})
    if not isinstance(raw_metrics, dict):
        raise TypeError("metrics must be an object")
    metrics = {
        name: _number(value, f"metric {name}")
        for name, value in raw_metrics.items()
        if name in _METRIC_NAMES
    }

    blockers = list(dict.fromkeys(blockers))
    would_block = bool(blockers) or score < 80
    enforce = payload.get("enforce", False) is True
    verdict = (
        "blocked" if would_block else "ready" if score >= 90 else "ready_with_debt"
    )
    data: dict[str, object] = {
        "score": score,
        "checks": checks,
        "categories": categories,
        "durations_seconds": durations,
        "duration_points": duration_points,
        "metrics": dict(sorted(metrics.items())),
        "live_status": live_status,
        "blockers": blockers,
        "would_block": would_block,
        "enforced": enforce,
        "verdict": verdict,
    }
    markdown = _render_markdown(data)
    evaluation = Evaluation(
        score=score,
        blockers=tuple(blockers),
        markdown=markdown,
        exit_code=1 if enforce and would_block else 0,
    )
    return evaluation, data


def evaluate(payload: dict[str, object]) -> Evaluation:
    return _evaluate(payload)[0]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _Parser(description=__doc__)
    parser.add_argument("--result", action="append", default=[], metavar="NAME=STATUS")
    parser.add_argument(
        "--duration", action="append", default=[], metavar="NAME=SECONDS"
    )
    parser.add_argument("--metric", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--live-requested", action="store_true")
    parser.add_argument("--live-trusted", action="store_true")
    parser.add_argument("--live-status", default="not_requested")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/qa/score.json"))
    return parser.parse_args(argv)


def _pairs(values: list[str], kind: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid {kind}: {value}")
        name, item = value.split("=", 1)
        if not name or not item:
            raise ValueError(f"invalid {kind}: {value}")
        pairs[name] = item
    return pairs


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        checks = _pairs(args.result, "result")
        unknown_checks = set(checks) - set(RULES)
        if unknown_checks:
            raise ValueError(f"unknown result: {min(unknown_checks)}")

        duration_values = _pairs(args.duration, "duration")
        durations = {
            name: _number(value, f"duration for {name}")
            for name, value in duration_values.items()
        }

        metric_values = _pairs(args.metric, "metric")
        unknown_metrics = set(metric_values) - _METRIC_NAMES
        if unknown_metrics:
            raise ValueError(f"unknown metric: {min(unknown_metrics)}")
        metrics = {
            name: _number(value, f"metric {name}")
            for name, value in metric_values.items()
        }

        payload: dict[str, object] = {
            "checks": checks,
            "durations_seconds": durations,
            "metrics": metrics,
            "live": {
                "requested": args.live_requested,
                "trusted": args.live_trusted,
                "status": args.live_status,
            },
            "enforce": args.enforce,
        }
        evaluation, data = _evaluate(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

        summary = args.summary
        if summary is None and os.environ.get("GITHUB_ACTIONS") == "true":
            summary_value = os.environ.get("GITHUB_STEP_SUMMARY")
            summary = Path(summary_value) if summary_value else None
        if summary is not None:
            summary.parent.mkdir(parents=True, exist_ok=True)
            with summary.open("a") as stream:
                stream.write(evaluation.markdown)
        return evaluation.exit_code
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
