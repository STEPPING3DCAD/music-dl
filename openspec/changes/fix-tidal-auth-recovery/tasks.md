## 1. Frontend reset confirmation

- [ ] 1.1 Update `tidaldl-py/tests/views-decisions.test.js` so reset-button wiring must call the existing `inlineConfirm` before `_resetTidalConnection`, and the reset action itself no longer depends on `window.confirm`.
- [ ] 1.2 From `tidaldl-py/`, run `rtk bun test tests/views-decisions.test.js` and record the expected red failure against the current `window.confirm` implementation.
- [ ] 1.3 Minimally update `tidaldl-py/tidal_dl/gui/static/views.js`: keep `_resetTidalConnection` as the existing reset action and wrap its button invocation with `inlineConfirm`; do not add a dependency, dialog helper, or immediate-delete path.
- [ ] 1.4 Re-run `rtk bun test tests/views-decisions.test.js` and require all reset confirmation, success, and failure decisions to pass.

## 2. Timezone-safe persistence and reconnect repair

- [ ] 2.1 Add focused tests in `tidaldl-py/tests/test_token_refresh.py` proving naive Tidal expiry datetimes serialize as UTC and aware datetimes preserve their instant.
- [ ] 2.2 Update `tidaldl-py/tests/test_gui_auth_login.py` to inject its fake Tidal object through the existing FastAPI dependency pattern and require `auth_login` to persist a remotely valid existing session before returning `already_logged_in`.
- [ ] 2.3 From the repository root, run `rtk uv run --project tidaldl-py --extra test python -m pytest tidaldl-py/tests/test_token_refresh.py tidaldl-py/tests/test_gui_auth_login.py -q` and record the expected red failures for timezone serialization and reconnect persistence.
- [ ] 2.4 Minimally update `tidaldl-py/tidal_dl/config.py` so naive datetime expiries receive `timezone.utc` before conversion; preserve aware datetime and numeric behavior without parsing JWTs or changing token JSON shape.
- [ ] 2.5 Minimally update `tidaldl-py/tidal_dl/gui/api/settings.py` so `auth_login` uses dependency injection and re-persists a session only after `check_login()` confirms it remains valid.
- [ ] 2.6 Re-run the focused Python command and require all authentication tests to pass.

## 3. Documentation and complete verification

- [ ] 3.1 Add a concise pending-release entry to `tidaldl-py/updatelog.md` covering desktop reset confirmation, UTC-safe expiry persistence, and reconnect repair for GitHub issue #115.
- [ ] 3.2 Run `rtk uv run --project tidaldl-py --extra test python -m pytest tidaldl-py/tests -q` and `rtk bun test tests/*.test.js` from `tidaldl-py/`; require zero failures.
- [ ] 3.3 Run `rtk uv run --project tidaldl-py --extra test ruff check tidaldl-py/tidal_dl/config.py tidaldl-py/tidal_dl/gui/api/settings.py tidaldl-py/tests/test_token_refresh.py tidaldl-py/tests/test_gui_auth_login.py` and require zero findings.
- [ ] 3.4 From the repository root run `rtk uv sync --project tidaldl-py --extra build`; then from `tidaldl-py/` run `rtk bun install` and `rtk bunx tauri build --bundles app --config '{"bundle":{"createUpdaterArtifacts":false}}'`. Launch the unsigned app with an isolated temporary config containing only fake future-dated credentials, verify Reset Tidal connection opens the in-app confirmation, cancel preserves the fixture, Continue removes only the fixture token, and quit removes the packaged process tree.
- [ ] 3.5 Record source, test, and packaged-app evidence in `openspec/changes/fix-tidal-auth-recovery/verification.md`, then run `rtk openspec validate fix-tidal-auth-recovery --strict`.
- [ ] 3.6 Review the final diff for unnecessary complexity with Ponytail and for correctness against every scenario; remove any speculative code and rerun affected checks.
