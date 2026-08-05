"""Tests for the deterministic LibraryDB performance probe."""

import json

import pytest

from scripts.qa_performance import classify, main, percentile_95


def test_absolute_ceiling_blocks():
    result = classify(
        {"pagination": 21.0, "search": 4.0, "artists": 6.0},
        baseline=None,
    )

    assert result.status == "fail"


def test_missing_baseline_is_calibrating_but_passes_absolute_limits():
    result = classify(
        {"pagination": 8.0, "search": 4.0, "artists": 6.0},
        baseline=None,
    )

    assert result.status == "pass"
    assert result.relative_status == "calibrating"


def test_material_relative_regression_requires_percent_and_delta():
    result = classify(
        {"pagination": 11.0, "search": 4.0, "artists": 6.0},
        baseline={"pagination": 8.0, "search": 4.0, "artists": 6.0},
    )

    assert result.status == "regression"
    assert result.relative_status == "regression"


def test_relative_change_under_two_ms_does_not_regress():
    result = classify(
        {"pagination": 5.5, "search": 4.0, "artists": 6.0},
        baseline={"pagination": 4.0, "search": 4.0, "artists": 6.0},
    )

    assert result.status == "pass"
    assert result.relative_status == "pass"


def test_percentile_95_uses_nearest_rank_for_25_samples():
    assert percentile_95(range(1, 26)) == 24.0


def test_serialized_result_contains_metrics_but_no_fixture_paths():
    result = classify(
        {"pagination": 8.12349, "search": 4.0, "artists": 6.0},
        baseline=None,
    )

    serialized = json.dumps(result.as_dict())

    assert json.loads(serialized)["p95_ms"] == {
        "pagination": 8.123,
        "search": 4.0,
        "artists": 6.0,
    }
    assert "library.db" not in serialized
    assert "/tmp" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"pagination": 8.0, "search": 4.0},
        {"pagination": 8.0, "search": 4.0, "artists": 6.0, "extra": 1.0},
        {"pagination": 8.0, "search": "fast", "artists": 6.0},
    ],
)
def test_invalid_baseline_exits_two_without_running_probe(tmp_path, capsys, payload):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(["--baseline", str(baseline)])

    assert exit_code == 2
    assert capsys.readouterr().err == "error: invalid performance baseline\n"
