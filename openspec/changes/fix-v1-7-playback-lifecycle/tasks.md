# v1.7.1 Playback and Lifecycle Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use Superpowers subagent-driven development task-by-task. Follow TDD and do not commit until all documentation and completion gates pass.

**Goal:** Release v1.7.1 with correct local/Tidal routing, trustworthy recent history and status, prompt visible artwork, safe sidecar cleanup, and an isolated test suite.

**Architecture:** Extend only existing serializers, browser helpers, Tauri lifecycle cleanup, and pytest fixtures. Reuse the library DB, native image hints, Unix `ps`, and current test runners; add no module or dependency.

**Tech Stack:** Python 3.13/FastAPI/pytest, browser JavaScript/Bun test, Rust/Tauri/Cargo, OpenSpec.

**Command workdirs:** Tasks 1-4 run from `tidaldl-py/` unless a command names `--project tidaldl-py`; OpenSpec and release-helper commands run from the repository root.

## 1. Playback source contract

- [x] 1.1 Add failing Bun coverage in `tidaldl-py/tests/player-decisions.test.js` proving `playTrack` uses `/api/playback/local` for either `local_path` or `path`, never generates `null`/`undefined` stream URLs for local payloads, and uses `/api/playback/stream/{id}` only without a local path; run `rtk bun test tests/player-decisions.test.js` and confirm the `path` case fails.
- [x] 1.2 Add failing pytest coverage in `tidaldl-py/tests/test_gui_playlist_local_preference.py` proving Tidal search serialization returns the live local path, quality, and format and remains remote when no live row exists; run `rtk uv run pytest -q tests/test_gui_playlist_local_preference.py` from `tidaldl-py/` and confirm the local metadata assertions fail.
- [x] 1.3 Add failing pytest coverage in `tidaldl-py/tests/test_api_endpoints.py` proving a local favorite exposes the same usable `local_path`; run `rtk uv run pytest -q tests/test_api_endpoints.py -k favorite` from `tidaldl-py/` and confirm it fails.
- [x] 1.4 Minimally update `tidaldl-py/tidal_dl/gui/api/search.py`, `tidaldl-py/tidal_dl/gui/api/library.py`, and `tidaldl-py/tidal_dl/gui/static/player.js` to satisfy the contract; rerun `rtk bun test tests/player-decisions.test.js`, `rtk uv run pytest -q tests/test_gui_playlist_local_preference.py`, and `rtk uv run pytest -q tests/test_api_endpoints.py -k favorite` green from `tidaldl-py/`.
- [x] 1.5 Add failing backend coverage in `tidaldl-py/tests/test_gui_api.py` for `credentials_ready` and failing Bun/static coverage in `player-decisions.test.js`, `views-decisions.test.js`, and `test_static_assets.py` for visible `local`/`tidal` source labels, blank unknown remote format, neutral saved-credential rendering on both surfaces, persisted remote-error downgrade, successful-remote-play recovery, unchanged status on local media events, and source-specific aggregate local errors. From `tidaldl-py/`, run `rtk uv run pytest -q tests/test_gui_api.py tests/test_static_assets.py` and `rtk bun test tests/player-decisions.test.js tests/views-decisions.test.js`; confirm the new assertions fail for the intended missing behavior.
- [x] 1.6 Minimally update `tidaldl-py/tidal_dl/gui/api/settings.py`, `tidaldl-py/tidal_dl/gui/static/views.js`, `player.js`, and `style.css`. Store only the observed remote playback-unavailable flag in browser session state so both surfaces retain it across `/auth/status` re-renders; rerun `rtk uv run pytest -q tests/test_gui_api.py tests/test_static_assets.py` and `rtk bun test tests/player-decisions.test.js tests/views-decisions.test.js` green from `tidaldl-py/`, then replay the original search and favorite clicks in the final packaged smoke.

## 2. Recent-history timestamp boundary

- [x] 2.1 Add failing Bun tests in `tidaldl-py/tests/player-decisions.test.js` for positive values below `10_000_000_000`, unchanged millisecond values at or above that boundary, and duplicate merge ordering; confirm the seconds case fails.
- [x] 2.2 Add failing Bun tests in `tidaldl-py/tests/views-decisions.test.js` proving normalized current/weekly/older values classify correctly and 30-day clearing preserves recent entries; confirm the current server play fails before normalization.
- [x] 2.3 Add the smallest normalization at `_syncRecentFromServer` in `tidaldl-py/tidal_dl/gui/static/player.js`; do not add unit branches to each view helper.
- [x] 2.4 Run `rtk bun test tests/player-decisions.test.js tests/views-decisions.test.js` and `rtk uv run pytest -q tests/test_home.py tests/test_library_db.py` green from `tidaldl-py/`.

## 3. Visible artwork loading

- [x] 3.1 Add a failing assertion in `tidaldl-py/tests/test_static_assets.py` that album indexes 0-5 with `cover_url` use eager loading, album index 6 and later stay lazy, and the existing image-error fallback remains; run `rtk uv run pytest -q tests/test_static_assets.py` from `tidaldl-py/` and confirm it fails against v1.7.0.
- [x] 3.2 Change only the existing artist-gallery loop in `tidaldl-py/tidal_dl/gui/static/views.js` to choose `eager` for the first six images and `lazy` thereafter while retaining the current error fallback.
- [x] 3.3 Run `rtk uv run pytest -q tests/test_static_assets.py` and `rtk bun test tests/player-decisions.test.js tests/routes.test.js tests/views-decisions.test.js` green from `tidaldl-py/`; final packaged browser QA must capture request/screenshot evidence that all six Moby cards load immediately and that card index 6 and later retain the browser-native lazy hint in a larger gallery.

