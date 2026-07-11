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
- Reset itself makes no request to Tidal.
- After reset, Settings shows **Not logged in to Tidal** and the existing
  **Log in to Tidal** action. OAuth starts only when the user presses Login.

## Implementation

Extend existing ownership boundaries:

- `Tidal.logout()` performs a complete same-process session reset instead of
  deleting the `session` attribute.
- `gui/api/settings.py` exposes `POST /auth/reset`, serializes it with existing
  login state, and returns the new auth state.
- `gui/static/views.js` renders the reset action and refreshes Settings auth
  status after success.

No new module is justified. Session lifecycle already belongs to `Tidal`, auth
HTTP behavior belongs to the Settings router, and account controls belong to the
existing Settings auth renderer.

## Error Handling

- Token-file deletion remains idempotent.
- Backend reset failure returns a clear HTTP 500 without starting OAuth.
- Frontend failure keeps current status visible and shows an error toast.
- Concurrent login/reset operations use the existing auth lock.

## Verification

- Unit test proves logout removes the token and leaves a usable unauthenticated
  session.
- API test proves reset returns logged-out state and clears login polling state.
- Static UI test proves confirmation, reset request, status refresh, and error
  feedback exist.
- Full Python and Bun suites pass.
- Manual localhost check confirms reset control renders and reset makes no
  provider request.
