# Tidal Connection Reset Design

## Goal

Let users remove a stale or unwanted Tidal OAuth connection from Settings and
return the running app to a clean, logged-out state without restarting it.

## Behavior

- Settings shows **Reset Tidal connection** when auth is connected, expired, or
  unavailable.
- The browser asks for confirmation before reset.
- Reset deletes the stored OAuth token, clears in-memory token fields, rebuilds
  an unauthenticated Tidal session, and returns login polling state to `idle`.
- Reset invalidates any pending OAuth attempt so its worker cannot persist a
  token or replace `idle` with a stale terminal state after reset.
- Reset itself makes no request to Tidal.
- After reset, Settings shows **Not logged in to Tidal** and the existing
  **Log in to Tidal** action. OAuth starts only when the user presses Login.

## Implementation

Extend existing ownership boundaries:

- `Tidal.logout()` prepares a fresh session, removes the token file, then swaps
  session and token state as one successful operation instead of deleting the
  `session` attribute.
- `gui/api/settings.py` exposes `POST /auth/reset`. While holding the existing
  login lock, it first completes `Tidal.logout()`. Only after that succeeds does
  it increment the OAuth attempt generation and replace login state with exactly
  `{"status": "idle"}`. It then returns the fixed local payload
  `{"status": "reset", "auth_state": "not_configured"}` without calling
  `check_login()` or another provider method.
- Each OAuth worker captures its generation and verifies it under the login lock
  before finalizing or updating state. A stale worker exits without persisting a
  token or changing reset state.
- `gui/static/views.js` renders the reset action. Success stops login polling,
  dismisses the device-code modal, refreshes Settings auth status and the global
  connection indicator, and never invokes `triggerLogin()`.

No new module is justified. Session lifecycle already belongs to `Tidal`, auth
HTTP behavior belongs to the Settings router, and account controls belong to the
existing Settings auth renderer.

## Error Handling

- Session construction completes before token-file deletion. If construction or
  token deletion fails, existing in-memory session and token fields remain
  unchanged. Only a successful deletion permits the prepared session and empty
  token model to replace current state.
- Token-file deletion remains idempotent when no token exists.
- Backend reset failure returns a clear HTTP 500 without starting OAuth.
- Failed reset preserves OAuth generation and login state exactly. A pending
  worker remains authoritative and can finish normally; reset never leaves a
  login attempt permanently pending by invalidating its worker early.
- Frontend failure keeps current status visible and shows an error toast.
- Reset invalidates concurrent login completion with the OAuth generation guard;
  it does not depend on holding the login lock during the five-minute wait.

## Verification

- Unit test proves logout removes the token and leaves a usable unauthenticated
  session.
- Unit failure-injection tests prove session-construction and token-deletion
  failures leave old disk and memory state intact.
- API tests use provider methods that fail on call and prove reset returns the
  fixed logged-out payload, clears login polling state, and invalidates a stale
  OAuth worker without making a provider request.
- API failure-injection test starts from a pending login and proves failed reset
  preserves generation and login state while its existing worker remains
  authoritative.
- Executable Bun tests cover the auth-state visibility matrix: connected,
  expired, and unavailable show Reset; not-configured does not. They also prove
  cancel sends nothing, confirm sends exactly one `POST /auth/reset`, success
  does not call login and refreshes both status surfaces, and failure preserves
  rendered status while showing an error toast.
- Full Python and Bun suites pass.
- Manual localhost check confirms reset control renders and reset makes no
  provider request.
