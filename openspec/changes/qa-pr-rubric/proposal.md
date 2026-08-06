## Why

Pull requests currently lack one trustworthy quality verdict: CI covers only a GUI smoke subset, Discord typechecking fails, and no performance budget or scored summary exists. Contributors need deterministic feedback within 10 minutes without letting a weighted score hide correctness, security, build, or absolute-performance failures.

## What Changes

- Add a risk-weighted 100-point PR rubric with an 80-point passing threshold.
- Add hard blockers that override score for critical correctness, static-type, PR-scoped secret, dependency-security, build, credential-boundary, and absolute-performance failures.
- Run deterministic Python, Bun, static, security, packaging, hygiene, and library-performance checks for every PR.
- Publish category evidence, points, duration, blockers, and final verdict in the GitHub Actions job summary, including failed and incomplete runs.
- Add protected, opt-in live Tidal/Discord smoke testing for trusted repository branches; never expose credentials to fork PRs.
- Roll out through baseline repair, five advisory PR runs, then branch-protection enforcement.

## Capabilities

### New Capabilities

- `pull-request-quality-gate`: Defines PR scoring, hard blockers, deterministic checks, performance budgets, live-smoke isolation, reporting, and enforcement rollout.

### Modified Capabilities

None.

## Impact

- GitHub Actions PR workflow and branch-protection requirements.
- Existing Python, Bun, security, release, installer, Rust, Docker, and packaging checks, plus a commit-pinned Gitleaks PR action.
- One standard-library score aggregator and its focused tests.
- Python development dependencies: pin Ruff because repository already contains Ruff configuration but no installed Ruff dependency.
- Contributor documentation covering local QA commands, score interpretation, hard blockers, and trusted live-smoke use.
