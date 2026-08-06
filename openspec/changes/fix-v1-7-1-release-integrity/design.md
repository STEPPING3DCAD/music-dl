## Context

The desktop shell loads the GUI from a Python sidecar on `http://127.0.0.1:<dynamic-port>`. Tauri currently grants custom commands only to the bundled local origin, so `get_updater_state` fails with `Command get_updater_state not allowed by ACL`.

Local library rows expose `quality` and `format`, but current views classify them differently. `M4A` is a container, not a quality signal: it may contain lossy AAC or lossless ALAC. Codec is the authoritative local fact.

Library scanning currently substitutes `Unknown Artist` immediately when an embedded artist tag is absent and accepts generic embedded titles such as `Track 05`. For a structured path such as `Los Hermanos/Los Hermanos - Ya llego/Con Cristo.m4a`, that loses useful user-authored organization already present on disk.

## Goals / Non-Goals

**Goals:**

- Restore desktop command access from the trusted loopback origin with least privilege.
- Make local quality classification deterministic and codec-based everywhere.
- Keep incomplete local albums grouped by conservatively resolving metadata at scan time.
- Repair legacy rows on the next library scan without modifying source audio.

**Non-Goals:**

- Redesign updater UX, playback routing, or Tidal authentication.
- Infer metadata from remote services or fuzzy matching.
- Write repaired metadata back into audio files.
- Add provenance UI or a new metadata service.

## Decisions

### Dedicated loopback capability

Register the seven existing custom commands in the Tauri app manifest and add a separate capability for `http://127.0.0.1:*`. Grant only those commands plus event and external-link permissions required by the remote UI.

**Why not simpler?** Extending the broad default capability is fewer lines, but it would also expose scoped sidecar spawn and process restart permissions to remote content. One dedicated JSON file is the smallest safe boundary. It adds one synchronized command list; a packaging contract test detects drift.

### Codec is the local quality authority

Persist normalized codec with each scanned track. Extend the existing quality helper to accept `(quality, format, codec)` and pass the same tuple from table, player, and ranking call sites. Lossy codecs are AAC, MP3, Ogg/Vorbis, and Opus. Lossless codecs are FLAC, ALAC, and PCM. Unknown codec yields Unknown; container extension never decides quality.

**Why not simpler?** Passing `format` to the player would make the screenshot agree but would still falsely label ALAC-in-M4A as lossy. Extending the existing scanner, database row, and shared helper fixes the root without a new module.

### Resolve metadata once at the scan boundary

For title, artist, and album, choose the first meaningful value from embedded metadata and conservative path structure. A title matching `Track <number>` is not meaningful when the filename stem is meaningful. Artist may come from the first directory beneath a configured scan root only when the file has both artist and album directories. Album may come from its directory with an optional `<artist> - ` prefix removed. Ambiguous shallow paths remain Unknown.

Resolution stores display facts in the database and marks the row as processed. Source files remain untouched. Existing rows lacking the completion marker are re-read once on a subsequent scan.

**Why not simpler?** Requiring users to retag files violates the product requirement. Repeating fallback logic in each view creates the same disconnected-facts bug. One pure resolver beside the existing scanner is the smallest shared implementation.

## Risks / Trade-offs

- [Loopback port pattern is too broad] -> Restrict scheme and host exactly to `http://127.0.0.1:*`; do not grant broad process or spawn permissions.
- [Folder names are mistaken for metadata] -> Infer only from paths at least two directories below a configured root; embedded meaningful tags always win.
- [Legacy scan costs extra time] -> Re-read only rows lacking the migration completion marker; future scans use the normal fast path.
- [Codec is unavailable] -> Display Unknown instead of guessing from the container.

## Migration Plan

Add nullable codec and a metadata-resolution completion marker idempotently. Existing rows are eligible for one repair scan. New and repaired rows persist normalized codec and resolved display metadata. Rollback leaves extra columns harmless and does not touch audio files.
