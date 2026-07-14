# Library Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair stale local metadata, remove excluded cache rows, classify actual codecs, and make every library read choose one deterministic best local copy.

**Status:** Implemented in commit `8d4e103` and verified locally with the full
Python and Bun suites. The unchecked steps below are preserved as the original
execution plan, not as current outstanding work.

**Architecture:** Extend the existing `LibraryDB` row schema and scanner. Store raw inspection facts on each row, reconcile stale rows without waveform work, and centralize canonical identity/preference helpers in the existing `library_db` package. Keep SQLite authoritative and keep playlist ordering intact.

**Tech Stack:** Python 3.12+, SQLite/WAL, Mutagen, FastAPI, pytest, Bun tests, vanilla JavaScript.

---

### Task 1: Persist Codec and Metadata Completeness

**Files:**
- Modify: `tidaldl-py/tidal_dl/helper/library_db/core.py`
- Modify: `tidaldl-py/tidal_dl/helper/library_db/scanned.py`
- Modify: `tidaldl-py/tidal_dl/gui/api/library.py`
- Modify: `tidaldl-py/tidal_dl/download/registry.py`
- Test: `tidaldl-py/tests/test_library_db.py`
- Test: `tidaldl-py/tests/test_api_endpoints.py`
- Create: `tidaldl-py/tests/test_download_registry.py`

- [ ] Add failing migration test requiring nullable `codec` and `metadata_complete` columns on legacy databases.
- [ ] Add failing `_read_metadata()` tests for FLAC-in-M4A, AAC-in-M4A, and missing raw tags.
- [ ] Run targeted tests and confirm failures describe missing columns/facts.
- [ ] Bump schema version and add both columns through existing migration code.
- [ ] Extend `record()` with optional `codec` and `metadata_complete`; preserve existing values when omitted.
- [ ] Return display fallbacks separately from raw-tag completeness in `_read_metadata()`.
- [ ] Derive codec from Mutagen `audio.info.codec` or codec description; use stable lowercase family values.
- [ ] Persist both facts through direct post-download registration, not only later scans.
- [ ] Serialize codec on local track API payloads.
- [ ] Run targeted tests until green.

### Task 2: Define Canonical Identity and Quality

**Files:**
- Modify: `tidaldl-py/tidal_dl/helper/library_db/utils.py`
- Modify: `tidaldl-py/tidal_dl/helper/library_db/_common.py`
- Test: `tidaldl-py/tests/test_library_db.py`

- [ ] Add failing tests for excluded path components, ISRC identity, metadata fallback identity, placeholder isolation, codec-aware quality, suffix preference, and deterministic ties.
- [ ] Run tests and confirm red state.
- [ ] Add `_is_excluded_library_path(row_or_path)` using whole components: `#recycle`, `.Trash`, `.Trashes`, `undo-staging`.
- [ ] Add deterministic ISRC and complete-metadata aliases; canonicalization collapses rows when either alias matches and keeps incomplete rows unique by path.
- [ ] Update quality rank to use codec family first and existing sample-rate/bit-depth rank second; retain current format fallback for null codec.
- [ ] Add one canonical preference tuple and one canonicalize helper.
- [ ] Run targeted tests until green.

### Task 3: Canonicalize Library Reads Before Pagination

**Files:**
- Modify: `tidaldl-py/tidal_dl/helper/library_db/scanned.py`
- Modify: `tidaldl-py/tidal_dl/helper/library_db/browse.py`
- Modify: `tidaldl-py/tidal_dl/gui/api/library.py`
- Test: `tidaldl-py/tests/test_library_db.py`
- Test: `tidaldl-py/tests/test_api_endpoints.py`

- [ ] Add failing tests proving duplicate copies count once, totals match canonical rows, page boundaries contain no repeats, and artist/album counts ignore excluded/duplicate rows.
- [ ] Run tests and confirm current raw SQL counts fail.
- [ ] Make `tracks_page()` load matching active rows, canonicalize, sort with existing sort semantics, then count and slice.
- [ ] Reuse canonical rows in artists, albums, recent albums, artist albums, and album tracks without adding a second cache.
- [ ] Route the local artist-search branch through canonical aggregate methods instead of its raw SQL query.
- [ ] Keep random sorting and offline cached rows working.
- [ ] Run targeted DB and endpoint tests until green.

