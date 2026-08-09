# Tidal auth recovery verification

Verified on macOS arm64 on 2026-08-08 from `codex/fix-tidal-auth-recovery`.

## Regression cycle

- Frontend red: the focused Bun test failed because `views.js` still contained the reset `window.confirm`; removing `window` from the extracted helper also made the reset-action tests fail until confirmation moved to the button wiring.
- Backend red: the naive expiry assertion observed `1767344645.0` instead of UTC epoch `1767323045.0`; both direct `auth_login(fake_tidal)` calls failed because the route accepted no injected argument.
- Frontend green: `bun test tests/views-decisions.test.js` passed `10` tests with `0` failures.
- Backend green: the final focused pytest command passed `29` tests with `0` failures, including correct-epoch round-trip, refresh-before-persist repair, and failed-refresh OAuth fallback.

## Source verification

- Full Python suite after the final reconnect repair: `671 passed, 1 skipped` in `34.85s`.
- Full Bun suite: `40 pass, 0 fail`, `115` assertions.
- Rust formatting passed; Rust tests passed `17` tests across `3` suites.
- Focused Ruff checks for imports, undefined names, UTC usage, and the changed test files passed with zero findings.
- The repository's existing whole-file Ruff command still reports unrelated baseline findings. A focused `B008` run proves the new `auth_login` dependency line is suppressed consistently while the unchanged `auth_status` and `auth_reset` lines remain the only two `B008` findings.
- `git diff --check` passed.
- Independent pre-merge review found no remaining issues after stored-epoch round-trip and refresh-before-persist corrections.

## ChatGPT Browser web acceptance

The source GUI ran on `127.0.0.1:28876` with an isolated temporary `MUSIC_DL_CONFIG_DIR`, an empty music directory, and fake future-dated credentials.

- Settings showed `credentials saved` and Reset Tidal connection.
- Reset opened the in-page dialog with Cancel and Continue controls; no native browser dialog was involved.
- Cancel closed the dialog and preserved the fake `token.json`.
- Continue removed only the fake token, changed the sidebar and Settings account status to `log in`, removed the reset action, and showed `Tidal connection reset`.

## Unsigned packaged-app acceptance

- `uv sync --project tidaldl-py --extra build` and `bun install` passed.
- `bunx tauri build --bundles app --config '{"bundle":{"createUpdaterArtifacts":false}}'` passed and produced `tidaldl-py/src-tauri/target/release/bundle/macos/music-dl.app`.
- The packaged app ran from the build directory with a separate isolated temporary config and fake future-dated credentials. Because another local source server already owned `8765`, the sidecar correctly selected `127.0.0.1:8766`.
- Computer Use opened Settings and observed the in-app reset confirmation. Cancel preserved the fake token. Continue removed it, changed both auth surfaces to `log in`, and showed the reset success status.
- Normal app Quit returned exit `0`. The owned wrapper/worker pair and listener were gone on the follow-up teardown check; no real config, token, or library path was used.

## Release verification

- `scripts/release_version.py bump patch` updated the Python, Rust, Tauri, Cargo lock, uv lock, and changelog metadata to v1.7.2.
- `scripts/release_version.py check` reports that all release version files agree on `1.7.2`.
- Focused release-version and edge-channel tests passed `11` tests with zero failures.
- Pending: merge, tag, signed GitHub build, release assets, `latest.json`, and installed-v1.7.1 updater-notification checks.
