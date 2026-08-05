## ADDED Requirements

### Requirement: Risk-weighted PR score
The system SHALL calculate a 100-point pull-request quality score using these fixed category weights: correctness 35, static quality 20, security 15, performance 15, build and packaging 10, and change hygiene 5. A pull request SHALL require at least 80 points to pass.

#### Scenario: High score passes
- **WHEN** every hard blocker is clear and the calculated score is at least 80
- **THEN** the final QA verdict is passing and reports the category breakdown

#### Scenario: Low score blocks
- **WHEN** the calculated score is below 80
- **THEN** the final QA verdict is blocked and reports the missing points

### Requirement: Critical failures override score
The system SHALL block a pull request regardless of score when required correctness tests, TypeScript typechecking, security checks, credential protections, affected builds, absolute performance ceilings, or requested live smoke fail. Missing or timed-out required evidence SHALL also block.

#### Scenario: Strong score with critical failure
- **WHEN** the calculated score is at least 80 but a hard blocker exists
- **THEN** the final QA verdict is blocked and names the blocker

#### Scenario: Required result missing
- **WHEN** a required job fails to emit its result
- **THEN** that check earns zero and the final QA verdict is blocked

### Requirement: Deterministic PR checks
The system SHALL run deterministic Python GUI/API smoke, Bun tests, release/installer regressions, TypeScript typechecking, Ruff, security regressions, packaging checks, change-hygiene checks, and library-performance checks for pull requests targeting `master`.

#### Scenario: Standard pull request
- **WHEN** a pull request targets `master`
- **THEN** all unconditional deterministic checks run without live Tidal or Discord access

#### Scenario: Affected-package check is not applicable
- **WHEN** an explicit path rule proves an expensive Rust, Docker, or package smoke check is unaffected
- **THEN** the check is reported as `not_applicable` and retains its assigned points

#### Scenario: Unexpected skip
- **WHEN** a check is skipped without an explicit path rule
- **THEN** the check earns zero and required evidence creates a hard blocker

### Requirement: Deterministic performance budget
The system SHALL benchmark a 10,000-track temporary `LibraryDB` fixture using 25 warm iterations. Pagination p95 SHALL be at most 20 ms, search p95 at most 15 ms, and artist-listing p95 at most 20 ms. The workflow SHALL earn one shared 5-point duration award only when every deterministic job finishes at or below 8 minutes and SHALL hard-block when any deterministic job exceeds 10 minutes. GitHub runner queue time SHALL be excluded.

#### Scenario: Absolute performance ceiling passes
- **WHEN** every measured p95 is at or below its absolute ceiling
- **THEN** no absolute-performance hard blocker is created

#### Scenario: Absolute performance ceiling fails
- **WHEN** any measured p95 exceeds its absolute ceiling
- **THEN** the final QA verdict is blocked

#### Scenario: Material relative regression
- **WHEN** a measured p95 is both more than 25% and more than 2 ms slower than its stored CI baseline without exceeding the absolute ceiling
- **THEN** the performance category loses all 10 benchmark points and the summary reports the regression without creating an independent hard blocker

#### Scenario: Advisory baseline calibration
- **WHEN** five-run calibration is incomplete and no stored CI-relative baseline exists
- **THEN** passing absolute ceilings earns all 10 benchmark points, relative status is `calibrating`, and enforcement remains disabled

#### Scenario: Deterministic job finishes within eight minutes
- **WHEN** every deterministic job finishes within 8 minutes excluding runner queue time
- **THEN** the performance category earns one shared 5-point duration award

#### Scenario: Deterministic job finishes between eight and ten minutes
- **WHEN** a deterministic job finishes after 8 minutes but no later than 10 minutes excluding runner queue time
- **THEN** the performance category loses the one shared 5-point duration award without creating an independent hard blocker

#### Scenario: Deterministic job exceeds ten minutes
- **WHEN** a deterministic job exceeds its 10-minute timeout
- **THEN** the final QA verdict is blocked

#### Scenario: Live latency varies
- **WHEN** live-smoke latency changes
- **THEN** the summary reports the latency without changing deterministic performance points

