## Context

Current PR CI runs a focused GUI smoke workflow. Broader Python, Bun, release, installer, packaging, Rust, and Docker checks exist but do not produce one merge verdict. Discord tests pass while TypeScript typechecking fails, proving that test success alone is insufficient. The full Python suite is too slow for the agreed PR feedback target, and the repository has no deterministic performance budget.

Constraints:

- PR feedback must finish within 10 minutes.
- Passing requires at least 80/100 and no hard blocker.
- Live Tidal and Discord checks may use existing credentials only on trusted internal branches after protected-environment approval.
- Fork PRs must never receive credentials.
- Use Bun and uv; reuse existing tests and workflows before adding code.
- Keep scoring local to GitHub Actions. No service, database, dashboard, or new runtime dependency.

## Goals / Non-Goals

**Goals:**

- Produce one evidence-backed PR score and merge verdict.
- Run deterministic checks in parallel within 10 minutes.
- Prevent points from compensating for critical failures.
- Detect material regressions in common local-library queries.
- Report every failed, skipped, missing, and timed-out result.
- Support read-only, opt-in live smoke without exposing credentials.
- Start advisory, calibrate from five PR runs, then enforce through branch protection.

**Non-Goals:**

- Coverage-percentage targets.
- Nightly or release-readiness rubrics.
- Hosted dashboards or historical metrics services.
- Automatic flaky-test quarantine.
- Live download, playback, queue mutation, or Discord message creation.
- Refactoring product code unrelated to making baseline checks pass.

## Decisions

### 1. Risk-weighted score plus hard blockers

The gate uses this fixed 100-point model:

| Category | Points | Evidence |
|---|---:|---|
| Correctness | 35 | Python GUI/API smoke 15; Bun tests 10; release/installer regressions 10 |
| Static quality | 20 | TypeScript typecheck 10; Ruff 10 |
| Security | 15 | Auth, CSRF, and path-trust tests 10; PR-scoped Gitleaks 3; official GitHub dependency review 2 |
| Performance | 15 | Library query benchmark 10; deterministic job duration 5 |
| Build/packaging | 10 | `uv build` 5; affected Rust, Docker, or package smoke 5 |
| Change hygiene | 5 | Documentation/install contracts 3; clean diff and no generated junk 2 |

Verdicts:

- 90-100: ready.
- 80-89: ready with visible quality debt.
- Below 80: blocked.
- Any hard blocker: blocked regardless of score.

Hard blockers are failed correctness tests, TypeScript typechecking, security regression, Gitleaks detection in the PR commit range, high-severity dependency regression, affected package build/start failure, absolute performance ceiling breach, deterministic job runtime above 10 minutes, requested trusted live-smoke failure, and any missing or timed-out required result. Ruff, material relative performance regression, deterministic job runtime above 8 but at most 10 minutes, and hygiene failures lose points but do not independently override an otherwise valid score.

A check skipped by an explicit path rule is `not_applicable` and retains its points because its risk is absent. An unexpected skip or missing result earns zero; required evidence also creates a hard blocker.

Equal category weights were rejected because documentation could offset broken behavior. Regression-only scoring was rejected because it would preserve existing defects.

### 2. One final GitHub Actions gate

Extend PR CI with parallel jobs for Python, Discord bot, contracts/build, security, and performance. Each job exposes named outcomes and duration. A final `qa` aggregation job runs with `if: always()`, consumes all job outputs, writes the Markdown job summary, and exits nonzero when the score or hard-blocker rule fails.

Only final `qa` becomes the required branch-protection check. Intermediate jobs retain diagnostic visibility but cannot prevent aggregation from reporting all evidence.

One standard-library Python scorer will own point arithmetic, blocker rules, verdict formatting, and exit status. Existing release and edge scripts cannot be extended because they manage version metadata and manifests, not CI evidence. A shell-only scorer was rejected: nested status arithmetic and missing-result handling would be harder to test and easier to drift. Added complexity is limited to one input mapping, one result model, and one focused test file.

### 3. Deterministic performance check

Benchmark `LibraryDB` with a temporary SQLite database containing 10,000 synthetic tracks. Exclude fixture seeding from timed operations. Run 25 warm iterations each for:

