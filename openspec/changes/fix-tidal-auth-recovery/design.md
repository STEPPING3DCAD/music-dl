## Context

Tidal authentication crosses three existing boundaries: browser controls in `views.js`, OAuth orchestration in the settings API, and token serialization in `config.py`. Tauri's macOS WebView does not surface the reset control's `window.confirm`, while `tidalapi 0.8.11` supplies a naive `datetime.utcnow()` expiry that Python's `datetime.timestamp()` interprets as local time. GitHub issue #115 shows the resulting loop: OAuth succeeds, a shifted expiry is saved, and reconnect briefly reports success before local status marks the same credentials expired.

## Goals / Non-Goals

**Goals:**

- Make reset confirmation work in browser and packaged desktop modes.
- Persist Tidal's naive expiry as UTC on every new login or refresh.
- Repair a valid credential file written with the old timezone-shifted timestamp when the user reconnects.
- Preserve current API response shapes and authentication safety.

**Non-Goals:**

- Replace `tidalapi`, change token-file format, or add encryption.
- Add a Tauri dialog plugin or new frontend abstraction.
- Claim remote playback availability before a stream request proves it.

## Decisions

1. **Reuse `inlineConfirm` for reset.** The existing accessible in-page dialog already works in browser and Tauri modes. The reset action remains unchanged and runs only from the dialog's Continue callback. A new Tauri dialog dependency would duplicate an existing capability; removing confirmation would risk accidental credential deletion.

2. **Normalize at serialization.** When `session.expiry_time` is a naive datetime, `token_persist` will attach `timezone.utc` before calling `timestamp()`. Aware datetimes and numeric values retain their represented instant. This fixes the shared persistence seam for OAuth login and token refresh without parsing JWT internals.

3. **Repair through the existing reconnect path.** If `/auth/login` finds that the current Tidal session still passes `check_login()`, it will persist that session before returning `already_logged_in`. This rewrites legacy shifted timestamps using the corrected serializer; genuinely invalid sessions continue into the existing OAuth flow.

4. **Use focused regression tests.** Bun tests cover real reset-button wiring to `inlineConfirm`; Python tests cover UTC serialization and the reconnect repair call. No broad refactor is needed.

## Risks / Trade-offs

- **A legacy token is already invalid remotely** → `check_login()` returns false and the normal OAuth flow remains available.
- **A third-party future release returns an aware datetime** → preserve its timezone-aware instant rather than forcing UTC fields.
- **The in-page dialog callback fails** → existing reset error toast and unchanged rendered state remain in force.

## Migration Plan

No eager migration. New and refreshed tokens serialize correctly. Existing affected credentials repair when Re-connect confirms the remote session is still valid; otherwise the user can reset and complete OAuth again. Rollback is the normal code rollback because token JSON shape is unchanged.

## Open Questions

None.
