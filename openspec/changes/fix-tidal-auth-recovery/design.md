## Context

Tidal authentication crosses three existing boundaries: browser controls in `views.js`, OAuth orchestration in the settings API, and token serialization in `config.py`. Tauri's macOS WebView does not surface the reset control's `window.confirm`, while `tidalapi 0.8.11` supplies a naive `datetime.utcnow()` expiry that Python's `datetime.timestamp()` interprets as local time. GitHub issue #115 shows the resulting loop: OAuth succeeds, a shifted expiry is saved, and reconnect briefly reports success before local status marks the same credentials expired.

## Goals / Non-Goals

**Goals:**

- Make reset confirmation work in browser and packaged desktop modes.
- Persist Tidal's naive expiry as UTC on every new login or refresh.
- Repair a valid credential file written with the old timezone-shifted timestamp when the user reconnects.
- Preserve current API response shapes and authentication safety.
- Publish a stable signed patch release and prove update discovery from v1.7.1.

**Non-Goals:**

- Replace `tidalapi`, change token-file format, or add encryption.
- Add a Tauri dialog plugin or new frontend abstraction.
- Claim remote playback availability before a stream request proves it.

## Decisions

1. **Reuse `inlineConfirm` for reset.** The existing accessible in-page dialog already works in browser and Tauri modes. The reset action remains unchanged and runs only from the dialog's Continue callback. A new Tauri dialog dependency would duplicate an existing capability; removing confirmation would risk accidental credential deletion.

2. **Normalize at the persistence boundary.** When `session.expiry_time` is a naive datetime, `token_persist` will attach UTC before calling `timestamp()`. Stored numeric epochs are reconstructed as UTC-aware datetimes so a correct token round-trips without another timezone shift. Aware datetimes and numeric values retain their represented instant. This fixes the shared persistence seam for OAuth login, stored-session loading, and token refresh without parsing JWT internals.

3. **Repair through the existing reconnect path.** If `/auth/login` finds that the current Tidal session still passes `check_login()`, it will use the existing refresh token to obtain a fresh provider expiry, persist it through the corrected serializer, and then return `already_logged_in`. A missing or failed refresh continues into the existing OAuth flow instead of claiming repair succeeded.

4. **Use focused regression tests.** Bun tests cover real reset-button wiring to `inlineConfirm`; Python tests cover UTC serialization and the reconnect repair call. No broad refactor is needed.

5. **Release through the existing stable updater pipeline.** After source and packaged-app verification, the repository release helper will bump all tracked metadata to v1.7.2. The hotfix merges before an annotated `v1.7.2` tag is pushed from the merged commit. The existing tag-triggered GitHub workflow owns signed macOS, Linux, and Windows artifacts plus `latest.json`; local packaging remains unsigned with updater artifacts disabled.

## Risks / Trade-offs

- **A legacy token is already invalid remotely** → `check_login()` returns false and the normal OAuth flow remains available.
- **A third-party future release returns an aware datetime** → preserve its timezone-aware instant rather than forcing UTC fields.
- **The in-page dialog callback fails** → existing reset error toast and unchanged rendered state remain in force.
- **A platform release job or updater manifest fails** → v1.7.2 is not considered deployed until every signed asset, signature, and `latest.json` is present and a v1.7.1 app reports the update.

## Migration Plan

No eager token migration. New and refreshed tokens serialize correctly. Existing affected credentials repair when Re-connect confirms the remote session is still valid; otherwise the user can reset and complete OAuth again. Release rollback follows the existing stable-release process because token JSON shape is unchanged.

## Open Questions

None.
