## Context

The Tauri shell launches the packaged `music-dl-server` sidecar and waits for `daemon.json` plus a healthy loopback endpoint. PyInstaller uses a wrapper process and a child process on Windows. The wrapper PID returned to Tauri differs from the PID written by the Python daemon. Current ancestry validation shells out to Unix `ps`, which is absent on Windows, so a healthy daemon is rejected until the 30-second timeout.

The failure was reproduced on Windows 11 build 26200 with v1.6.8: the daemon published ready metadata and passed health checks within five seconds, while Tauri timed out and killed the wrapper at 30 seconds. The Python daemon also falls back to `HOMEDRIVE` plus `HOMEPATH` when `HOME` is absent, but the Rust metadata reader does not.

Packaged verification of the readiness fix exposed the matching shutdown defect: closing Tauri terminated the PyInstaller wrapper but left its child daemon running. All eight lifecycle cleanup paths call `CommandChild.kill()` directly, so each can orphan the descendant on Windows.

## Goals / Non-Goals

**Goals:**

- Let the Windows desktop shell accept its healthy packaged PyInstaller daemon.
- Keep existing app, mode, status, loopback URL, and live health validation.
- Match Python's Windows home-directory fallback without moving existing config.
- Preserve strict PID or ancestor matching on Unix.
- Terminate the owned Windows wrapper and descendant daemon together on every lifecycle cleanup path.
- Add the smallest regression coverage that protects both Windows failures.

**Non-Goals:**

- Migrate config to `%APPDATA%` or change existing config layout.
- Add a cross-process nonce protocol or a Windows process-inspection dependency.
- Refactor daemon supervision or change startup timeouts.
- Add a daemon shutdown protocol or persist the daemon child PID solely for cleanup.
- Change Hyper-V, host networking, or unrelated Windows services during verification.

## Decisions

### Use verified metadata instead of Unix ancestry on Windows

On Windows, sidecar metadata will match when its mode is `tauri-sidecar`; the existing metadata and health validation remains mandatory before readiness succeeds. On non-Windows targets, matching will continue to require the exact spawned PID or a verified descendant PID.

This is the minimum complete fix. A native Windows process-tree dependency would add build and maintenance cost only to duplicate identity signals already checked through the sidecar mode, application name, ready status, constrained loopback URL, and live health response. A nonce handshake would be stronger but would expand the Rust/Python protocol across multiple files without a present threat or failure requiring it.

### Mirror Python's Windows home fallback

Rust will retain `MUSIC_DL_CONFIG_DIR` as the highest-precedence override and `HOME/.config/music-dl` as the normal path. When `HOME` is absent on Windows, it will combine `HOMEDRIVE` and `HOMEPATH`, matching the Python daemon's established behavior. Existing config stays in place.

### Keep changes in existing modules

Implementation and tests remain in `src-tauri/src/lib.rs`; no new module or dependency is justified. The bug-report template will name `%USERPROFILE%\.config\music-dl` so support instructions match runtime behavior.

The existing `build-desktop.yml` matrix will run `cargo test` after platform sidecar setup and before packaging. This supplies the Windows-only red/green proof without creating another workflow or installing a permanent development toolchain on PLEX-MINI.

The first green workflow attempt exposed pre-existing checks for deleted `static/app.js`. CI will run the existing split-bundle static-asset test on every platform, while the local Tauri build command will reuse its dependency-free `read_gui_js` helper. This removes duplicated platform checks and preserves local builds that install only the build extras.

### Use native Windows tree termination through one shared helper

Every owned-sidecar cleanup path will call one helper in `src-tauri/src/lib.rs`. On Windows the helper will run `taskkill /PID <wrapper-pid> /T /F`, which asks the operating system to terminate the wrapper and its descendants. If `taskkill` cannot start or reports failure, the helper will fall back to the existing direct wrapper kill and return that result. Non-Windows builds will retain the existing `CommandChild.kill()` behavior.

Patching only the window-destroyed handler would leave readiness timeout, restart, and explicit stop paths broken. Storing the daemon child PID or adding a shutdown endpoint would expand state or protocol across files. One native command helper, reused by all eight callers, fixes the common root without a new module, dependency, or protocol.

## Risks / Trade-offs

- [A second local sidecar becomes ready during the spawn window] → Existing pre-spawn reuse, `tauri-sidecar` mode, application identity, loopback URL validation, ready status, and live health checks constrain the accepted daemon.
- [Windows environment lacks both `HOME` and drive/path variables] → Preserve the current explicit path error; do not guess a writable directory.
- [Packaged behavior differs from Rust unit tests] → Run Rust tests in the existing Windows build job, then install that job's MSI and repeat the timed process/metadata capture on PLEX-MINI.
- [`taskkill` is unavailable or fails] → Fall back to direct wrapper termination and report the existing kill result; packaged PLEX-MINI verification proves the normal Windows path removes both processes.

## Migration Plan

1. Ship as a non-breaking desktop startup fix.
2. Existing config remains at the same path; no data migration runs.
3. Roll back the release if packaged Windows verification fails; no persisted schema changes require reversal.

## Open Questions

None.
