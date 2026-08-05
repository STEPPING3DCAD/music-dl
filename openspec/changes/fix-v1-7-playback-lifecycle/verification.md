# v1.7.1 Packaged Verification

Verified on macOS arm64 on 2026-08-05 from the final v1.7.1 worktree.

## Build

- `uv sync --extra build` passed.
- `bun install --frozen-lockfile` passed without lockfile changes.
- The default `bunx tauri build --bundles app,dmg` compiled and produced the app and DMG, then returned nonzero because the local environment has the updater public key but no `TAURI_SIGNING_PRIVATE_KEY`.
- `bunx tauri build --bundles app,dmg --config '{"bundle":{"createUpdaterArtifacts":false}}'` passed with exit 0.
- App: `tidaldl-py/src-tauri/target/release/bundle/macos/music-dl.app`
- DMG: `tidaldl-py/src-tauri/target/release/bundle/dmg/music-dl_1.7.1_aarch64.dmg`
- The app and DMG were rebuilt after the final path-only preload/restore review fix; that final build also passed with exit 0.
- Final DMG SHA-256: `bdeb808c4b8f04f7cc07d04f96d61efdf29707726e55f65cd40606497be2e05a`

## Sidecar lifecycle

The app launched with an isolated temporary `MUSIC_DL_CONFIG_DIR`.

First launch:

- app PID: `30928`
- owned wrapper PID: `30954`, parent `30928`
- metadata/worker PID: `30978`, parent `30954`
- metadata version: `1.7.1`
- listening endpoint: `127.0.0.1:8765`

After a normal macOS Quit, `ps` found none of PIDs `30928`, `30954`, or `30978`, and `lsof` found no listener on port `8765`.

Relaunch:

- app PID: `36766`
- owned wrapper PID: `36785`, parent `36766`
- metadata/worker PID: `36880`, parent `36785`
- metadata version: `1.7.1`
- listening endpoint: `127.0.0.1:8765`

The relaunch used a fresh process tree. A second normal Quit removed all three new PIDs and the listener.

Post-review final rebuild smoke:

- app PID: `11666`
- owned wrapper PID: `11703`, parent `11666`
- metadata/worker PID: `11741`, parent `11703`
- metadata version: `1.7.1`
- listening endpoint: `127.0.0.1:8765`
- the packaged `/player.js` contained the shared local-path calls for direct play, gapless preload, and saved-position restore
- a normal Quit removed all three PIDs and the listener

## Packaged browser QA

The final app was launched against a temporary WAL-safe copy of the real library database and copied settings/token files. The real config and library database were not modified.

- Sidebar showed `v1.7.1` and neutral `tidal · credentials saved`, not a green connected claim.
- Search for `michael jackson` showed explicit `local` and `tidal` source labels.
- Local matches showed `FLAC`; unmatched remote tracks showed a blank Format cell.
- Playing the local Search result `They Don't Care About Us` selected `/api/playback/local?path=...` and played successfully. No `/api/playback/stream/{id}` source was selected.
- Playing the local Favorite `I Speak Jesus` selected `/api/playback/local?path=...` and played successfully. No `/api/playback/stream/{id}` source was selected.
- Browser console warning/error logs remained empty during the checked flows.

## Artwork

- A clean Moby artist-page load produced six Moby `/api/library/art` requests.
- All six Moby images had `loading="eager"`, `complete=true`, and nonzero `naturalWidth`; the captured screenshot showed all six covers rendered together.
- Moby has exactly six albums, so the later-card boundary was checked on Linkin Park's 21-album gallery: indexes `0` through `5` had `loading="eager"`; index `6` and later retained `loading="lazy"`.
- Browser-native lazy loading is a hint: the browser may prefetch nearby lazy images based on viewport distance. Acceptance therefore verifies the attribute boundary rather than promising a specific request remains absent.

## Final gates and reviews

- Python: `657 passed, 1 skipped`
- Browser JavaScript: `36 passed`
- Rust: formatting passed, `17 passed`, and `cargo check` passed
- Release metadata: all files agreed on `1.7.1`
- OpenSpec: strict validation passed
- Ponytail review removed dead `all-local` class bookkeeping.
- Code-quality review found and verified the path-only preload/restore regression fix.
- Final specification and code-quality re-reviews reported no remaining findings.