## 4. Desktop sidecar process tree

- [x] 4.1 Add failing Rust unit tests in `tidaldl-py/src-tauri/src/lib.rs` for Unix parent/child parsing, recursive descendants, malformed `ps` lines, and deepest-first ordering; confirm `rtk cargo test --manifest-path src-tauri/Cargo.toml` fails before implementation.
- [x] 4.2 Extend the existing sidecar cleanup in `lib.rs` with a Unix `ps -axo pid=,ppid=` query and descendant-only termination before `CommandChild.kill()`; retain Windows `taskkill /T /F` and add no crate.
- [x] 4.3 Add a failing Rust unit test named `updater_shutdown_uses_shared_owned_sidecar_cleanup` that exercises the planned shared shutdown seam's owned-state clearing/cleanup decision and guards updater wiring from bypassing that seam. From `tidaldl-py/`, run `rtk cargo test --manifest-path src-tauri/Cargo.toml updater_shutdown_uses_shared_owned_sidecar_cleanup` and confirm it fails before the seam exists.
- [x] 4.4 Extract the smallest `pub(crate)` owned-sidecar shutdown seam in `lib.rs`, call it from `tidaldl-py/src-tauri/src/updater.rs`, and remove the updater's direct `child.kill()`. Do not add a trait, module, or dependency solely for mocking. Rerun `rtk cargo test --manifest-path src-tauri/Cargo.toml updater_shutdown_uses_shared_owned_sidecar_cleanup` green.
- [x] 4.5 Run Rust formatting, tests, and compile checks: `rtk cargo fmt --manifest-path src-tauri/Cargo.toml -- --check`, `rtk cargo test --manifest-path src-tauri/Cargo.toml`, and `rtk cargo check --manifest-path src-tauri/Cargo.toml`.
- [x] 4.6 Defer packaged lifecycle acceptance until the final v1.7.1 build in Task 6.3; record the expected metadata PID, wrapper PID, descendant PID, port, and relaunch PID checks there.

## 5. Full-suite configuration isolation

- [x] 5.1 Add a failing collection-time assertion/test in `tidaldl-py/tests/test_test_isolation.py` proving `MUSIC_DL_CONFIG_DIR` is temporary before the test module imports application configuration; also prove every test receives a per-test directory and cannot resolve the normal user config. Run `rtk uv run pytest -q tests/test_test_isolation.py` from `tidaldl-py/` and confirm the collection-time assertion fails first.
- [x] 5.2 Update only `tidaldl-py/tests/conftest.py`: before importing `tidal_dl.config`, set a session-temporary config environment; then define an autouse fixture using `tmp_path` and `monkeypatch` to set a per-test config directory and call `reset_singletons()` before and after each test.
- [x] 5.3 Run `rtk uv run pytest -q tests/test_test_isolation.py tests/test_gui_lifespan.py tests/test_gui_api.py tests/test_home.py tests/test_library_db.py` green from `tidaldl-py/`.
- [x] 5.4 From the repository root run `rtk proxy env PYTHONNOUSERSITE=1 uv run --project tidaldl-py --extra test python -m pytest tidaldl-py/tests -q`; require zero failures, no real-config path in captured output, and no scan thread/process after pytest exits.

## 6. Release gates and documentation

- [x] 6.1 Update `tidaldl-py/updatelog.md` with concise v1.7.1 user-facing fixes and insert a fresh `## Unreleased` section above them so `scripts/release_version.py` can convert it to the dated release section.
- [x] 6.2 From the repository root run `rtk uv run --project tidaldl-py python scripts/release_version.py bump patch --date 2026-08-05`, then `rtk uv run --project tidaldl-py python scripts/release_version.py check`; require every release file to report 1.7.1 before packaging.
- [x] 6.3 From `tidaldl-py/`, run `rtk uv sync --extra build`, `rtk bun install --frozen-lockfile`, and `rtk bunx tauri build --bundles app,dmg`. Launch `src-tauri/target/release/bundle/macos/music-dl.app/Contents/MacOS/music-dl` with a temporary `MUSIC_DL_CONFIG_DIR`, record its metadata/wrapper/descendant PIDs and listening port, then quit it and prove all recorded PIDs and the port are gone. Relaunch and prove fresh PIDs. In that same final v1.7.1 app, replay local Search and Favorite clicks with no Tidal stream request and capture artist-gallery request/screenshot evidence for eager first-row art and lazy later art.

  Evidence: `verification.md`.
- [x] 6.4 Perform a Ponytail diff audit and remove speculative code, duplicated helpers, and any dependency or module not required by this change.
- [x] 6.5 Dispatch final specification and code-quality reviews, fix all important findings, re-run the affected gates, and validate `rtk openspec validate fix-v1-7-playback-lifecycle --strict`.
- [x] 6.6 Mark OpenSpec tasks complete, commit the verified branch once, and present integration/release options without tagging or publishing until selected.
