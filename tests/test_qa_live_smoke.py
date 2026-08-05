import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import requests

from scripts import qa_live_smoke
from scripts.qa_live_smoke import Track, check_discord, check_tidal


class FakeResponse:
    def __init__(self, status_code: int, body: str = "") -> None:
        self.status_code = status_code
        self.text = body


class FakeSession:
    def __init__(self, *, logged_in: bool = True, search_result: object = None) -> None:
        self.logged_in = logged_in
        self.search_result = (
            {"tracks": [object()]} if search_result is None else search_result
        )
        self.calls: list[tuple[str, object]] = []

    def check_login(self) -> bool:
        self.calls.append(("check_login", None))
        return self.logged_in

    def search(self, query: str, *, models: list[type], limit: int) -> object:
        self.calls.append(("search", (query, models, limit)))
        return self.search_result


class FakeTidal:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.calls: list[tuple[str, object]] = []

    def login_token(self, *, quiet: bool) -> bool:
        self.calls.append(("login_token", quiet))
        return True


def test_tidal_check_restores_token_checks_login_and_searches_once() -> None:
    session = FakeSession()
    tidal = FakeTidal(session)

    result = check_tidal(lambda: tidal)

    assert result.status == "pass"
    assert tidal.calls == [("login_token", True)]
    assert session.calls == [
        ("check_login", None),
        ("search", ("Daft Punk", [Track], 1)),
    ]


def test_tidal_failed_login_and_empty_search_are_concise() -> None:
    failed_login = check_tidal(lambda: FakeTidal(FakeSession(logged_in=False)))
    empty_search = check_tidal(lambda: FakeTidal(FakeSession(search_result={})))

    assert asdict(failed_login) | {"latency_ms": 0.0} == {
        "service": "tidal",
        "status": "fail",
        "latency_ms": 0.0,
        "detail": "login failed",
    }
    assert empty_search.status == "fail"
    assert empty_search.detail == "search returned no results"


def test_tidal_exception_does_not_leak_exception_text() -> None:
    secret = "tidal-secret-in-error"

    def fail_factory() -> object:
        raise RuntimeError(secret)

    result = check_tidal(fail_factory)

    assert result.status == "fail"
    assert result.detail == "request failed"
    assert secret not in json.dumps(asdict(result))


def test_discord_check_is_read_only_and_secret_safe() -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    token = "do-not-print-me"

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append((url, kwargs))
        return FakeResponse(200, '{"id":"123","username":"music-dl"}')

    result = check_discord(token, get=fake_get)

    assert result.status == "pass"
    assert calls == [
        (
            "https://discord.com/api/v10/users/@me",
            {"headers": {"Authorization": f"Bot {token}"}, "timeout": 10},
        )
    ]
    serialized = json.dumps(asdict(result))
    assert token not in serialized
    assert "music-dl" not in serialized


def test_discord_missing_token_timeout_and_non_200_are_concise() -> None:
    missing = check_discord("")

    def timeout(*args: object, **kwargs: object) -> object:
        raise requests.Timeout("secret response body")

    timed_out = check_discord("token", get=timeout)
    rejected = check_discord(
        "token",
        get=lambda *args, **kwargs: FakeResponse(401, "secret response body"),
    )

    assert (missing.status, missing.detail) == ("fail", "missing DISCORD_TOKEN")
    assert (timed_out.status, timed_out.detail) == ("fail", "request timed out")
    assert (rejected.status, rejected.detail) == ("fail", "HTTP 401")
    assert "secret response body" not in json.dumps(
        [asdict(missing), asdict(timed_out), asdict(rejected)]
    )


def test_module_exposes_no_mutating_http_helpers() -> None:
    for method in ("post", "put", "patch", "delete"):
        assert not hasattr(qa_live_smoke, method)


def test_cli_missing_discord_token_writes_safe_failure(tmp_path: Path) -> None:
    output = tmp_path / "live.json"
    env = os.environ.copy()
    env.pop("DISCORD_TOKEN", None)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/qa_live_smoke.py",
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(output.read_text())
    assert set(payload) == {"services"}
    discord = next(item for item in payload["services"] if item["service"] == "discord")
    assert set(discord) == {"service", "status", "latency_ms", "detail"}
    assert discord["status"] == "fail"
    assert discord["detail"] == "missing DISCORD_TOKEN"
    assert completed.stderr == ""
