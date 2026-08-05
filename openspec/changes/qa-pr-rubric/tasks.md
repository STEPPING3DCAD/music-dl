## 1. Repair baseline

- [ ] 1.1 Fix Discord command-builder types until `bun run typecheck` passes without changing command behavior.
- [ ] 1.2 Pin Ruff through uv, update `uv.lock`, and establish the smallest passing configured lint baseline without unrelated reformatting.
- [ ] 1.3 Run existing Python, Bun, release, and installer checks; fix every proposed hard blocker and record only non-blocking quality debt.

## 2. Build score engine

- [ ] 2.1 Add focused tests for passing score, score below 80, hard-blocker override, explicit `not_applicable`, missing required result, Ruff deduction, Gitleaks blocker, high-severity dependency-review blocker, hygiene deduction, shared duration award, performance deductions, and Markdown summary output.
- [ ] 2.2 Implement one standard-library score aggregator that consumes named check outcomes, calculates fixed category points, reports blockers, writes Markdown, and returns the final exit status.

## 3. Add deterministic performance check

- [ ] 3.1 Add a 10,000-track `LibraryDB` benchmark with 25 warm iterations for pagination, search, and artist listing.
- [ ] 3.2 Enforce absolute p95 ceilings of 20 ms, 15 ms, and 20 ms respectively, and emit machine-readable measurements for scoring.
- [ ] 3.3 Add calibration status that awards benchmark points from absolute ceilings until five-run CI baselines exist, then deducts all 10 benchmark points for a regression exceeding both 25% and 2 ms.

## 4. Assemble deterministic PR workflow

- [ ] 4.1 Extend the existing PR workflow into parallel Python, Discord bot, contracts/build, security, and performance jobs using Bun and uv.
- [ ] 4.2 Add explicit affected-path rules for expensive Rust, Docker, and package smoke checks; emit `not_applicable` only through those rules.
- [ ] 4.3 Add an always-running final `qa` job that aggregates outcomes, durations, score, blockers, and verdict into the GitHub job summary.
- [ ] 4.4 Add workflow contract coverage for score mappings, required-result handling, path-based skips, full duration points through 8 minutes, duration-point loss from 8 to 10 minutes, hard timeout above 10 minutes, and final aggregation after failures.
- [ ] 4.5 Configure `gitleaks/gitleaks-action` at commit `ff98106e4c7b2bc287b24eaf42907196329070c7` to scan the PR commit range, award 3 points when clean, and emit a named hard-blocker result on detection using no repository secrets.
- [ ] 4.6 Configure official GitHub dependency review to award 2 points on success and hard-block new high-or-critical dependency vulnerabilities.
- [ ] 4.7 Verify native GitHub secret scanning and push protection remain enabled as defense-in-depth outside the PR score.

## 5. Add protected live smoke

- [ ] 5.1 Add read-only Tidal authentication/search and Discord authentication/identity smoke commands with no download, playback, queue, or message mutation.
- [ ] 5.2 Gate live smoke on the `qa-live` label, internal head repository, and protected `qa-live` environment approval with least-privilege permissions.
- [ ] 5.3 Add contract coverage proving fork PRs receive no live credentials, no PR code runs with secrets through `pull_request_target`, and fork `qa-live` requests report `not_applicable` without a blocker.
- [ ] 5.4 Feed requested trusted internal live-smoke failure or missing evidence into the final hard-blocker verdict while keeping live latency outside performance points.

## 6. Document, calibrate, and enforce

- [ ] 6.1 Update README and relevant contributor instructions with local QA commands, score meanings, hard blockers, path-based `not_applicable`, and trusted live-smoke use.
- [ ] 6.2 Run scorer tests, deterministic QA checks, OpenSpec validation, Superpowers verification, and Ponytail diff review.
- [ ] 6.3 Run five representative PRs in advisory mode and record category outcomes, total duration, and performance p95 values.
- [ ] 6.4 Store median CI performance baselines, confirm the 10-minute target, and enable final `qa` enforcement through branch protection.
- [ ] 6.5 Document rollback to advisory mode when QA infrastructure blocks healthy changes.
