# Tidal Connection Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Settings action that safely removes stored Tidal OAuth state and leaves the running app ready for an explicit future login.

**Architecture:** Extend `Tidal.logout()` for atomic same-process reset, then expose it through the existing Settings auth router with OAuth-generation invalidation. Keep UI behavior in the existing Settings renderer and test it through executable Bun helpers. Reset uses only local state and never starts OAuth or checks provider status.

**Tech Stack:** Python 3.13, FastAPI, tidalapi, vanilla JavaScript, Bun test, pytest, Ruff.

---

### Task 1: Atomic Tidal Session Reset

**Files:**
- Modify: `tidaldl-py/tidal_dl/config.py:653-662`
- Test: `tidaldl-py/tests/test_token_refresh.py`

- [ ] **Step 1: Write failing success and failure-atomicity tests**

Test that `logout()` prepares a fresh unauthenticated `Session`, deletes an
existing token, clears `ModelToken`, resets Atmos/storage state, and preserves
the old session/data when session construction or token unlink raises. Assert
the fresh session keeps `item_limit=10000`, `certifi.where()` TLS verification,
normal managed API credentials, configured audio quality, and high video
quality.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --project tidaldl-py pytest -q tidaldl-py/tests/test_token_refresh.py -k logout`

Expected: failures because current method deletes `session` and mutates before
all failure points complete.

- [ ] **Step 3: Implement minimal atomic reset**

Prepare and configure a fresh `Session` in local variables with the same
`TidalConfig(item_limit=10000)` and `certifi.where()` CA bundle used by startup.
Capture normal default credentials, apply the first valid managed API key from
the local key registry, and apply configured audio/high video quality without
calling provider methods. Delete token only after preparation succeeds. Then
assign fresh session, normal credential fields, `ModelToken()`,
`token_from_storage = False`, and `is_atmos_session = False`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run --project tidaldl-py pytest -q tidaldl-py/tests/test_token_refresh.py -k logout`

- [ ] **Step 5: Commit**

Commit: `fix: reset Tidal session in process`

### Task 2: Transactional Reset API and OAuth Invalidation

**Files:**
- Modify: `tidaldl-py/tidal_dl/gui/api/settings.py:163-238`
- Test: `tidaldl-py/tests/test_gui_auth_login.py`
- Test: `tidaldl-py/tests/test_gui_api.py`

- [ ] **Step 1: Write failing API and stale-worker tests**

Cover fixed reset response, no calls to `check_login`, refresh, or OAuth; exact
idle-state replacement; successful generation invalidation; stale worker exit;
and failed reset preserving generation plus pending login state.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --project tidaldl-py pytest -q tidaldl-py/tests/test_gui_auth_login.py tidaldl-py/tests/test_gui_api.py -k 'reset or stale'`

Expected: failures because reset route and generation guard do not exist.

- [ ] **Step 3: Implement route and generation guard**

Add `_login_generation`. Login workers capture it and check it before any state
update or `login_finalize()`. `POST /auth/reset` holds `_login_lock`, calls
`tidal.logout()` first, and only on success increments generation and replaces
state with `{"status": "idle"}`. Return fixed local response; map failure to a
generic HTTP 500.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run --project tidaldl-py pytest -q tidaldl-py/tests/test_gui_auth_login.py tidaldl-py/tests/test_gui_api.py -k 'reset or stale'`

- [ ] **Step 5: Commit**

Commit: `fix: expose transactional Tidal reset`

### Task 3: Settings Account Reset Control

**Files:**
- Modify: `tidaldl-py/tidal_dl/gui/static/views.js:3926-3950`
- Modify: `tidaldl-py/tidal_dl/gui/static/player.js:1392-1452`
- Test: `tidaldl-py/tests/views-decisions.test.js`
- Test: `tidaldl-py/tests/test_gui_tidal_auth_recovery.py`

- [ ] **Step 1: Write failing executable Bun behavior tests**

Cover visibility for `connected|expired|unavailable`, absence for
`not_configured`, confirmation cancellation, one reset POST on confirmation,
no login call, poll/modal cleanup, both status refreshes, and failure toast with
existing rendered state preserved.

- [ ] **Step 2: Run tests and verify RED**

Run: `bun test tidaldl-py/tests/views-decisions.test.js`

Expected: failures because reset decision/action helpers do not exist.

- [ ] **Step 3: Implement minimal UI behavior**

Add small pure visibility decision plus async reset action using existing
`api`, `toast`, `loadAuthStatus`, `refreshStatusLights`, `_loginPoll`, and device
modal helpers. Render command button in existing auth row. Do not call
`triggerLogin()`.

- [ ] **Step 4: Run Bun and static-source tests**

Run: `bun test tidaldl-py/tests/views-decisions.test.js`

Run: `uv run --project tidaldl-py pytest -q tidaldl-py/tests/test_gui_tidal_auth_recovery.py`

- [ ] **Step 5: Commit**

Commit: `feat: add Tidal reset control`

### Task 4: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify: `tidaldl-py/docs/backend-guide.md`
- Modify: `tidaldl-py/updatelog.md`
- Modify ignored QA log: `output/qa/local-server-e2e-2026-07-09.md`

- [ ] **Step 1: Document reset semantics and provider-safety boundary**

State reset deletes local OAuth credentials, performs no Tidal request, and
requires explicit Login afterward.

- [ ] **Step 2: Run focused and full verification**

Run changed-file Ruff, focused pytest/Bun tests,
`uv run --project tidaldl-py pytest -q`, `bun test`, and `git diff --check`.

- [ ] **Step 3: Restart source server and manually verify**

Verify Settings control across auth states using local test state or a temporary
token fixture. Confirm reset endpoint logs only localhost request and no provider
request. Do not reset the user's real token without explicit confirmation.

- [ ] **Step 4: Commit documentation**

Commit: `docs: document Tidal connection reset`
