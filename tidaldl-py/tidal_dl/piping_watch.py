"""Watch Tidal OAuth client piping so a silent cap is caught before the next binary.

The Android Auto client used to advertise HiFi/Master and later started
returning HIGH/AAC. This module compares the bundled clients to a committed
baseline, diffs the public API-key gist, and optionally probes
playbackinfopostpaywall when a watch token is present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from tidal_dl.api import (
    API_KEYS_GIST_ID,
    bundled_api_keys,
    fetch_remote_api_keys,
)
from tidal_dl.constants import QUALITY_PROBE_TRACK_ID, REQUESTS_TIMEOUT_SEC, TIER_RANK

BASELINE_PATH = Path(__file__).with_name("piping_baseline.json")
PLAYBACKINFO_URL = "https://api.tidal.com/v1/tracks/{track_id}/playbackinfopostpaywall"
WATCH_TOKEN_ENV = "TIDAL_WATCH_ACCESS_TOKEN"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str


@dataclass
class PipingReport:
    findings: list[Finding]
    preferred_client_id: str
    bundled_client_ids: list[str]
    gist_client_ids: list[str] | None
    live_probe: dict[str, Any] | None

    @property
    def ok(self) -> bool:
        return not any(item.severity in {"warning", "error"} for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "preferred_client_id": self.preferred_client_id,
            "bundled_client_ids": self.bundled_client_ids,
            "gist_client_ids": self.gist_client_ids,
            "live_probe": self.live_probe,
            "findings": [asdict(item) for item in self.findings],
        }


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw.get("clients"):
        raise ValueError("piping baseline must be a JSON object with clients")
    return raw


def _quality_rank(quality: str | None) -> int | None:
    if not quality:
        return None
    return TIER_RANK.get(str(quality).upper())


def _normalize_quality(value: Any) -> str:
    return str(value or "").strip().upper()


def check_bundled_contract(baseline: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    bundled = bundled_api_keys()["keys"]
    bundled_ids = [key.get("clientId") or "" for key in bundled]
    expected_ids = [str(item["client_id"]) for item in baseline["clients"]]
    preferred = str(baseline["preferred_client_id"])

    if bundled_ids != expected_ids:
        findings.append(
            Finding(
                "error",
                "bundled_clients_drift",
                "Bundled Tidal clients do not match piping_baseline.json. "
                f"bundled={bundled_ids} baseline={expected_ids}",
            )
        )
    if not bundled_ids or bundled_ids[0] != preferred:
        findings.append(
            Finding(
                "error",
                "preferred_not_first",
                f"Preferred client {preferred} must be the first bundled key so new logins get FLAC.",
            )
        )
    if API_KEYS_GIST_ID != str(baseline.get("gist_id") or ""):
        findings.append(
            Finding(
                "error",
                "gist_id_mismatch",
                "API key gist id does not match the committed piping baseline.",
            )
        )
    return findings


def _gist_valid(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def check_gist_drift(baseline: dict[str, Any], remote: dict[str, Any] | None) -> list[Finding]:
    findings: list[Finding] = []
    if remote is None:
        findings.append(
            Finding("warning", "gist_unavailable", "Could not fetch the public Tidal API-key gist.")
        )
        return findings

    remote_keys = remote.get("keys") or []
    remote_by_id = {
        str(key.get("clientId") or ""): key
        for key in remote_keys
        if key.get("clientId")
    }
    known = {
        str(item["client_id"]): bool(item.get("valid"))
        for item in baseline.get("gist_clients") or []
        if item.get("client_id")
    }
    remote_ids = list(remote_by_id)
    new_ids = [client_id for client_id in remote_ids if client_id not in known]
    removed_ids = [client_id for client_id in known if client_id not in remote_by_id]
    if new_ids:
        findings.append(
            Finding(
                "warning",
                "gist_new_clients",
                "Public gist listed new Tidal clients: "
                f"{new_ids}. Probe them for FLAC and ship any winner with the next binary.",
            )
        )
    if removed_ids:
        findings.append(
            Finding(
                "warning",
                "gist_removed_clients",
                f"Public gist dropped clients {removed_ids}. Update piping_baseline.json after review.",
            )
        )
    flipped = [
        client_id
        for client_id, expected_valid in known.items()
        if client_id in remote_by_id and _gist_valid(remote_by_id[client_id].get("valid")) != expected_valid
    ]
    if flipped:
        findings.append(
            Finding(
                "warning",
                "gist_valid_flag_changed",
                f"Gist valid flags changed for {flipped}. This is how a silent client cap usually shows up.",
            )
        )

    preferred = str(baseline["preferred_client_id"])
    preferred_remote = remote_by_id.get(preferred)
    if preferred_remote is None and not baseline.get("preferred_bundled_only"):
        findings.append(
            Finding(
                "warning",
                "gist_missing_preferred",
                f"Gist no longer lists preferred client {preferred}. Keep it bundled until a replacement is proven.",
            )
        )
    elif preferred_remote is not None and not _gist_valid(preferred_remote.get("valid")):
        findings.append(
            Finding(
                "warning",
                "gist_preferred_invalid",
                f"Gist marks preferred client {preferred} invalid. Confirm live FLAC before the next release.",
            )
        )
    return findings


def probe_playbackinfo(
    access_token: str,
    *,
    track_id: str = QUALITY_PROBE_TRACK_ID,
    audio_quality: str = "HI_RES_LOSSLESS",
) -> dict[str, Any]:
    response = requests.get(
        PLAYBACKINFO_URL.format(track_id=track_id),
        params={
            "audioquality": audio_quality,
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUESTS_TIMEOUT_SEC,
    )
    payload: dict[str, Any]
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "status_code": response.status_code,
        "audio_quality": _normalize_quality(payload.get("audioQuality")),
        "codec": str(payload.get("codec") or payload.get("codecs") or "").lower(),
        "bit_depth": payload.get("bitDepth"),
        "sample_rate": payload.get("sampleRate"),
    }


def check_live_probe(baseline: dict[str, Any], probe: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    preferred = next(item for item in baseline["clients"] if item.get("role") == "preferred")
    expected_min = str(preferred["expected_min_quality"])
    delivered = str(probe.get("audio_quality") or "")
    if int(probe.get("status_code") or 0) >= 400:
        findings.append(
            Finding(
                "warning",
                "live_probe_http",
                f"playbackinfo returned HTTP {probe.get('status_code')}. Token may be expired or client-bound.",
            )
        )
        return findings
    delivered_rank = _quality_rank(delivered)
    expected_rank = _quality_rank(expected_min)
    if delivered_rank is None or expected_rank is None:
        findings.append(
            Finding("warning", "live_probe_unknown_quality", f"Live probe returned unranked quality {delivered!r}.")
        )
        return findings
    if delivered_rank < expected_rank:
        findings.append(
            Finding(
                "error",
                "preferred_client_degraded",
                f"Preferred client delivered {delivered} (codec {probe.get('codec') or 'unknown'}), "
                f"below baseline {expected_min}. Update api.py before the next binary.",
            )
        )
    codec = str(probe.get("codec") or "")
    if delivered_rank >= _quality_rank("LOSSLESS") and codec and "flac" not in codec and "mqa" not in codec:
        findings.append(
            Finding(
                "warning",
                "lossless_without_flac",
                f"Live probe delivered {delivered} with codec {codec}, not flac.",
            )
        )
    return findings


def run_watch(
    *,
    check_gist: bool = False,
    live_token: str | None = None,
    baseline_path: Path = BASELINE_PATH,
    fetch_remote=fetch_remote_api_keys,
    probe_fn=probe_playbackinfo,
) -> PipingReport:
    baseline = load_baseline(baseline_path)
    findings = check_bundled_contract(baseline)
    bundled_ids = [key.get("clientId") or "" for key in bundled_api_keys()["keys"]]
    gist_ids: list[str] | None = None
    live_probe: dict[str, Any] | None = None

    if check_gist:
        remote = fetch_remote()
        if remote is not None:
            gist_ids = [str(key.get("clientId") or "") for key in remote.get("keys", []) if key.get("clientId")]
        findings.extend(check_gist_drift(baseline, remote))

    token = (live_token or os.environ.get(WATCH_TOKEN_ENV) or "").strip()
    if token:
        track_id = str(baseline.get("probe_track_id") or QUALITY_PROBE_TRACK_ID)
        live_probe = probe_fn(token, track_id=track_id)
        findings.extend(check_live_probe(baseline, live_probe))

    return PipingReport(
        findings=findings,
        preferred_client_id=str(baseline["preferred_client_id"]),
        bundled_client_ids=bundled_ids,
        gist_client_ids=gist_ids,
        live_probe=live_probe,
    )


def format_report(report: PipingReport) -> str:
    if report.ok:
        lines = ["Tidal piping watch: ok"]
    else:
        lines = ["Tidal piping watch: drift detected"]
    lines.append(f"preferred: {report.preferred_client_id}")
    lines.append(f"bundled: {', '.join(report.bundled_client_ids)}")
    if report.gist_client_ids is not None:
        lines.append(f"gist: {', '.join(report.gist_client_ids) or '(empty)'}")
    if report.live_probe:
        probe = report.live_probe
        lines.append(
            "live: "
            f"{probe.get('audio_quality') or 'unknown'} "
            f"codec={probe.get('codec') or 'unknown'} "
            f"http={probe.get('status_code')}"
        )
    for finding in report.findings:
        lines.append(f"{finding.severity}: {finding.code}: {finding.message}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch Tidal OAuth client piping for silent quality caps.")
    parser.add_argument("--gist", action="store_true", help="Fetch and diff the public API-key gist.")
    parser.add_argument("--live", action="store_true", help=f"Probe playbackinfo when {WATCH_TOKEN_ENV} is set.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print a machine-readable report.")
    parser.add_argument("--report", type=Path, help="Write the JSON report to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get(WATCH_TOKEN_ENV) if args.live else None
    report = run_watch(check_gist=args.gist, live_token=token)
    text = json.dumps(report.to_dict(), indent=2) if args.as_json else format_report(report)
    print(text)
    if args.report:
        args.report.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
