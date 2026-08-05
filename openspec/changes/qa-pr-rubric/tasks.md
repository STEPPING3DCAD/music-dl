# PR QA Rubric Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one advisory pull-request QA workflow that reports a risk-weighted score out of 100, hard-blocker verdicts, deterministic performance evidence, and protected opt-in live smoke within a 10-minute execution budget.

**Architecture:** Existing checks remain their own commands. Parallel GitHub Actions jobs collect named outcomes and durations; `scripts/qa_score.py` alone owns weights, blocker rules, and Markdown verdicts. Separate standard-library scripts measure `LibraryDB` performance and perform mutation-free live checks. Initial workflow is advisory; enforcement and CI-relative baselines wait for five real PR runs.

**Tech Stack:** Python 3.12, pytest, uv, Ruff 0.16.1, Bun, TypeScript, GitHub Actions, Gitleaks, SQLite, requests, tidalapi.

---

## File map

- Modify `apps/discord-bot/src/commands.ts`: repair existing Discord builder type errors only.
- Modify `tidaldl-py/pyproject.toml` and `tidaldl-py/uv.lock`: pin Ruff through uv.
- Create `scripts/qa_score.py`: fixed rubric, hard blockers, advisory/enforced exit policy, Markdown summary.
- Create `tests/test_qa_score.py`: score arithmetic and failure-semantics tests.
- Create `scripts/qa_performance.py`: deterministic 10,000-track `LibraryDB` benchmark and JSON result.
- Create `tests/test_qa_performance.py`: percentile, absolute ceiling, calibration, and relative-regression tests.
- Create `scripts/qa_live_smoke.py`: read-only Tidal and Discord credential checks.
- Create `tests/test_qa_live_smoke.py`: injected fake-service tests proving mutation-free calls and secret-safe errors.
- Rename `.github/workflows/gui-smoke.yml` to `.github/workflows/qa.yml`: parallel checks, outcome collection, protected live job, final score.
- Create `tests/test_qa_workflow.py`: textual workflow contract tests without adding a YAML dependency.
- Modify `README.md` and `CONTRIBUTING.md`: local commands, score meanings, rollout, and live-smoke safety.
- Create `scripts/qa_performance_baseline.json` only after five advisory CI runs; do not invent baseline values during implementation.
- Update this file as tasks complete and record five-run calibration evidence in the final table.

## 1. Repair baseline typecheck and pin Ruff

**Files:**

- Modify: `apps/discord-bot/src/commands.ts`
- Modify: `tidaldl-py/pyproject.toml`
- Modify: `tidaldl-py/uv.lock`

- [ ] 1.1 Run the existing failing typecheck.

Run:

```bash
cd apps/discord-bot && bun run typecheck
```

Expected: FAIL at `addPlaylistNameOption` because `ReturnType<SlashCommandBuilder["addSubcommand"]>` resolves to the parent builder rather than `SlashCommandSubcommandBuilder`.

- [ ] 1.2 Replace the incorrect derived type with Discord's exported subcommand-builder type.

Minimal change:

```ts
import {
  MessageFlags,
  SlashCommandBuilder,
  type ChatInputCommandInteraction,
  type GuildMember,
  type SlashCommandSubcommandBuilder,
} from "discord.js";

function addPlaylistNameOption(builder: SlashCommandSubcommandBuilder): void {
  builder.addStringOption((option) =>
    option
      .setName(PLAYLIST_NAME_OPTION.name)
      .setDescription(PLAYLIST_NAME_OPTION.description)
      .setRequired(true),
  );
}
```

- [ ] 1.3 Verify typecheck and existing bot behavior.

Run:

```bash
cd apps/discord-bot && bun run typecheck && bun test
```

Expected: typecheck exit 0; all existing Bun tests pass.

- [ ] 1.4 Pin Ruff through uv; never use bare pip.

Run:

```bash
uv add --project tidaldl-py --dev 'ruff==0.16.1'
```

