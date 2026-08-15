# Mistakes

## 2026-08-15 — Treated local playback as the core hello-world

**What happened:** During Cloud Agent environment setup, the first end-to-end demo indexed a synthetic local FLAC and played it in the GUI. That path works without Tidal. Catalog search, stream, and download do not.

**Root cause:** `/api/auth/status` was `not_configured` (`token.json` has null tokens). `/api/search` returns `401 Not logged in to Tidal` in that state. The UI still indexes and searches the local library, so it looks like “search works” while Tidal actions do nothing.

**Prevention:** Before claiming the product works end to end, call `GET /api/auth/status` and require `logged_in: true`. Then exercise a Tidal catalog search and a download. Local scan/playback is only a fallback when Tidal is intentionally out of scope.

## 2026-08-15 — Treated HIGH/M4A as a successful download

**What happened:** After Tidal login, `HI_RES_LOSSLESS` downloads failed with a quality mismatch. I switched `quality_audio` to `HIGH` so an M4A file landed. The user needs FLAC.

**Root cause:** This account is Hi-Res Premium (`highestSoundQuality: HI_RES`), but every OAuth client this app can use (`playbackinfopostpaywall`) still returns `HIGH` / `MP4A`. The exact-quality gate then errors, or a HIGH setting “succeeds” as lossy M4A. Public Hi-Fi API instances (the FLAC path) were all down.

**Prevention:** Do not lower quality to make a download succeed. Check subscription + raw `audioQuality`/`codecs`. FLAC requires a lossless delivery (`LOSSLESS`/`HI_RES_LOSSLESS` + `flac`), not a completed HIGH job.
