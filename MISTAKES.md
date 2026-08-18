# Mistakes

## 2026-08-18 — Fingerprint sweep write skipped `write_transaction` after rebase onto 135

**What happened:** Rebasing scan-safety onto `717ec5a` applied the fingerprint fast-path sweep as `set_meta` + `commit`. That commit predates PR 135’s writer helper.

**Root cause:** The follow-up commit only added the DB-only recycle drop. It did not go through the new `write_transaction` contract that 135 added for every short library persist.

**Prevention:** After rebasing scanner work onto the lock-contention helper, wrap remaining `set_meta` / `record` / `remove` persists in `write_transaction`. Keep mark-and-sweep (no start-of-scan deletes) and 135’s short writer bursts together.

## 2026-08-17 — Sync Library deleted cache rows before the walk finished

**What happened:** On a clean copy of the real Mac library DB (schema v9, 11,974 rows), Sync Library stayed on `Scanning...` for 90s with `/api/library/scan/status` stuck at `{"scanning":true,"scanned":0,"total":0,"done":false}`. The isolated cache shrank to 8,554 rows before the process exited. Stale `#recycle` tracks stayed visible because the walk never completed.

**Root cause:** `_background_scan` backed up the DB, then called `drop_skipped_scan_paths()` and committed deletes before reconcile/walk finished. Status was only reset after that pre-walk work, so a Synology-backed reconcile or a locked backup looked like a 0/0 black hole. Writer transactions also stayed open across mutagen/ffmpeg reads (commit every 50 records), and full-library `_album_cards(include_artwork=True)` ran on the scan thread. A matching scan fingerprint also skipped the walk entirely, so stale `#recycle` rows could survive a later Sync.

**Prevention:** Never delete or age `scanned` rows at scan start. Mark-and-sweep skipped/stale paths only after a successful traversal, including the unchanged-fingerprint fast path (DB-only drop, no walk). An interrupted or failed scan must preserve the previous good cache. Do not read or repair rows under skipped directories. Expose a named `phase` immediately and increment `scanned` during discovery even when `total` is unknown. Stage metadata outside a writer transaction; commit short batches only. Keep the skipped-directory list centralized in `library_scanner.py`. Do not hold the scan busy state on full-library album grouping.

## 2026-08-17 — Recently Added stayed blank while a cover-art subquery scanned the library

**What happened:** Recently Added showed only the search shell and filter pills for ~3s. Warmed `/library/recent-albums` was 2.998s / 3.007s on the 11,974-row Mac library after PR 133 cut grouping from 25–53s to ~2.5–3s.

**Root cause:** The remaining cost was not page grouping. `recent_albums_page` `GROUP BY album`'d the whole library with a correlated cover-art subquery that `SCAN`ned the path PK once per album (~500–800ms on a local 12k/1.5k fixture; ~3s on NAS-backed SQLite). The endpoint then discarded that cover data and used `_album_cards`. The route also awaited the API before painting any results copy, so the wait was a blank shell.

**Prevention:** Page recency without per-album cover-art subqueries. Group only the current page titles plus already-stamped release members. Do not call `tracks_for_artist` for every page artist. Paint a Home-style `home-loading-hint` before the fetch. Lock the warmed 12-item page to the same <250ms budget as artist/release.

## 2026-08-17 — Library grouping held the SQLite writer lock until the download worker died

**What happened:** The Mac release-candidate gate saw repeated `sqlite3.OperationalError: database is locked` for minutes. A source-profile worker died at `BEGIN IMMEDIATE` while library API / scan writes were in flight. Port 8878 looked like a long scan; it was lock contention. Live v1.7.5 was left untouched.

**Root cause:** `_album_cards` called `save_grouping_assessment` inside the candidate loop. The first INSERT opened an implicit write transaction. Later `assess_pair` CPU, artwork reads, more inserts, `clear_release_ids`, and `stamp_release_ids` all ran before `commit()`. Scan/index paths did the same: `db.record()` then metadata/waveform/genre I/O before the next commit. API, scanner, enrichment, and `DownloadJobService` each open their own `LibraryDB` connection. WAL readers are fine; one reserved writer blocks every other `BEGIN IMMEDIATE`. The worker’s claim is uncaught, so a 5-second busy timeout killed the thread instead of retrying.

**Prevention:** Compute grouping, filesystem/network I/O, metadata reads, and callbacks first. Persist in one short `write_transaction`. Never hold a SQLite writer lock across that work. Multiple `LibraryDB` connections serialize writes at that helper (`BEGIN IMMEDIATE` + per-db lock). Retry a transient lock *outside* the process lock with a short acquire busy timeout — do not sit in `PRAGMA busy_timeout=5000` while holding that lock. The download worker must catch a remaining lock error and keep running to a terminal job state.

## 2026-08-17 — Post-download `rglob` walked Synology `#recycle` and stalled the worker

