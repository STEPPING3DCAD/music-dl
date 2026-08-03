## 1. Regression Coverage

- [ ] 1.1 Add a Windows-only Rust test proving valid `tauri-sidecar` metadata can use a PyInstaller child PID different from the spawned wrapper PID, while preserving wrong-mode, failed-health, and unrelated-Unix-process negative coverage.
- [ ] 1.2 Add pure Rust tests for daemon metadata path precedence and the Windows `HOMEDRIVE` plus `HOMEPATH` fallback.
- [ ] 1.3 Run the focused Rust tests before implementation and record the expected failing assertions.

## 2. Minimal Implementation

- [ ] 2.1 Make Windows sidecar matching rely on sidecar mode plus the existing metadata and health validation while preserving Unix PID ancestry checks.
- [ ] 2.2 Make Rust daemon metadata path resolution match Python's Windows home fallback without adding a module or dependency.
- [ ] 2.3 Correct the Windows config path in the GitHub bug-report template.

## 3. Verification

- [ ] 3.1 Run focused and full Rust tests for `tidaldl-py/src-tauri`.
- [ ] 3.2 Validate the OpenSpec change and run relevant repository documentation checks.
- [ ] 3.3 Perform the required Ponytail diff review and remove unnecessary complexity.
- [ ] 3.4 Build and install the packaged Windows app on PLEX-MINI, repeat the timed readiness capture, and verify no timeout or orphaned daemon.
- [ ] 3.5 Uninstall the test package and remove only test-created `music-dl` config and temporary files from PLEX-MINI.
