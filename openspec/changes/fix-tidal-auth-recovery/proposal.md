## Why

Desktop users on v1.7.1 can be trapped in an expired Tidal state: the packaged Tauri WebView suppresses the reset control's native browser confirmation, and Tidal's naive UTC expiry is serialized as local time. GitHub issue #115 confirms that a completed OAuth login can therefore write credentials while the UI immediately continues to report an expired session.

## What Changes

- Show the existing in-app confirmation before resetting saved Tidal credentials, including in the packaged desktop WebView.
- Persist naive Tidal expiry datetimes as UTC so local timezone offsets cannot shorten token lifetime.
- Re-persist a still-valid session during reconnect so credentials written by affected releases repair themselves without another OAuth grant.
- Add focused frontend and backend regressions for reset confirmation, UTC serialization, and reconnect repair.

## Capabilities

### New Capabilities

- `tidal-auth-recovery`: Defines reliable desktop reset confirmation, timezone-safe token expiry persistence, and repair of valid legacy credentials during reconnect.

### Modified Capabilities

None.

## Impact

- Frontend: `tidaldl-py/tidal_dl/gui/static/views.js` and its Bun decision tests.
- Backend: `tidaldl-py/tidal_dl/config.py`, `tidaldl-py/tidal_dl/gui/api/settings.py`, and focused Python tests.
- API shape and dependencies remain unchanged.
- User report: GitHub issue #115.
