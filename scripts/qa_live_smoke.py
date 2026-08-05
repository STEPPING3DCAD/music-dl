"""Read-only live credential checks for Tidal and Discord."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from tidalapi.media import Track

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tidaldl-py"))

from tidal_dl.config import Tidal

DISCORD_ME_URL = "https://discord.com/api/v10/users/@me"


@dataclass(frozen=True)
class ServiceResult:
    service: str
    status: str
    latency_ms: float
    detail: str


def _result(service: str, status: str, started: float, detail: str) -> ServiceResult:
    return ServiceResult(
        service, status, round((time.perf_counter() - started) * 1000, 3), detail
    )


def check_tidal(tidal_factory: Callable[[], object] = Tidal) -> ServiceResult:
    started = time.perf_counter()
    try:
        tidal: Any = tidal_factory()
        tidal.login_token(quiet=True)
        session = tidal.session
        if not session.check_login():
            return _result("tidal", "fail", started, "login failed")
        search_result = session.search("Daft Punk", models=[Track], limit=1)
        found = (
            any(search_result.values())
            if isinstance(search_result, dict)
            else bool(search_result)
        )
        if not found:
            return _result("tidal", "fail", started, "search returned no results")
    except Exception:  # noqa: BLE001 - sanitize every service-boundary failure
        return _result("tidal", "fail", started, "request failed")
    return _result("tidal", "pass", started, "authenticated search succeeded")


def check_discord(
    token: str, get: Callable[..., object] = requests.get
) -> ServiceResult:
    started = time.perf_counter()
    if not token:
        return _result("discord", "fail", started, "missing DISCORD_TOKEN")
    try:
        response: Any = get(
            DISCORD_ME_URL,
            headers={"Authorization": f"Bot {token}"},
            timeout=10,
        )
    except requests.Timeout:
        return _result("discord", "fail", started, "request timed out")
    except Exception:  # noqa: BLE001 - sanitize every injected-client failure
        return _result("discord", "fail", started, "request failed")
    if response.status_code != 200:
        return _result("discord", "fail", started, f"HTTP {response.status_code}")
    return _result("discord", "pass", started, "authenticated request succeeded")


def _write_results(output: Path, results: list[ServiceResult]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"services": [asdict(result) for result in results]}, indent=2)
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/qa/live.json"))
    args = parser.parse_args(argv)

    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        results = [check_discord(token)]
    else:
        results = [check_tidal(), check_discord(token)]
    _write_results(args.output, results)
    return int(any(result.status != "pass" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
