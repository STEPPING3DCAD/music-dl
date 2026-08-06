## Why

The v1.7.0 desktop app can route known local tracks through Tidal, mislabel saved credentials as a verified connection, misread server playback timestamps, defer visible artwork, and leave the packaged macOS sidecar running after quit. These defects block trustworthy playback and safe release of a hotfix.

## What Changes

- Route a track through local playback whenever its serialized payload contains a usable local path, including search and favorite results.
- Preserve actual local quality and format metadata while marking true cloud results as Tidal without inventing a codec.
- Present stored Tidal credentials as credential readiness, and mark playback unavailable after an observed remote stream failure.
- Normalize server `played_at` seconds to browser milliseconds before merging recent history.
- Load the first visible artist-album row eagerly while leaving later artwork lazy.
- Terminate packaged Unix sidecar descendants on quit, restart, failed launch, and updater installation.
- Isolate every pytest from the user's real configuration and music folders before running the full suite.

## Capabilities

### New Capabilities

- `source-aware-playback`: Local and Tidal results expose honest source metadata and route playback through the correct endpoint.
- `recent-history-time`: Recent-play timestamps use one browser-side unit for sorting, grouping, filtering, and clearing.
- `visible-artwork-loading`: Artwork visible on initial render is requested without lazy-load deferral.
- `desktop-sidecar-lifecycle`: An app-owned sidecar process tree is removed at all desktop lifecycle shutdown points.
- `test-config-isolation`: Automated tests cannot read or scan the user's configured library.

### Modified Capabilities

None. This repository has no archived capability specs yet.

## Impact

The change touches existing FastAPI serializers, browser player/view logic and tests, Tauri sidecar cleanup, updater cleanup, pytest fixtures, and release documentation. It adds no dependency, API endpoint, database migration, background network probe, or new module.