Expected: `tidaldl-py/pyproject.toml` and `tidaldl-py/uv.lock` change; no runtime dependency changes.

- [ ] 1.5 Verify a green legacy-safe floor without modifying source.

Run:

```bash
uv run --project tidaldl-py ruff check --no-fix --select E9,F63,F7,F82 \
  tidaldl-py/tidal_dl tidaldl-py/tests scripts tests
```

Expected: `All checks passed!` Existing broader Ruff debt remains visible but is not mass-fixed. PR workflow later runs configured Ruff against added/modified Python files only.

- [ ] 1.6 Commit baseline repair.

```bash
git add apps/discord-bot/src/commands.ts tidaldl-py/pyproject.toml tidaldl-py/uv.lock
git commit -m "fix: restore static quality baseline"
```

## 2. Build score engine with TDD

**Files:**

- Create: `tests/test_qa_score.py`
- Create: `scripts/qa_score.py`

The scorer owns this immutable mapping; workflow YAML supplies statuses, never points:

```python
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
```

`pass` and explicitly allowed `not_applicable` earn full points. `regression`, `slow`, and `fail` earn zero. Any missing required result blocks. `affected_build` is the only scored check allowed to be `not_applicable`. Duration is computed from job seconds: all jobs `<=480` earn 5; any job `481..600` earns zero without its own blocker; any job `>600` blocks. A `library_performance=regression` loses 10 without blocking; `fail` means absolute ceiling breach and blocks.

- [ ] 2.1 Write `tests/test_qa_score.py` with a complete passing payload helper.

```python
PASSING_CHECKS = {name: "pass" for name in RULE_NAMES}

def passing_payload(**overrides):
    checks = {**PASSING_CHECKS, **overrides}
    return {
        "checks": checks,
        "durations_seconds": {"python": 60, "bot": 20, "contracts": 30},
        "live": {"requested": False, "trusted": False, "status": "not_requested"},
        "enforce": True,
    }

def test_all_checks_score_100_and_pass():
    result = evaluate(passing_payload())
    assert result.score == 100
    assert result.blockers == []
    assert result.exit_code == 0

def test_hard_blocker_overrides_97_point_score():
    result = evaluate(passing_payload(gitleaks="fail"))
    assert result.score == 97
    assert "gitleaks" in result.blockers
    assert result.exit_code == 1

def test_material_performance_regression_loses_ten_without_hard_blocker():
    result = evaluate(passing_payload(library_performance="regression"))
    assert result.score == 90
    assert result.blockers == []

def test_affected_build_not_applicable_keeps_points():
    result = evaluate(passing_payload(affected_build="not_applicable"))
    assert result.score == 100
```

Also cover: score 79 blocks; Ruff failure deducts 10 without hard blocker; high-severity dependency failure blocks; missing required result blocks; unexpected `not_applicable` blocks; shared duration 5/0/block boundaries; trusted requested live failure blocks; fork live request is `not_applicable`; advisory mode returns exit 0 while reporting `would_block`; Markdown contains category totals, raw states, duration, blockers, score, and verdict.

Add one metric test proving supplied `pagination_p95_ms`, `search_p95_ms`, and `artists_p95_ms` values appear in JSON and Markdown without affecting score arithmetic.

- [ ] 2.2 Run scorer tests to verify red state.

Run:

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_score.py -q
```

Expected: FAIL because `scripts.qa_score` does not exist.

- [ ] 2.3 Implement the smallest score API in `scripts/qa_score.py`.

Required public surface:

```python
@dataclass(frozen=True)
class Evaluation:
    score: int
    blockers: tuple[str, ...]
    markdown: str
    exit_code: int

def evaluate(payload: dict[str, object]) -> Evaluation: ...
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

CLI inputs:

```text
--result NAME=STATUS       repeatable
--duration NAME=SECONDS    repeatable
--metric NAME=VALUE        repeatable diagnostic measurement; never scored directly
--live-requested
--live-trusted
--live-status STATUS
--enforce                  absent during advisory phase
--summary PATH             append Markdown; use $GITHUB_STEP_SUMMARY in CI
--output PATH              default output/qa/score.json
```

