# Local-First QA Fixes Design

## Goal

Fix the five defects found in local-server end-to-end QA, then expand QA against
the repaired browser GUI. The primary user path is a fresh install with local
music and no Tidal account session.

## Scope

1. Fresh users can configure a local music directory before logging in to
   Tidal.
2. Tidal remains visible as an optional capability for catalog search,
   streaming, and downloads.
3. A user with no Tidal session is not told that a session expired.
4. Coverless local files do not create failed artwork requests.
5. Tidal catalog search renders an authentication-required state for a 401,
   rather than an empty-result state.
6. The browser does not request an absent favicon.
7. Selecting a local track starts loading and playback even when the audio
   element uses `preload="none"`.
8. Sibling artwork can be cached from filesystems that reject metadata or flag
   preservation.

## User Flow

### Fresh local user

1. User opens the GUI with no configured scan path and no Tidal session.
2. Wizard opens on `Set up your local library`.
3. User adds one or more writable music folders, then continues.
4. GUI saves scan paths, sets the first path as the download path, starts a
   scan, and opens the app.
5. Wizard copy states that Tidal can be connected later for catalog search,
   streaming, and downloads.

The user is never required to log in to reach local playback.

### Tidal-required action

1. User without a Tidal session opens Search or submits a catalog query.
2. GUI clears stale results and presents an explicit connection action.
3. Tidal device-code login starts only after the user chooses that action.
4. A genuine previously authenticated session failure may use expired-session
   language; a never-authenticated user may not.

## Implementation Boundaries

- Keep the existing FastAPI routes and vanilla JavaScript frontend.
- Reuse the existing path validation, settings update, scan, and login flows.
- Do not add a new onboarding subsystem, persistence model, or frontend
  framework.
- Do not change authenticated Tidal download or playback behavior.

## Detailed Changes

### Onboarding

Change the no-source branch of the setup renderer to show the existing folder
setup step first. Add a secondary Tidal connection action in that step or its
supporting copy. The action must describe Tidal as the source for catalog
search, streaming, and downloads.

After a local path has been saved, application access remains available without
Tidal login.

### Authentication States

Extend `/api/auth/status` with an `auth_state` value:

- `connected`: `check_login()` succeeds.
- `not_configured`: no persisted Tidal access token exists.
- `expired`: a persisted access token exists but `check_login()` fails.

The state derives from the existing persisted Tidal token fields; it does not
add storage. An absent login must use neutral connection language. Search must
handle a 401 as an authentication-required result, not as an empty list, and
must not auto-open the external Tidal page.

### Local Artwork

When a local track has no embedded artwork, its serialized data must omit its
art URL. Existing gradient/fallback renderers then handle the absent value
without issuing `/api/library/art` requests. Artwork URLs remain present for
tracks that have real artwork.

### Favicon

Declare an inline SVG data-URI favicon in the HTML document. This avoids an
additional static asset and prevents the browser from requesting an undeclared
`/favicon.ico` path.

### Local Playback and Artwork Cache Compatibility

After assigning a selected track source and its readiness listener, playback
must explicitly call `audio.load()`. This keeps `preload="none"` while ensuring
the browser issues the local range request that can produce `canplay`.

Sibling artwork caching copies image bytes only. Cache files do not need source
timestamps, permissions, flags, or other metadata, which may be unsupported on
SMB-backed libraries.

## Regression Coverage

- Fresh setup exposes local path configuration before Tidal login.
- Setup copy describes Tidal catalog search, streaming, and downloads as
  optional capabilities.
- Never-authenticated local state does not render expired-session text.
- Auth status returns `connected`, `not_configured`, and `expired` for the
  corresponding persisted-token and session outcomes.
- A coverless local track serializes without an artwork URL.
- Coverless artwork endpoint/rendering produces no failed request.
- A catalog search 401 renders connection-required UI and does not render
  `No results found`.
- Page HTML declares a favicon.
- Selecting a local track calls `audio.load()` after the readiness listener is
  installed.
- Sibling artwork still returns successfully when metadata copying is rejected.

## Validation

- Run focused Python tests for setup, GUI API, home, library, and frontend
  source behavior.
- Start the browser GUI with isolated configuration and a coverless audio test
  file.
- Verify fresh onboarding, local scan, local playback endpoint, no-auth search,
  and browser console/network logs.
- Verify individual-track and album playback against the configured real local
  library, including advancing audio time and `206 Partial Content` responses.
- Continue with a coverage matrix for authenticated Tidal, desktop Tauri, and
  Discord bot paths. Credential- or platform-dependent cases remain explicitly
  logged when unavailable.

## Non-Goals

- Redesigning the full onboarding visual language.
- Changing Tidal OAuth or download protocol behavior.
- Adding test credentials, a mock Tidal service, or Discord fixtures.
