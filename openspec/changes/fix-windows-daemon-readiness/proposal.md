## Why

The Windows desktop app can report `Timed out waiting for daemon readiness` even when its packaged Python daemon is healthy. The Tauri shell rejects the valid PyInstaller child process because Windows lacks the Unix `ps` command used for PID ancestry checks, and Windows hosts without `HOME` cannot resolve the daemon metadata path consistently with Python.

## What Changes

- Accept a healthy `tauri-sidecar` daemon on Windows without requiring Unix PID ancestry resolution.
- Resolve the Windows daemon metadata path from `HOMEDRIVE` and `HOMEPATH` when `HOME` is unavailable.
- Add focused Rust regression coverage for Windows sidecar matching and config-path fallback.
- Run Rust desktop-shell tests in the existing cross-platform desktop build workflow before packaging.
- Correct the Windows config path documented in the GitHub bug-report template.
- Verify a packaged Windows build on the designated PLEX-MINI test host.

## Capabilities

### New Capabilities

- `desktop-daemon-readiness`: Defines how the desktop shell discovers and validates its local daemon across supported operating systems.

### Modified Capabilities

None.

## Impact

- Affected code: `tidaldl-py/src-tauri/src/lib.rs` and its Rust unit tests.
- Affected CI and documentation: `.github/workflows/build-desktop.yml` and `.github/ISSUE_TEMPLATE/bug-report.yml`.
- Dependencies: no new runtime or build dependencies.
- Systems: Windows desktop startup behavior; Unix PID validation remains unchanged.