Implementation rules:

- Validate unknown names/statuses and malformed durations with a concise `error:` message and exit 2.
- Normalize GitHub `success/failure/skipped/cancelled` to `pass/fail/missing/missing`.
- Treat absent required results as `missing`; never silently pass them.
- Restrict `not_applicable` to `affected_build` and untrusted fork live smoke.
- Create output parent directories with `Path.mkdir(parents=True, exist_ok=True)`.
- Never include environment values or secrets in JSON/Markdown.
- Preserve only allow-listed numeric metrics (`pagination_p95_ms`, `search_p95_ms`, `artists_p95_ms`) for calibration evidence.
- In advisory mode, preserve `would_block=true` but return exit 0.

- [ ] 2.4 Run focused tests and CLI self-check.

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_score.py -q
uv run --project tidaldl-py python scripts/qa_score.py --help
```

Expected: scorer tests pass; help exits 0.

- [ ] 2.5 Commit score engine.

```bash
git add scripts/qa_score.py tests/test_qa_score.py
git commit -m "feat: add pull request QA scorer"
```

## 3. Add deterministic performance probe with TDD

**Files:**

- Create: `tests/test_qa_performance.py`
- Create: `scripts/qa_performance.py`
- Later create after calibration: `scripts/qa_performance_baseline.json`

- [ ] 3.1 Write pure classification tests before any real timing test.

```python
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
```

Also test p95 indexing for 25 sorted samples, a >25% change with <=2 ms delta does not regress, and output contains no fixture paths.

- [ ] 3.2 Run performance tests to verify red state.

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_performance.py -q
```

Expected: FAIL because `scripts.qa_performance` does not exist.

- [ ] 3.3 Implement `scripts/qa_performance.py` using existing `LibraryDB`.

Required public surface:

```python
ABSOLUTE_MS = {"pagination": 20.0, "search": 15.0, "artists": 20.0}

def percentile_95(samples_ms: Sequence[float]) -> float: ...
def measure(operation: Callable[[], object], iterations: int = 25) -> float: ...
def build_fixture(path: Path, tracks: int = 10_000) -> LibraryDB: ...
def classify(measurements: dict[str, float], baseline: dict[str, float] | None) -> ProbeResult: ...
def run_probe() -> dict[str, float]: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

CLI accepts optional `--baseline PATH`. When absent, relative status is `calibrating`. When present, load exactly the three numeric baseline keys or exit 2 with a concise configuration error.

Time only 25 warm calls to:

```python
db.tracks_page(limit=50, offset=5000)
db.tracks_page(query="Track 9999", limit=50, offset=0)
db.artists_page(limit=50, offset=0)
```

Exclude database creation and 10,000 inserts. Emit `status`, `relative_status`, rounded p95 values, and ceiling values to `--output` (default `output/qa/performance.json`). Exit 1 only for absolute failure; relative regression remains machine-readable for scorer.

- [ ] 3.4 Verify tests and one real local probe.

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_performance.py -q
uv run --project tidaldl-py python scripts/qa_performance.py --output output/qa/performance.json
```

Expected: tests pass; local probe exits 0; JSON has three p95 measurements. Do not encode local measurements as CI baselines.

- [ ] 3.5 Commit deterministic probe.

```bash
git add scripts/qa_performance.py tests/test_qa_performance.py
git commit -m "feat: add deterministic library performance probe"
```

## 4. Add mutation-free live smoke with TDD

**Files:**

- Create: `tests/test_qa_live_smoke.py`
- Create: `scripts/qa_live_smoke.py`

- [ ] 4.1 Write injected-service tests.

Tests must prove:

