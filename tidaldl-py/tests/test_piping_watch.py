"""Tests for the Tidal piping watcher."""

import json
from pathlib import Path

from typer.testing import CliRunner

from tidal_dl.cli import app
from tidal_dl.piping_watch import (
    check_bundled_contract,
    check_gist_drift,
    check_live_probe,
    load_baseline,
    main,
    run_watch,
)


def test_bundled_clients_match_committed_baseline():
    findings = check_bundled_contract(load_baseline())

    assert findings == []


def test_bundled_contract_fails_when_preferred_is_not_first(tmp_path: Path):
    baseline = load_baseline()
    baseline["preferred_client_id"] = "zU4XHVVkc2tDPo4t"

    findings = check_bundled_contract(baseline)

    assert any(item.code == "preferred_not_first" for item in findings)


def _gist_remote_from_baseline(baseline, extra=None, valid_overrides=None):
    valid_overrides = valid_overrides or {}
    keys = []
    for item in baseline["gist_clients"]:
        client_id = item["client_id"]
        valid = valid_overrides.get(client_id, item["valid"])
        keys.append({"clientId": client_id, "valid": "True" if valid else "False"})
    keys.extend(extra or [])
    return {"version": "1", "keys": keys}


def test_gist_new_clients_are_a_warning():
    baseline = load_baseline()
    remote = _gist_remote_from_baseline(
        baseline,
        extra=[{"clientId": "brand-new-client", "valid": "True"}],
    )

    findings = check_gist_drift(baseline, remote)

    assert findings[0].severity == "warning"
    assert findings[0].code == "gist_new_clients"
    assert "brand-new-client" in findings[0].message


def test_gist_valid_flag_change_is_a_warning():
    baseline = load_baseline()
    remote = _gist_remote_from_baseline(baseline, valid_overrides={"zU4XHVVkc2tDPo4t": False})

    findings = check_gist_drift(baseline, remote)

    assert any(item.code == "gist_valid_flag_changed" for item in findings)


def test_gist_marks_preferred_invalid():
    baseline = load_baseline()
    baseline["preferred_bundled_only"] = False
    remote = _gist_remote_from_baseline(
        baseline,
        extra=[{"clientId": baseline["preferred_client_id"], "valid": "False"}],
    )

    findings = check_gist_drift(baseline, remote)

    assert any(item.code == "gist_preferred_invalid" for item in findings)


def test_current_gist_snapshot_is_quiet():
    baseline = load_baseline()

    assert check_gist_drift(baseline, _gist_remote_from_baseline(baseline)) == []


def test_live_probe_errors_when_preferred_client_drops_below_lossless():
    baseline = load_baseline()
    probe = {"status_code": 200, "audio_quality": "HIGH", "codec": "mp4a"}

    findings = check_live_probe(baseline, probe)

    assert findings[0].severity == "error"
    assert findings[0].code == "preferred_client_degraded"


def test_live_probe_accepts_flac_at_or_above_baseline():
    baseline = load_baseline()
    probe = {"status_code": 200, "audio_quality": "LOSSLESS", "codec": "flac"}

    assert check_live_probe(baseline, probe) == []


def test_run_watch_combines_gist_and_live_without_network():
    report = run_watch(
        check_gist=True,
        live_token="token",
        fetch_remote=lambda: _gist_remote_from_baseline(load_baseline()),
        probe_fn=lambda *_args, **_kwargs: {
            "status_code": 200,
            "audio_quality": "LOSSLESS",
            "codec": "flac",
        },
    )

    assert report.ok is True
    assert report.gist_client_ids == [item["client_id"] for item in load_baseline()["gist_clients"]]
    assert report.live_probe["audio_quality"] == "LOSSLESS"


def test_module_main_writes_json_report(tmp_path: Path, capsys):
    report_path = tmp_path / "piping.json"

    code = main(["--json", "--report", str(report_path)])

    assert code == 0
    payload = json.loads(report_path.read_text())
    assert payload["ok"] is True
    assert payload["preferred_client_id"] == "4N3n6Q1x95LL5K7p"
    assert "4N3n6Q1x95LL5K7p" in capsys.readouterr().out


def test_cli_piping_watch_is_registered():
    result = CliRunner().invoke(app, ["piping-watch", "--help"])

    assert result.exit_code == 0
    assert "Tidal OAuth" in result.output


def test_cli_token_refresh_is_registered():
    result = CliRunner().invoke(app, ["token-refresh", "--help"])

    assert result.exit_code == 0
    assert "without starting device login" in result.output
