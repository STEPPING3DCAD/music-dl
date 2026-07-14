# Library Integrity Design

## Problem

The SQLite library cache currently accepts incomplete and excluded rows as active library tracks. Different API surfaces then choose local copies with different rules.

Observed local evidence:

- 1,789 active rows have blank title, artist, and album fields.
- 2,951 rows point into `#recycle` directories.
- Search returns both active and recycled copies of the same recording.
- Playlist matching prefers album and path length, not actual audio quality.
- Ten active playlist `.m4a` files contain FLAC audio but are labeled Lossy because quality logic treats every M4A container as lossy.
- Metadata repair regenerates existing waveforms while a SQLite transaction remains open, causing long scans and `database is locked` failures in the download worker.

## Required Behavior

1. `#recycle`, `.Trash`, and application staging paths are not part of the active library.
2. Excluded rows are removed from SQLite without deleting or moving audio files.
3. Cached rows with blank core metadata are re-read from their known file paths.
4. Metadata-only repair preserves cached waveforms and artwork state.
5. SQLite writes remain short so playback and download workers can continue using the database.
6. Library and Search show one canonical result per recording.
7. Album views use the same canonical selection rule.
8. Tidal playlists preserve authored order and repeated entries, but each entry uses the best matching local copy.
9. Quality labels and ranking use actual codec, not filename extension alone.

## Design

### Scan Admission

Extend the existing library scanner. Do not add another scanner module.

- Reject paths containing excluded directory components before metadata work.
- Prune previously cached excluded paths during reconciliation.
- Keep files untouched.

### Metadata Reconciliation

Use existing `scanned` rows as the repair worklist. Query rows with blank core fields, unknown metadata-completeness state, or missing codec data.

- Read tags and codec outside a SQLite write transaction.
- Preserve existing waveform, high-resolution waveform, play count, and artwork fields.
- Commit each repaired row after its metadata is ready.
- Do not regenerate waveforms for an existing row.
- Store `metadata_complete` per row based on the presence of raw title, artist, and album tags before display fallbacks are applied.
- A genuinely untagged file stores display fallbacks plus `metadata_complete = 0`; it remains visibly Unknown but does not retry forever.
- A failed or unreachable row keeps null repair fields and retries on the next Sync.

### Codec Storage

Add nullable `codec` and `metadata_complete` columns to `scanned`.

`format` continues to represent the file extension/container contract. `codec` records the audio stream family reported by Mutagen, such as `fLaC` or `mp4a.40.2`.

This cannot safely reuse `format`: an M4A file can contain either FLAC or AAC, and existing code uses `format` for file/container behavior. The added complexity is two nullable facts on the existing row and one schema migration. The rejected simpler alternative would overload one field with two meanings and could not distinguish a successfully inspected untagged file from a repair that has not run.

Codec determines the lossy/lossless family. Existing sample-rate and bit-depth quality continues to order tracks within a lossless family, so 24/192 FLAC outranks 16/44 FLAC. Null codec uses the current format-based ranking until reconciliation fills it.

### Canonical Track Selection

Keep the policy in the existing `library_db` package.

Identity aliases:

- Rows are duplicates when their nonblank ISRC matches or their complete normalized title, artist, album, and exact rounded duration match.
- Exact complete metadata may therefore collapse copies with missing or conflicting ISRCs; this handles equivalent local encodes whose source tags disagree.
- Never group blank or placeholder-only rows by metadata identity.

Playlist selection considers the union of ISRC matches and exact normalized title, artist, and album matches, then prefers the candidate whose rounded duration is closest to the Tidal duration before applying canonical quality preference. This allows a lossless local copy to outrank a lossy copy carrying the Tidal ISRC.

Preference order:

1. Active, non-excluded cached row.
2. Complete core metadata.
3. Highest actual codec quality.
4. Filename without a generated `_NN` suffix.
5. Shortest path, then lexical path for deterministic ties.

Canonicalization occurs before totals, sorting, and pagination. Library pages, Search, artist and album aggregates, album tracks, and playlist local matching call the same policy. Playlist serialization does not remove repeated Tidal entries.

The existing database remains the source of rows and indexes. Canonicalization is a bounded Python pass over matching SQLite rows; no second persistence layer or materialized table is added.

An active row means `status != 'unreadable'` and no excluded path component. It does not require filesystem access or current mount availability, preserving offline cached-library browsing.

### Excluded Row Reconciliation

Excluded components are `#recycle`, `.Trash`, `.Trashes`, and `undo-staging`, compared case-insensitively as whole path components.

Before removing an excluded `scanned` row:

- Find its active canonical equivalent using the same identity policy.
- Repoint path-based favorites and play events when an equivalent exists.
- If the canonical path is already favorited, keep that favorite and remove only the excluded duplicate favorite row.
- Preserve play-event rows when no equivalent exists so listening history is not erased.
- Preserve unmatched favorite metadata by clearing its excluded path; omit pathless entries from active local playback.
- Delete only the excluded `scanned` row. Never delete or move its audio file.

## Error Handling

- Unreachable files remain cached with null repair fields and retry on the next Sync; they are not converted to blank metadata.
- Unreadable files retain `unreadable` status.
- One failed file does not abort reconciliation.
- SQLite lock errors use the existing busy timeout and short per-row transactions; no long-running media work occurs between writes and commits.
- Reconciliation reports progress through the existing scan status surface.

## Verification

Automated tests cover:

- Blank strings do not count as complete metadata, and display fallbacks do not become raw metadata.
- Excluded path components are skipped and pruned from SQLite only.
- FLAC-in-M4A ranks lossless while AAC-in-M4A ranks lossy, and hi-res FLAC outranks CD-quality FLAC.
- Metadata repair preserves existing waveform and artwork data.
- Library, Search, totals, pagination, and aggregates use deterministic canonical rows.
- Playlist matching chooses the highest-quality active local copy while preserving playlist order.
- Repeated Tidal playlist entries remain repeated after local matching.
- Favorite repointing handles an existing canonical favorite without violating unique constraints.
- Unmatched excluded favorites retain metadata with a cleared path.
- Play events repoint when a canonical copy exists and remain intact when none exists.
- Download worker database access continues during reconciliation.

Manual verification uses the local server and current library:

- Blank metadata count falls from 1,789 to zero; genuinely untagged files use explicit display fallbacks and `metadata_complete = 0`.
- No `#recycle` result appears in Library or Search.
- `I Speak Jesus` appears once in Search.
- FLAC-in-M4A playlist tracks display Lossless.
- The one verified AAC playlist track remains Lossy.
- Local playback works during and after reconciliation.

## Non-Goals

- Do not delete duplicate audio files.
- Do not alter Tidal playlists.
- Do not contact Tidal during repair.
- Do not redesign the Home dashboard in this change.