- Tidal calls only token restore, `check_login()`, and one fixed one-result search.
- Discord calls only `GET https://discord.com/api/v10/users/@me` with a 10-second timeout.
- No POST/PUT/PATCH/DELETE helper exists.
- Missing `DISCORD_TOKEN`, failed Tidal login, HTTP timeout, and non-200 Discord response return concise failures.
- Output reports service, status, and latency only; token values and response bodies never appear.

Representative test:

```python
def test_discord_check_is_read_only_and_secret_safe():
    calls = []
    token = "do-not-print-me"

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"id": "123", "username": "music-dl"})

    result = check_discord(token, get=fake_get)

    assert result.status == "pass"
    assert calls[0][0] == "https://discord.com/api/v10/users/@me"
    assert calls[0][1]["timeout"] == 10
    assert token not in json.dumps(asdict(result))
```

- [ ] 4.2 Run live-smoke tests to verify red state.

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_live_smoke.py -q
```

Expected: FAIL because `scripts.qa_live_smoke` does not exist.

- [ ] 4.3 Implement `scripts/qa_live_smoke.py` with dependency injection at service boundaries.

Required public surface:

```python
@dataclass(frozen=True)
class ServiceResult:
    service: str
    status: str
    latency_ms: float
    detail: str

def check_tidal(tidal_factory: Callable[[], object] = Tidal) -> ServiceResult: ...
def check_discord(token: str, get: Callable[..., object] = requests.get) -> ServiceResult: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Tidal flow: instantiate existing `Tidal`, call `login_token(quiet=True)`, require `session.check_login()`, then run `session.search("Daft Punk", models=[Track], limit=1)`. Discord flow: one bot-authenticated GET to `/users/@me`. Write JSON to `--output` (default `output/qa/live.json`). Return 1 when either service fails. Never print exception representations that could contain headers or tokens.

- [ ] 4.4 Verify unit tests; do not run live credentials during ordinary local tests.

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_live_smoke.py -q
```

Expected: all tests pass without network access.

- [ ] 4.5 Commit live-smoke helper.

```bash
git add scripts/qa_live_smoke.py tests/test_qa_live_smoke.py
git commit -m "feat: add read-only live service smoke"
```

## 5. Replace GUI smoke workflow with advisory QA workflow

**Files:**

- Create: `tests/test_qa_workflow.py`
- Rename: `.github/workflows/gui-smoke.yml` -> `.github/workflows/qa.yml`

- [ ] 5.1 Write workflow contract tests before renaming or editing workflow.

Read workflow as text. Assert all of these exact contracts:

```python
WORKFLOW = ROOT / ".github" / "workflows" / "qa.yml"

def test_qa_workflow_has_safe_triggers_and_permissions():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target" not in text
    assert "pull_request:" in text
    assert "types: [opened, synchronize, reopened, labeled]" in text
    assert "contents: read" in text
    assert "pull-requests: read" in text
    assert "fetch-depth: 0" in text

def test_gitleaks_is_commit_pinned_and_receives_no_secret():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "GITLEAKS_LICENSE" not in text

def test_live_job_is_internal_labelled_and_protected():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "qa-live" in text
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text
    assert "environment: qa-live" in text

def test_final_qa_always_aggregates():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: always()" in text
    assert "scripts/qa_score.py" in text
    assert "GITHUB_STEP_SUMMARY" in text