- `tracks_page(limit=50, offset=5000)`
- `tracks_page(query="Track 9999", limit=50, offset=0)`
- `artists_page(limit=50, offset=0)`

Initial absolute p95 ceilings:

| Operation | Local observed p95 | CI ceiling |
|---|---:|---:|
| Paginated tracks | 7.9 ms | 20 ms |
| Search | 4.1 ms | 15 ms |
| Artist listing | 6.2 ms | 20 ms |

Absolute ceiling breach is a hard blocker. During five advisory PR runs, record CI p95 values and award all 10 benchmark points when absolute ceilings pass; relative status is `calibrating` and deducts nothing. Before enforcement, store median CI baselines. After calibration, a result loses all 10 benchmark points when it is both more than 25% and more than 2 ms slower than stored baseline. Baseline changes require benchmark evidence and review. Enforcement cannot start without stored baselines.

The workflow earns one shared 5-point duration award only when every deterministic job finishes within 8 minutes. If any deterministic job runs longer than 8 but no longer than 10 minutes, the workflow loses the shared 5 points. Any deterministic job exceeding its 10-minute timeout is a hard blocker. GitHub runner queue time is excluded because it is not product performance. Live-service latency is reported separately and never affects performance points because network and vendor variance would make the score unstable.

### 4. Trusted live smoke

Label `qa-live` requests live smoke. The job runs only when the PR head repository equals the target repository and a protected `qa-live` GitHub environment grants approval. It uses least-privilege workflow permissions and never uses `pull_request_target` to execute PR code.

Live smoke is read-only: validate Tidal authentication and search, validate Discord bot authentication/identity, and record latency. It must not download media, change queues, start playback, or create Discord messages. Once requested for an approved trusted internal PR, failure or missing evidence is a hard blocker. A fork PR carrying `qa-live` reports live smoke as `not_applicable`; it neither receives credentials nor creates a blocker.

### 5. Baseline repair and rollout

1. Fix current Discord type errors.
2. Pin Ruff in the uv-managed development dependencies because Ruff configuration already exists but the executable is absent. Standard-library syntax checks were rejected because they do not detect unused imports or other configured static defects; added complexity is one pinned development dependency and lockfile update.
3. Make all proposed hard blockers green.
4. Add `gitleaks/gitleaks-action` pinned to commit `ff98106e4c7b2bc287b24eaf42907196329070c7`. Run it against the PR commit range with read-only permissions and consume its named result in the final scorer. A clean result earns 3 points; any detection earns zero and hard-blocks. Fork PRs use only the reduced read-only `GITHUB_TOKEN`, never repository secrets.
5. Configure official `actions/dependency-review-action` to earn 2 points when clean and block high-or-critical dependency regressions. Keep native GitHub secret scanning plus push protection enabled as defense-in-depth, not as a PR-scoped scorer input.
6. Run five PRs in advisory mode and collect durations and benchmark values.
7. Set CI-relative performance baselines, validate the 10-minute target, then enable score enforcement and branch protection.
8. Roll back enforcement by making `qa` advisory again; keep evidence collection active while fixing gate infrastructure.

## Risks / Trade-offs

- [Path rules miss an indirect dependency] -> Keep critical Python, Bun, and security suites unconditional; path rules apply only to expensive affected-package smoke.
- [Shared-runner timing noise] -> Use 25 warm iterations, broad absolute ceilings, and the dual relative threshold.
- [Score becomes false reassurance] -> Hard blockers override score and summaries list raw evidence.
- [Workflow setup fails before outputs exist] -> Final aggregation treats missing required output as zero plus hard blocker.
- [Credentials reach untrusted code] -> Require internal head repository, protected environment approval, least privilege, and no `pull_request_target` execution.
- [Existing red baseline prevents adoption] -> Repair baseline first, then use five advisory PRs before enforcement.
- [Ruff introduces broad unrelated cleanup] -> Establish baseline with the smallest configured rule set that passes or narrowly excludes documented legacy debt; do not reformat unrelated files.

## Open Questions

None. CI-relative performance baseline values will be derived from the approved five-run calibration period.
