# Mistakes

## 2026-08-15 — Treated local playback as the core hello-world

**What happened:** During Cloud Agent environment setup, the first end-to-end demo indexed a synthetic local FLAC and played it in the GUI. That path works without Tidal. Catalog search, stream, and download do not.

**Root cause:** `/api/auth/status` was `not_configured` (`token.json` has null tokens). `/api/search` returns `401 Not logged in to Tidal` in that state. The UI still indexes and searches the local library, so it looks like “search works” while Tidal actions do nothing.

**Prevention:** Before claiming the product works end to end, call `GET /api/auth/status` and require `logged_in: true`. Then exercise a Tidal catalog search and a download. Local scan/playback is only a fallback when Tidal is intentionally out of scope.

## 2026-08-15 — Treated HIGH/M4A as a successful download

**What happened:** After Tidal login, `HI_RES_LOSSLESS` downloads failed with a quality mismatch. I switched `quality_audio` to `HIGH` so an M4A file landed. The user needs FLAC.

**Root cause:** This account is Hi-Res Premium (`highestSoundQuality: HI_RES`), but every OAuth client this app can use (`playbackinfopostpaywall`) still returns `HIGH` / `MP4A`. The exact-quality gate then errors, or a HIGH setting “succeeds” as lossy M4A. Public Hi-Fi API instances (the FLAC path) were all down.

**Prevention:** Do not lower quality to make a download succeed. Check subscription + raw `audioQuality`/`codecs`. FLAC requires a lossless delivery (`LOSSLESS`/`HI_RES_LOSSLESS` + `flac`), not a completed HIGH job.

## 2026-08-15 — Treated a live Tidal login as a gray "credentials saved" chip

**What happened:** After a real login, the sidebar Tidal chip stayed gray. `/api/auth/status` returns `logged_in: true` with `auth_state: credentials_ready`. The UI treated `credentials_ready` as a saved-but-offline state before the connected/green case.

**Root cause:** The presentation helper assumed `credentials_ready` meant "token on disk, session not verified." The local-only status endpoint now uses that state for a valid unexpired token.

**Prevention:** A saved unexpired token is connected. Use the default green `.connection-dot` for `logged_in` / `credentials_ready`. Keep gray only for an explicit saved-but-unverified state, which this API no longer has.

## 2026-08-15 — Android Auto kept advertising HiFi after Tidal capped it

**What happened:** The bundled Android Auto OAuth client still claimed HiFi/Master, but `playbackinfopostpaywall` returned HIGH/AAC. Downloads and playback looked configured for FLAC and then failed or saved M4A.

**Root cause:** Tidal changed that client's piping without a matching change in our key list. We only noticed after a live login.

**Prevention:** Keep `tidaldl-py/tidal_dl/piping_baseline.json` as the expected client contract. `music-dl piping-watch` and `.github/workflows/tidal-piping-watch.yml` (Monday) fail when the gist grows new clients or the preferred Web client drops below LOSSLESS. Ship any client change with the next binary.
