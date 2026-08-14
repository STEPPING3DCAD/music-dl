## Context

Issue #118 reports that desktop downloads advance almost instantly, turn green, and create no folders or files. The GUI path is `POST /api/download` -> `DownloadJobService` -> `Download.item()` -> persisted history/SSE -> `_dlComplete()`. `Download.item()` already returns `(DownloadOutcome, path)`: validation, unavailable stream, and segment failures can return `DownloadOutcome.FAILED` without raising. The worker discards that result and unconditionally records `done`, marks progress 100, and emits `complete`; the frontend faithfully renders that false completion.

An in-process reproduction on current `origin/master` returned `FAILED` from the fake download layer and observed `stored_status='done'`, `history_status='done'`, `event_types=['progress', 'complete']`, and no download directory. Existing test `test_worker_executes_download_job_and_records_history` masks the defect by returning `None` from its fake `item()` and asserting success, despite the current typed return contract.

Reporter changes to singleton `__new__` signatures and `FileMixin.cover_data()` restore CLI behavior but leave this GUI result-handling path unchanged. The quality probe also runs during authentication, not GUI job terminalization. Those changes therefore do not explain or repair the false green completion.

## Goals / Non-Goals

**Goals:**

- Make standard GUI job state, history, and SSE agree with `Download.item()`'s typed outcome.
- Route `FAILED` through the worker's existing error persistence and broadcast behavior.
- Keep `DOWNLOADED`, `COPIED`, and `SKIPPED` as terminal successes, matching collection/checkpoint semantics.
- Add one focused failure regression plus success-outcome coverage.

**Non-Goals:**

- Change singleton constructors, cover-art binding, or subscription-quality probing from the reporter's fork.
- Diagnose or alter provider/account-specific stream delivery after the hidden failure becomes visible.
- Change source selection, retries, download internals, database schema, API payloads, or frontend rendering.
- Repair historical false-success rows or add telemetry, dependencies, modules, or abstractions.

## Decisions

### Consume the existing typed outcome at the GUI worker boundary

Capture the tuple returned by `dl.item()`. When the outcome is `DownloadOutcome.FAILED`, construct a concise runtime error, call the existing `_mark_job_error()` and `_broadcast_error()` helpers, and return before success history, `DONE`, `complete`, or library scanning. Continue the existing success path for `DOWNLOADED`, `COPIED`, and `SKIPPED`.

This is the smallest shared fix because search, playlist, bot, and ordinary GUI downloads already converge on `DownloadJobService`. A filesystem rescan would infer success indirectly and cannot distinguish intentional skips. Changing `Download.item()` to raise would widen the CLI and collection contract unnecessarily.

### Test state and events, not source text

Update the existing success fixture to return a real typed success outcome. Add a failed-outcome test that executes the claimed job and asserts job `error`, one error-history row, no done-history row, an `error` event, and no `complete` event. Parameterize or otherwise cover the three accepted success outcomes without adding fixtures or helper layers solely for this change.

### Keep the error generic at this boundary

`DownloadOutcome.FAILED` carries no reason. The worker SHALL surface a stable message identifying the track and failed outcome while existing download-layer logs retain the lower-level cause. Adding a new result object or exception hierarchy is outside this fix.

## Risks / Trade-offs

- [Provider failure remains unresolved] -> The GUI stops lying and exposes an error; use that concrete error/log evidence for any separate provider-specific repair.
- [Existing callers used `None` as fake success] -> Update the stale test double to the current `Download.item()` tuple contract.
- [`SKIPPED` creates no new file] -> Preserve it as success because the download layer uses it only for an already-present/deduplicated item and collection checkpoints already treat it as terminal success.
- [Old false-success history remains] -> Do not rewrite user history without reliable evidence identifying affected rows.

## Migration Plan

No schema or data migration. Deploy the worker/test/docs change together. Rollback restores the prior worker behavior but does not require data conversion.

## Open Questions

None for implementation. The reporter's next concrete GUI error may justify a separate source/provider change; this contract does not guess it.