### Task 4: Choose Best Local Playlist Copy

**Files:**
- Modify: `tidaldl-py/tidal_dl/gui/api/playlists.py`
- Test: `tidaldl-py/tests/test_gui_playlist_local_preference.py`

- [ ] Add failing tests for higher-quality preference, recycle exclusion, closest-duration fallback, and repeated Tidal entries remaining repeated.
- [ ] Run tests and confirm current path-length ranking fails.
- [ ] Replace playlist-specific sort with shared canonical preference.
- [ ] Combine ISRC and normalized title/artist/album matches, rank duration distance, then canonical quality.
- [ ] Copy the selected local row's codec into the serialized playlist track.
- [ ] Preserve serialized Tidal order and repetitions.
- [ ] Run playlist tests until green.

### Task 5: Reconcile Excluded and Incomplete Rows Safely

**Files:**
- Modify: `tidaldl-py/tidal_dl/helper/library_db/scanned.py`
- Modify: `tidaldl-py/tidal_dl/gui/api/library.py`
- Modify: `tidaldl-py/tidal_dl/gui/services/download_job_service.py`
- Test: `tidaldl-py/tests/test_api_endpoints.py`
- Test: `tidaldl-py/tests/test_download_jobs_service.py`
- Test: `tidaldl-py/tests/test_library_db.py`

- [ ] Add failing tests for metadata-only repair preserving waveforms/art/play counts, per-row commits, excluded-row pruning, favorite merge collisions, unmatched favorite path clearing, play-event repointing, and unmatched history preservation.
- [ ] Add concurrency regression proving another DB connection can claim a job while reconciliation performs slow file reads.
- [ ] Run targeted tests and confirm failures.
- [ ] Add DB worklist/reconciliation methods in existing mixins.
- [ ] Run metadata reconciliation before the directory-fingerprint fast-path; add a matching-fingerprint regression test with one pending repair row.
- [ ] Inspect file metadata before starting each write; record and commit immediately afterward.
- [ ] Never run waveform extraction for an existing row.
- [ ] Apply excluded-path admission to both library scan and post-download scan.
- [ ] Persist codec and metadata completeness in `scan_new_downloads()` as well as excluded-path admission.
- [ ] Repoint/merge related rows before deleting only the excluded `scanned` row.
- [ ] Keep failed rows eligible for next Sync.
- [ ] Run targeted tests until green.

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `tidaldl-py/README.md`
- Modify: `tidaldl-py/tidal_dl/gui/static/api.js`
- Modify: `tidaldl-py/tidal_dl/gui/static/views.js`
- Modify: `tidaldl-py/tidal_dl/gui/static/player.js`
- Modify: `tidaldl-py/tests/views-decisions.test.js`
- Modify: `tidaldl-py/tests/player-decisions.test.js`

- [ ] Document codec-aware quality labels, canonical search results, excluded recycle folders, and metadata repair behavior.
- [ ] Add failing Bun tests proving FLAC-in-M4A displays Lossless and AAC-in-M4A displays Lossy.
- [ ] Make quality label/class decisions consume serialized codec while preserving null-codec fallback.
- [ ] Pass codec through every quality label/title/class call in library, playlist, queue, and player surfaces.
- [ ] Run `bun test` from `tidaldl-py`.
- [ ] Run `PYTHONNOUSERSITE=1 uv run --extra test python -m pytest` from `tidaldl-py`.
- [ ] Restart local server on `127.0.0.1:8876`.
- [ ] Run local reconciliation with no Tidal requests.
- [ ] Verify blank core metadata rows are zero and excluded scanned rows are zero.
- [ ] Manually search `I Speak Jesus` and confirm one result.
- [ ] Manually verify FLAC-in-M4A is Lossless and verified AAC remains Lossy.
- [ ] Verify Home retains its all-time principal artist and two secondary artist cards.
- [ ] Play local tracks during/after reconciliation and inspect server logs for lock errors.
- [ ] Inspect git diff, commit implementation, push branch, and verify PR checks.
