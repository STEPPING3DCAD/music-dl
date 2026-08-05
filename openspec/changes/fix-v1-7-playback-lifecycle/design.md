## Context

Real v1.7.0 QA reproduced five independent defects in one shipped desktop flow. Search and favorite payloads disagree about whether a local path is named `path` or `local_path`; Tidal search marks an ISRC as local without returning the matching path; recent-history API timestamps are seconds while the browser uses milliseconds; all album gallery images are lazy even when initially visible; and the macOS PyInstaller wrapper has a child daemon that survives `CommandChild.kill()`. The full pytest run also reached the user's NAS because tests inherit the real config directory.

Constraints: keep the auth status endpoint free of provider keepalive calls, do not change the database schema, do not add dependencies or modules, preserve Windows `taskkill /T`, and do not terminate a Unix process group because live evidence showed it also contains the app process.

## Goals / Non-Goals

**Goals:**

- Make every local result carry a usable path and play through `/api/playback/local`.
- Keep remote results remote and identify their source without inventing a codec.
- Make Tidal status copy match what is actually known and downgrade it after a stream failure.
- Normalize server history timestamps once, before browser merge and UI calculations.
- Request initially visible artist artwork eagerly.
- Remove app-owned Unix descendants before their wrapper at every shared shutdown path.
- Make the complete automated suite safe to run on a developer machine.

**Non-Goals:**

- No background Tidal stream probe, cache redesign, artwork backfill, artist-count redesign, library mutation, process-group signaling, dependency addition, or architectural refactor.

## Decisions

### Extend existing playback contracts

`playTrack` will accept `local_path || path`, matching serializers already used elsewhere. Tidal search serialization will reuse the library DB's existing ISRC lookup to attach the selected local row's path, quality, and format. Favorite serialization will expose the same `local_path` alias. A row is local only when that usable path exists.

Alternative rejected: add a new source resolver service. The same DB lookup and serializer seams already exist; another layer adds call paths and debugging surface without a present requirement. The simplest alternative—patch only `playTrack`—was rejected because it would leave Tidal search's false-local classification and missing metadata intact.

Remote rows keep advertised Tidal quality, show `tidal` as source, and show no codec when format is unknown. The local auth endpoint will name unexpired stored-token state `credentials_ready`, not `connected`. Both status surfaces will render that state with a neutral class and honest copy. A small browser-session playback-state flag persists an observed remote media error, including an HTTP stream-route failure surfaced by the media element, across status re-renders. A later successful remote `play` event clears the flag and restores neutral credential-ready state; local media events never change it. No background request is added.

### Normalize recent timestamps at ingestion

`_syncRecentFromServer` will copy server tracks and multiply positive `played_at` values below `10_000_000_000` by 1000 before sorting or deduplication. Existing local `Date.now()` millisecond values remain unchanged.

Alternative rejected: make every date helper accept both units. One normalization at the trust boundary is fewer branches and protects sorting, grouping, filters, and deletion together.

### Use the native image loading hint

The artist gallery will set the first six album images to `loading="eager"` and retain `lazy` for the rest. Six matches the current wide first-row layout seen in QA and costs no observer or prefetch system.

Alternative rejected: pre-cache all missing library artwork. That would perform thousands of NAS reads and did not explain the already-cached Moby delay. A custom intersection observer duplicates native browser behavior.

### Kill descendants, not the Unix process group

On Unix, the existing sidecar helper will query `ps` for parent/child PID pairs, derive the owned wrapper's descendants, terminate descendants deepest-first, and finally kill the wrapper through `CommandChild`. Windows keeps `taskkill /T /F`. The updater will call this same helper.

Alternative rejected: signal the process group. The observed group included the app, so that can kill the wrong process. A new process-management crate is unnecessary for a small `ps` parser and would expand release risk.

### Isolate pytest globally

At `tests/conftest.py` import time, before importing application configuration or collecting test modules, the suite will point `MUSIC_DL_CONFIG_DIR` at a session-temporary directory. An autouse fixture will then point it at each test's temporary directory and reset configuration singletons before and after the test. Tests that require explicit config remain free to override the environment within their own scope.

Alternative rejected: patch individual lifespan tests. Any future test could reintroduce the leak; the existing global fixture boundary is the smallest reliable guard.

## Risks / Trade-offs

- [A valid local ISRC points to a missing file] -> Use the DB's live-path lookup and set `is_local` only with a usable returned path.
- [Six eager images exceed a narrow viewport's first row] -> The bounded extra requests are local cache endpoints; later cards remain lazy.
- [Unix descendant discovery races with process exit] -> Ignore already-exited descendant failures and always attempt wrapper cleanup.
- [`ps` output differs across Unix variants] -> Request only numeric `pid` and `ppid`, parse whitespace, and cover malformed lines in unit tests.
- [A test intentionally depends on real user config] -> Such a test must opt in explicitly; the default suite remains non-destructive.

## Migration Plan

Ship as v1.7.1 with no data migration. Verify focused Python/Bun/Rust tests, then the isolated full pytest suite, then a packaged macOS quit/relaunch smoke. Rollback is the v1.7.0 binary; no persisted data changes require reversal.

## Open Questions

None for this hotfix. The artist total wording and broader artwork cache maintenance remain separate work.