### Requirement: PR-scoped secret and dependency controls
The system SHALL run `gitleaks/gitleaks-action` pinned to commit `ff98106e4c7b2bc287b24eaf42907196329070c7` against the pull request commit range with read-only permissions. A clean Gitleaks result SHALL earn 3 security points; any detection SHALL earn zero and hard-block. The system SHALL use official GitHub dependency review to earn 2 security points when clean and block high-or-critical dependency regressions. Native GitHub secret scanning and push protection SHALL remain enabled as defense-in-depth but SHALL NOT supply the PR-scoped score result.

#### Scenario: PR secret scan passes
- **WHEN** pinned Gitleaks scans the pull request commit range and finds no secret
- **THEN** the check earns 3 security points and emits a passing named result for final aggregation

#### Scenario: PR secret scan detects a secret
- **WHEN** pinned Gitleaks finds a secret in the pull request commit range
- **THEN** the check earns zero and emits a hard blocker for final aggregation

#### Scenario: Fork PR secret scan
- **WHEN** Gitleaks scans a fork pull request
- **THEN** it uses only read-only repository contents and the reduced `GITHUB_TOKEN` without receiving repository secrets

#### Scenario: Dependency review passes
- **WHEN** a pull request introduces no high-or-critical dependency regression
- **THEN** dependency review earns 2 security points and creates no blocker

#### Scenario: High-severity dependency regression
- **WHEN** official GitHub dependency review finds a new high-or-critical vulnerability
- **THEN** dependency review earns zero and creates a hard blocker

#### Scenario: Secret scanning detects a credential
- **WHEN** native GitHub secret scanning or push protection detects an exposed credential
- **THEN** native GitHub protection blocks or alerts independently of the PR-scoped score

### Requirement: Complete QA summary
The system SHALL run final aggregation after all prerequisite jobs, including failed or cancelled jobs, and SHALL publish category points, raw check outcomes, duration, hard blockers, total score, and final verdict in the GitHub Actions job summary.

#### Scenario: Intermediate check fails
- **WHEN** an intermediate check fails
- **THEN** final aggregation still runs and reports all available evidence

#### Scenario: Infrastructure failure
- **WHEN** setup or runner failure prevents a required result
- **THEN** the summary classifies missing evidence separately from product failure and blocks pending a clean rerun

### Requirement: Protected opt-in live smoke
The system SHALL run live Tidal and Discord smoke only when the `qa-live` label is present, the PR head belongs to the target repository, and a protected environment grants approval. The workflow SHALL NOT use `pull_request_target` to execute PR code.

#### Scenario: Trusted live smoke approved
- **WHEN** an internal PR has the `qa-live` label and environment approval
- **THEN** read-only Tidal authentication/search and Discord authentication/identity checks run

#### Scenario: Fork requests live smoke
- **WHEN** a fork PR has the `qa-live` label
- **THEN** no live credential is exposed, the live job does not execute untrusted code with secrets, and live smoke is reported as `not_applicable` without creating a blocker

#### Scenario: Live smoke attempts mutation
- **WHEN** the live test plan would download media, alter playback or queues, or create Discord messages
- **THEN** the workflow rejects that operation as outside the allowed smoke scope

#### Scenario: Requested trusted live smoke fails
- **WHEN** an approved live-smoke run for a trusted internal PR fails or produces no result
- **THEN** the final QA verdict is blocked

### Requirement: Staged enforcement
The system SHALL repair existing hard-blocker failures, run five pull requests in advisory mode, calibrate CI-relative performance baselines, and only then make the final `qa` verdict a required branch-protection check.

#### Scenario: Advisory calibration
- **WHEN** fewer than five representative advisory PR runs have completed
- **THEN** QA reports score and blockers without enforcing branch protection

#### Scenario: Enforcement readiness
- **WHEN** baseline hard blockers are green, five advisory runs are recorded, relative baselines are stored, and the deterministic workflow meets the 10-minute target
- **THEN** maintainers may require the final `qa` check through branch protection

#### Scenario: Gate infrastructure is unreliable
- **WHEN** QA infrastructure blocks healthy changes
- **THEN** maintainers may return `qa` to advisory mode while evidence collection and repair continue