**What happened:** After a track finished, Downloads History showed Done while Active stayed on "Waiting to start...". The worker was busy. On a Synology library, `scan_new_downloads` used `Path.rglob("*")` on the configured download root, so it recursively entered `#recycle` and other trash trees. Large deleted folders kept the next jobs queued and pegged the worker.

**Root cause:** Local library indexing already skipped trash-like directory names through `is_skipped_scan_dir` / `os.walk` pruning. The post-download indexer did not. It also marked the job `done` and wrote History before that walk finished, so the UI looked idle while the worker was still scanning.

**Prevention:** Index the completed file path(s) directly. If a walk is required, reuse the centralized skip helpers and prune those directories. Keep the job in an `indexing` status (and show that status) until post-processing finishes, then mark `done`.

## 2026-08-17 — Full-library album grouping on a single-artist/release read

**What happened:** Artist page and release detail took 25–53s each on a 12k-row library. SQLite itself was instant. A bad release id 404'd in ~50s.

**Root cause:** `artist_albums`, `artist_album_tracks`, and `release_tracks` called `_album_cards(db)`, which is not just “group everything.” On the live Mac it ran `build_local_album_groups(db.all_tracks())` on 11,844 rows, then `find_candidates` = `combinations(1565 albums, 2)` = 1,223,830 pairs, then `assess_pair` plus SQLite writes. In-flight CPU was 98% in `normalize_text()` (`unicodedata.combining`). After the release-tracks GET, `renderLocalAlbumDetail` re-fetched artist albums only for cover. Artist/album “loading” used `skeleton-row`, which has no CSS, so the wait was a blank page. “1 albums” was both the Home hero tile and the gallery count.

**Prevention:** Group only the rows for that artist, the current recent-albums page, or a stamped release id. Do not call full-library grouping on those reads. After v9 migrate, `release_id` is NULL; a stamp miss for a real hash must recover with one full `_album_cards(db)` that writes every stamp, then return the card. A miss on a complete index 404s without walking. Skip the artist-albums cover fetch when the release payload already has `cover_url`. Use a visible Home-style loading hint, not an unstyled `skeleton-row`. Singularize both the hero tile and the gallery count.

## 2026-08-16 — Local scan indexed Synology `#recycle` as an artist

**What happened:** Artists view showed a `#recycle` heading with deleted NAS files (WAV titles like `08 Menu Groove Edit`) as if they were a real library artist.

**Root cause:** The local folder walk used `rglob("*")` with no directory-name skip. Recycle and system dirs (`#recycle`, `@eaDir`, `$RECYCLE.BIN`, `.Trash`, `lost+found`, …) were treated as music. When tags were missing, the first relative path part became the artist, so `#recycle` appeared as an artist. Duplicate scoring already penalized `#recycle` paths; the indexer did not skip them.

**Prevention:** Skip those directory names at the walk (whole component, case-insensitive). Do not match the word recycle in a track title. Drop already-indexed rows whose path contains a skipped dir so a rescan does not keep them. Hidden-dot albums stay indexed unless the name is an explicit skip.

## 2026-08-15 — Progress SSE skipped the queue counts that clear the waiting card

**What happened:** Claiming a queued job emits `progress` (and that payload already includes `queued_count`). The Active list only re-snapshotted on non-`progress` events, so the “Waiting to start…” summary stayed beside the now-running track until a later terminal or queue event.

**Root cause:** The client treated `progress` as a per-card paint and ignored the queue envelope. Separately, Cancel All marked `running`/`retrying` rows cancelled, but `_update_job` / `_mark_retrying` wrote those statuses back and broadcast `progress`, which redrew the job in Active.

**Prevention:** Apply `queued_count` / `active_count` / `paused` from progress payloads. Do not write an active job status, or emit downloading/retrying progress, after cancel has been requested or the row is already `cancelled`. If `_update_job` refuses `retrying`, `_mark_retrying` must mark cancelled and the retry loop must return — do not sleep and continue.

## 2026-08-15 — Exact quality match rejected valid Blue Lossless

**What happened:** Settings default to `HI_RES_LOSSLESS`. Tracks that Tidal only publishes as Blue Lossless failed the download gate, sat on "Waiting to start...", and could not be requeued. The Downloads badge also stayed at 1 after Clear Done / Clear All.

**Root cause:** `_require_exact_quality` required the delivered tier to equal the setting. Tidal already returns the best available stream at or below the request, so LOSSLESS FLAC was treated as a mismatch. The nav badge was a local increment/decrement that double-counted `batch_queued` and never synced from queue state, so Clear History could not hide it.

**Prevention:** Treat lossless settings as a family + ceiling. Accept FLAC `LOSSLESS`/`HI_RES`/`HI_RES_LOSSLESS` when lossless was requested; still reject AAC/HIGH. The Downloads Active list and badge are projections of `/downloads/active/snapshot` and `/downloads/queue-state`. Do not accumulate SSE cards; `batch_queued.count` is remaining queued jobs, not the last enqueue size.

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
