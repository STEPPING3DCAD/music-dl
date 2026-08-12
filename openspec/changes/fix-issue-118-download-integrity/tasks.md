# GUI Download Terminal Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` to implement this plan task-by-task, then `superpowers:verification-before-completion`. Follow Ponytail full. Do not broaden scope beyond this contract.

**Goal:** Stop GUI downloads from reporting done when `Download.item()` returned `DownloadOutcome.FAILED`.

**Architecture:** Extend the existing `DownloadJobService` boundary only. Capture the download layer's typed outcome, route `FAILED` through existing error helpers, and leave the current success path unchanged for `DOWNLOADED`, `COPIED`, and `SKIPPED`.

**Tech Stack:** Python 3.13, pytest, UV, FastAPI service code, SQLite job/history storage, OpenSpec.

---

## 1. Lock the failure contract with tests

- [x] 1.1 In `tidaldl-py/tests/test_download_jobs_service.py`, update `test_worker_executes_download_job_and_records_history` so its fake `item()` returns `(DownloadOutcome.DOWNLOADED, tmp_path / "Song.flac")` instead of `None`; import `DownloadOutcome` from `tidal_dl.model.downloader` in the test.
- [x] 1.2 Add `test_worker_failed_outcome_records_error_without_complete` beside the existing worker tests. Reuse the same fake track/session/settings shape, make fake `item()` return `(DownloadOutcome.FAILED, "")`, capture `service.events.broadcast`, execute the claimed job, and assert all of the following: stored status is `error`; history contains one `error` row and no `done` row; an `error` event exists; no `complete` event exists; the configured download directory does not exist.
- [x] 1.3 Add success coverage for `DownloadOutcome.COPIED` and `DownloadOutcome.SKIPPED` by parameterizing the existing typed-success worker test or adding the two outcomes to that test without creating a new fixture/helper layer.
- [x] 1.4 Run the new failure test before production edits and preserve the red result: `cd tidaldl-py && rtk uv run pytest -q tests/test_download_jobs_service.py::test_worker_failed_outcome_records_error_without_complete`. Expected before the fix: assertion failure because stored/history status is `done` and events contain `complete`.

## 2. Gate GUI completion on the typed outcome

- [x] 2.1 In `tidaldl-py/tidal_dl/gui/services/download_job_service.py`, import the existing `DownloadOutcome` enum from `tidal_dl.model.downloader`; do not add a new result type, helper module, or dependency.
- [x] 2.2 In `_execute_download_job`, capture `download_outcome, _output_path = dl.item(...)` inside the existing retry loop instead of discarding the return value.
- [x] 2.3 After retry exhaustion and cancellation checks, handle only `DownloadOutcome.FAILED` before the existing success block: create `RuntimeError(f"Download failed for track {job.track_id}")`, call `_mark_job_error(current, error)` and `_broadcast_error(current, error)`, then return. Do not record done history, set `DONE`, emit `complete`, or scan the library on that branch.
- [x] 2.4 Leave `DOWNLOADED`, `COPIED`, and `SKIPPED` on the current success path. Do not add filesystem rescans, path-existence inference, new retries, or changes inside `Download.item()`.
- [x] 2.5 Run focused green verification: `cd tidaldl-py && rtk uv run pytest -q tests/test_download_jobs_service.py`. Expected: all tests pass, including the failed-outcome and three terminal-success outcomes.

## 3. Document and verify

- [x] 3.1 Update `tidaldl-py/docs/backend-guide.md` download flow to place an explicit `DownloadOutcome` gate before history/completion: `FAILED` follows the error path; `DOWNLOADED`, `COPIED`, and `SKIPPED` follow the success path. Keep the existing rule that downloads never fail silently.
- [x] 3.2 Run focused lint: `cd tidaldl-py && rtk uv run ruff check tidal_dl/gui/services/download_job_service.py tests/test_download_jobs_service.py`. Expected: exit 0.
- [x] 3.3 Run the relevant full Python suite: `cd tidaldl-py && rtk uv run pytest -q`. Expected: exit 0 with no new failures.
- [x] 3.4 Run documentation coverage: `cd tidaldl-py && rtk uv run pytest -q ../tests/test_documentation.py`. Expected: exit 0.
- [x] 3.5 Run strict specification validation from the repository root: `rtk proxy openspec validate fix-issue-118-download-integrity --strict`. Expected: valid with zero errors.
- [x] 3.6 Run final diff gates from the repository root: `rtk git diff --check`, `rtk git status --short`, and `rtk proxy git diff -- tidaldl-py/tidal_dl/gui/services/download_job_service.py tidaldl-py/tests/test_download_jobs_service.py tidaldl-py/docs/backend-guide.md openspec/changes/fix-issue-118-download-integrity`. Confirm only contracted files changed, no dependency/config/schema/module was added, and no reporter-fork quality-probe, singleton, or cover-art change leaked into this fix.

## 4. Explicit scope exclusions

- [x] 4.1 Do not widen `Settings`, `Tidal`, or `HandlingApp.__new__`; do not change `FileMixin.cover_data`; do not change `_probe_subscription_quality`. Live evidence shows those reporter-fork edits recover CLI but do not repair GUI false completion.
- [x] 4.2 Do not change provider/source selection, OAuth behavior, download retries, frontend event rendering, database schema, historical rows, release notes, version numbers, packaging, or dependencies.
- [x] 4.3 Stop and report a blocker instead of guessing if the failed-outcome test cannot reproduce the current false-success state or if implementation requires changes outside `download_job_service.py`, its focused test, and backend documentation.
