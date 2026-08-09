## 1. Frontend reset confirmation

- [x] 1.1 Update `tidaldl-py/tests/views-decisions.test.js` so reset-button wiring must call the existing `inlineConfirm` before `_resetTidalConnection`, and the reset action itself no longer depends on `window.confirm`.
- [x] 1.2 From `tidaldl-py/`, run `rtk bun test tests/views-decisions.test.js` and record the expected red failure against the current `window.confirm` implementation.
- [x] 1.3 Minimally update `tidaldl-py/tidal_dl/gui/static/views.js`: keep `_resetTidalConnection` as the existing reset action and wrap its button invocation with `inlineConfirm`; do not add a dependency, dialog helper, or immediate-delete path.
- [x] 1.4 Re-run `rtk bun test tests/views-decisions.test.js` and require all reset confirmation, success, and failure decisions to pass.

## 2. Timezone-safe persistence and reconnect repair

- [x] 2.1 Add focused tests in `tidaldl-py/tests/test_token_refresh.py` proving naive Tidal expiry datetimes serialize as UTC, aware datetimes preserve their instant, and a stored epoch round-trips unchanged.
- [x] 2.2 Update `tidaldl-py/tests/test_gui_auth_login.py` to inject its fake Tidal object through the existing FastAPI dependency pattern and require `auth_login` to refresh and persist a remotely valid existing session before returning `already_logged_in`.
- [x] 2.3 From the repository root, run `rtk uv run --project tidaldl-py --extra test python -m pytest tidaldl-py/tests/test_token_refresh.py tidaldl-py/tests/test_gui_auth_login.py -q` and record the expected red failures for timezone serialization and reconnect persistence.
- [x] 2.4 Minimally update `tidaldl-py/tidal_dl/config.py` so naive Tidal datetimes receive UTC before conversion and stored epochs reload as UTC-aware; preserve aware datetime and numeric behavior without parsing JWTs or changing token JSON shape.
- [x] 2.5 Minimally update `tidaldl-py/tidal_dl/gui/api/settings.py` so `auth_login` uses dependency injection, refreshes and persists a remotely valid session, and falls through to OAuth if refresh cannot repair it.
- [x] 2.6 Re-run the focused Python command and require all authentication tests to pass.

## 3. Documentation and complete verification

- [x] 3.1 Add a concise pending-release entry to `tidaldl-py/updatelog.md` covering desktop reset confirmation, UTC-safe expiry persistence, and reconnect repair for GitHub issue #115.
- [x] 3.2 Run `rtk uv run --project tidaldl-py --extra test python -m pytest tidaldl-py/tests -q` and `rtk bun test tests/*.test.js` from `tidaldl-py/`; require zero failures.
- [x] 3.3 Run focused Ruff checks for imports, undefined names, and the new timezone handling; document the unchanged whole-file lint baseline and require zero new findings.
- [x] 3.4 From the repository root run `rtk uv sync --project tidaldl-py --extra build`; then from `tidaldl-py/` run `rtk bun install` and `rtk bunx tauri build --bundles app --config '{"bundle":{"createUpdaterArtifacts":false}}'`. Launch the unsigned app with an isolated temporary config containing only fake future-dated credentials, verify Reset Tidal connection opens the in-app confirmation, cancel preserves the fixture, Continue removes only the fixture token, and quit removes the packaged process tree.
- [x] 3.5 Record source, test, and packaged-app evidence in `openspec/changes/fix-tidal-auth-recovery/verification.md`, then run `rtk openspec validate fix-tidal-auth-recovery --strict`.
- [x] 3.6 Review the final diff for unnecessary complexity with Ponytail and for correctness against every scenario; remove any speculative code and rerun affected checks.

## 4. Stable v1.7.2 deployment

- [x] 4.1 Use `scripts/release_version.py bump patch` to update all tracked release metadata and turn the pending changelog entry into v1.7.2; run the focused release-version and edge-channel tests plus `scripts/release_version.py check`.
- [ ] 4.2 Commit the verified implementation and release metadata, push the SSH-backed hotfix branch, open a ready pull request, and require the current commit's CI checks to pass before merge.
- [ ] 4.3 Merge the hotfix, create annotated tag `v1.7.2` from the merged `master` commit, push the tag, and wait for every `build-desktop` platform job and manifest-publishing job to succeed.
- [ ] 4.4 Verify the v1.7.2 GitHub release contains `latest.json`, signed macOS, Linux, and Windows updater artifacts, and matching signature files; verify `latest.json` advertises `1.7.2`.
- [ ] 4.5 Launch the installed v1.7.1 app, use its Check for Updates control, and verify it shows the v1.7.2 update notification without installing the update.
- [ ] 4.6 Append release-workflow, asset, manifest, and updater-notification evidence to `verification.md`; run strict OpenSpec validation and close GitHub issue #115 with the verified release link.