```

Also assert: every checkout that computes a base/head diff or scans commits uses `fetch-depth: 0`; job timeout is 10 minutes; Python uses uv; bot uses Bun; Ruff uses `--no-fix`; performance probe runs; both Gitleaks and dependency-review action steps use `continue-on-error: true`; dependency review fails at `high`; affected build has explicit path rules; final scorer is advisory without `--enforce`; live token file is created under `$RUNNER_TEMP`, permission `600`, and removed in `if: always()` cleanup.

- [ ] 5.2 Run workflow tests to verify red state.

```bash
uv run --project tidaldl-py --extra test python -m pytest tests/test_qa_workflow.py -q
```

Expected: FAIL because `.github/workflows/qa.yml` does not exist.

- [ ] 5.3 Rename existing workflow and preserve its current GUI/API smoke command as the `python_smoke` check.

```bash
git mv .github/workflows/gui-smoke.yml .github/workflows/qa.yml
```

Set workflow name `qa`; trigger only PRs targeting `master`, including the `labeled` event. Use top-level read-only permissions. Do not keep duplicate push coverage; existing edge workflow already validates `master` pushes.

Use `actions/checkout` with `fetch-depth: 0` for every job that computes the PR base/head diff or scans the PR commit range. This is required for both changed-path selection and Gitleaks history.

- [ ] 5.4 Add parallel outcome-producing jobs with `timeout-minutes: 10`.

Jobs and exact commands:

| Job | Scored outputs | Commands |
|---|---|---|
| `python` | `python_smoke`, `ruff`, `security_tests`, `uv_build`, duration | Existing GUI/API pytest selection; legacy-safe Ruff plus configured Ruff on changed Python files using `--no-fix`; `test_gui_security.py test_bot_api.py test_bot_control_api.py` plus root `tests/test_qa_workflow.py`; `uv build --project tidaldl-py` |
| `bot` | `bun_tests`, `typescript`, duration | `bun install --frozen-lockfile`; `bun test`; `bun run typecheck` |
| `contracts` | `release_installers`, `docs_contracts`, `diff_hygiene`, duration | Root Python release tests; behavioral installer scripts; documentation/workflow scripts; `git diff --check` plus tracked-junk check |
| `performance` | `library_performance`, `pagination_p95_ms`, `search_p95_ms`, `artists_p95_ms`, duration | `scripts/qa_performance.py --output "$RUNNER_TEMP/performance.json"`; map JSON `pass/regression/fail` and all three numeric p95 values into named job outputs |
| `supply_chain` | `gitleaks`, `dependency_review`, duration | Commit-pinned Gitleaks with `GITHUB_TOKEN: ${{ github.token }}`; official dependency review with `fail-on-severity: high`; both action steps set `continue-on-error: true` so either failure cannot suppress the other result |
| `affected_build` | `affected_build`, duration | Explicit base/head path diff; `cargo check`, Docker build, and/or existing-convention `bun install` only when matching paths change; otherwise emit `not_applicable` |

Each command check and third-party action check uses `continue-on-error: true`. A final `if: always()` step in each job converts step outcomes into named job outputs and emits elapsed execution seconds. Setup failure leaves outputs missing; scorer hard-blocks missing required evidence. Workflow security-contract failure feeds the hard-blocking `security_tests` result, not soft `docs_contracts`.

Performance result step reads `$RUNNER_TEMP/performance.json` with Python, writes status plus three p95 values to `$GITHUB_OUTPUT`, and leaves outputs missing when JSON is absent or malformed. Do not upload temporary SQLite files.

Configured Ruff policy:

1. Always run `ruff check --no-fix --select E9,F63,F7,F82` over project and QA Python.
2. Compute added/modified `.py` paths from `origin/${{ github.base_ref }}...HEAD`.
3. If any exist, run configured `ruff check --no-fix` on only those paths.
4. Never invoke `--fix` in CI because repository config has `fix = true`.

Split root scripts without double-counting:

- `release_installers`: `tests/test_release_version.py`, `tests/test_edge_channel.py`, `tests/test_macos_local_installer.sh`, `tests/test_macos_release_installer.sh`, `tests/test_windows_local_installer.sh`.
- `docs_contracts`: `tests/test_edge_installers.sh`, `tests/test_edge_workflow.sh`, `tests/test_one_line_install_docs.sh`, `tests/test_stable_release_workflow.sh`.
- `diff_hygiene`: fail on `git diff --check` or tracked paths under `__pycache__`, `.pytest_cache`, `dist`, `target`, or `output`.

Affected path rules:

- Rust/Tauri: `tidaldl-py/src-tauri/**` -> install existing Linux packages from `build-desktop.yml`, then `cargo check --manifest-path tidaldl-py/src-tauri/Cargo.toml`.
- Docker: `docker/**`, `docker-compose.yml`, or `tidaldl-py/pyproject.toml` -> `docker build -f docker/Dockerfile -t music-dl:qa .`.
- Tauri package metadata: `tidaldl-py/package.json` -> `cd tidaldl-py && bun install && bunx tauri --version`. Do not use `--frozen-lockfile`: current `tidaldl-py/bun.lock` is ignored and absent from a fresh checkout. Tracking that lockfile is outside this change.

- [ ] 5.5 Add protected live job without exposing credentials to fork PRs.

Condition:

```yaml
if: >-
  contains(github.event.pull_request.labels.*.name, 'qa-live') &&
  github.event.pull_request.head.repo.full_name == github.repository
environment: qa-live
```

Protected environment inputs:

- `MUSIC_DL_TIDAL_TOKEN_JSON`: contents of existing `token.json`.
- `DISCORD_TOKEN`: existing bot token.

Write Tidal JSON to `$RUNNER_TEMP/music-dl/token.json`, `chmod 600`, set `MUSIC_DL_CONFIG_DIR=$RUNNER_TEMP/music-dl`, run `scripts/qa_live_smoke.py`, then remove token file in an `if: always()` cleanup step. Never print secret values. Label absent -> `not_requested`; fork label -> `not_applicable`; trusted labelled job missing/failure -> hard blocker.

- [ ] 5.6 Add final always-running `qa` aggregation job.

Final job needs every deterministic and live job. It invokes `scripts/qa_score.py` with all scored `--result` outputs, deterministic-job `--duration` outputs, and three performance `--metric` outputs; derives trusted/live-requested booleans from event context; passes `--summary "$GITHUB_STEP_SUMMARY"`; and omits `--enforce` during calibration. Never pass live-job duration into the shared deterministic duration award. Job summary is the calibration record; no new artifact upload is needed.

- [ ] 5.7 Run workflow and scorer contract tests.

```bash
uv run --project tidaldl-py --extra test python -m pytest \
  tests/test_qa_workflow.py tests/test_qa_score.py -q
```

Expected: all tests pass.

- [ ] 5.8 Commit advisory workflow.

```bash
git add .github/workflows/qa.yml .github/workflows/gui-smoke.yml tests/test_qa_workflow.py
git commit -m "ci: add advisory pull request QA gate"
```

- [ ] 5.9 Verify native GitHub secret scanning and push protection are enabled; stop if either is disabled.

```bash
gh api repos/alfdav/music-dl --jq '.security_and_analysis | {
  secret_scanning: .secret_scanning.status,
  push_protection: .secret_scanning_push_protection.status
}'
```

Expected: both values are `enabled`. This read-only repository setting check is defense-in-depth evidence, not a scored PR result.

## 6. Document local QA and rollout

**Files:**

- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `openspec/changes/qa-pr-rubric/tasks.md`

- [ ] 6.1 Replace `gui-smoke` wording in `CONTRIBUTING.md` with final `qa` summary semantics.

Document: 90-100 ready, 80-89 ready with debt, below 80 blocked after enforcement, and any hard blocker blocked. State workflow remains advisory for first five PRs.

- [ ] 6.2 Add local QA commands to README Development section.

Include exact commands:

```bash
uv run --project tidaldl-py --extra test python -m pytest \
  tests/test_qa_score.py tests/test_qa_performance.py \
  tests/test_qa_live_smoke.py tests/test_qa_workflow.py -q
uv run --project tidaldl-py ruff check --no-fix --select E9,F63,F7,F82 \
  tidaldl-py/tidal_dl tidaldl-py/tests scripts tests
cd apps/discord-bot && bun test && bun run typecheck
```

Document `qa-live` as internal-only, approval-protected, read-only, and never available to fork PRs. Do not document secret values.

- [ ] 6.3 Add a calibration evidence table to the end of this plan.

- [ ] 6.4 Run documentation contract tests.

```bash
for test_script in \
  tests/test_edge_installers.sh \
  tests/test_edge_workflow.sh \
  tests/test_one_line_install_docs.sh \
  tests/test_stable_release_workflow.sh
do
  bash "$test_script"
done
```

Expected: every script exits 0.

- [ ] 6.5 Commit documentation.

```bash
git add README.md CONTRIBUTING.md openspec/changes/qa-pr-rubric/tasks.md
git commit -m "docs: explain pull request QA gate"
```

## 7. Verify implementation before advisory rollout

- [ ] 7.1 Run focused QA unit and contract tests.

```bash
uv run --project tidaldl-py --extra test python -m pytest \
  tests/test_qa_score.py \
  tests/test_qa_performance.py \
  tests/test_qa_live_smoke.py \
  tests/test_qa_workflow.py \
  tests/test_release_version.py \
  tests/test_edge_channel.py -q
```

- [ ] 7.2 Run existing deterministic Python smoke and security groups from workflow exactly.

- [ ] 7.3 Run every root shell contract assigned to `release_installers` and `docs_contracts`.

- [ ] 7.4 Run bot checks.

```bash
cd apps/discord-bot && bun test && bun run typecheck
```

- [ ] 7.5 Run static and packaging checks.

```bash
uv run --project tidaldl-py ruff check --no-fix --select E9,F63,F7,F82 \
  tidaldl-py/tidal_dl tidaldl-py/tests scripts tests
uv build --project tidaldl-py
```

- [ ] 7.6 Run one real deterministic performance probe and confirm all absolute p95 ceilings pass.

- [ ] 7.7 Run `openspec validate qa-pr-rubric`, Superpowers verification, and `ponytail:ponytail-review` on the complete diff. Fix only concrete findings, rerun affected checks, and update relevant docs.

- [ ] 7.8 Confirm `git status --short` contains only known user-owned untracked files or intended implementation changes before publishing.

## 8. Calibrate on five PRs, then enforce

Do not execute this group in the initial implementation session. Five completed GitHub Actions runs and human approval are required.

- [ ] 8.1 Publish advisory workflow through normal SSH Git workflow and open a PR.
- [ ] 8.2 Re-run the native GitHub secret-scanning/push-protection check from Step 5.9, then configure protected `qa-live` environment with required reviewer. Add secrets only through GitHub environment secret controls; never copy them into repository files, commands, logs, or task notes.
- [ ] 8.3 Record five representative advisory runs below. Every row requires a GitHub run URL, score, maximum deterministic job seconds, and three performance p95 values.
- [ ] 8.4 Confirm all five runs finish with every deterministic job at or below 10 minutes. Fix gate infrastructure before proceeding if any healthy PR is blocked.
- [ ] 8.5 Compute median CI p95 values and add `scripts/qa_performance_baseline.json` with only `pagination`, `search`, and `artists` numeric milliseconds.
- [ ] 8.6 Add baseline-loading tests, update CI performance command to pass `--baseline scripts/qa_performance_baseline.json`, and rerun absolute plus relative-regression cases. Assert workflow contract contains the baseline path and fails if enforced mode lacks it.
- [ ] 8.7 Remove advisory-only behavior by passing `--enforce` in final workflow job only after Step 8.6 proves relative comparison is active.
- [ ] 8.8 Validate OpenSpec, rerun workflow contracts, update README/CONTRIBUTING from advisory to enforced, and commit calibration.
- [ ] 8.9 Enable final `qa` check through branch protection. Keep intermediate jobs diagnostic-only.
- [ ] 8.10 If gate infrastructure blocks healthy PRs, remove required-check enforcement while keeping evidence collection active; record cause and fix before re-enabling.

## Calibration evidence

| Run | PR | GitHub run | Score | Max job seconds | Pagination p95 ms | Search p95 ms | Artists p95 ms |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |
| 4 |  |  |  |  |  |  |  |
| 5 |  |  |  |  |  |  |  |
