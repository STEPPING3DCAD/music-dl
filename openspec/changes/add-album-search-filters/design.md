## Context

`GET /api/search` uses the pinned `tidalapi` client to return up to 50 catalog results. TIDAL album objects expose `audio_quality`, `media_metadata_tags`, `audio_modes`, and `explicit`, but `_serialize_item()` currently returns only identity, artwork, artist, and track count. The browser therefore cannot identify or filter album editions by resolution or content rating.

The Search view already stores the complete response in `state.searchResults` and rerenders it through `renderUnifiedSearchResults()` and `renderSearchResults()`. Existing quality helpers classify track quality, and existing pill styles establish the visual language for compact filters.

## Goals / Non-Goals

**Goals:**

- Let users filter the current TIDAL album result set by Max, Lossless, or High resolution tier.
- Let users filter the same result set by Explicit or Clean content rating.
- Preserve All as the default for both dimensions so existing search behavior does not change.
- Identify resolution, Dolby Atmos availability, and explicit editions directly on album cards.
- Keep filter interactions local, immediate, keyboard accessible, and free of extra TIDAL requests.
- Treat missing or unrecognized metadata as unknown without failing the search.

**Non-Goals:**

- Fetch additional TIDAL pages to replace filtered-out albums.
- Open every album or track to infer exact bitrate, bit depth, or sample rate.
- Filter local-library albums, tracks, artists, or playlists.
- Add a persisted user preference, backend filter query parameters, new module, or dependency.
- Change download quality selection or guarantee that every track in an album has identical stream properties.

## Decisions

### Normalize catalog metadata in the existing search module

`search.py` will keep album metadata normalization beside `_serialize_item()`. A small in-file helper will normalize only album resolution and Atmos metadata. Existing track serialization and response behavior remain unchanged.

`HIRES_LOSSLESS` and `HIRES` media tags take precedence over the album's `audio_quality`; otherwise the recognized `audio_quality` value is used. Unrecognized or absent values serialize as an unknown resolution. Dolby Atmos serializes as a separate boolean derived from the Atmos media tag or audio mode. Explicit content preserves three states: `true`, `false`, and unknown.

Keeping Atmos separate prevents a spatial format from being mislabeled as proof of maximum bitrate or bit depth. An album carrying both Hi-Res and Atmos metadata can display both badges and matches Max; an Atmos-only album does not match Max.

### Filter the cached TIDAL album payload in the browser

Two in-memory state values will hold the selected quality and rating filters. A pure helper in `views.js` will filter only the TIDAL albums already present in `state.searchResults`; local-library results remain unchanged. Filter clicks rerender from that cached response and do not call `/api/search` again.

Max matches the normalized Hi-Res values, Lossless matches `LOSSLESS`, and High matches `HIGH`. Unknown quality matches only All. Explicit matches `true`, Clean matches `false`, and unknown rating matches only All. The helper will apply both active dimensions together.

This is the smallest complete path because the upstream API does not expose server-side quality or explicit filters. Adding query parameters would repeat the same in-process filtering after an unnecessary TIDAL request, while hydrating every album would add latency and still could not promise one exact resolution for every track.

### Reuse the visible pill pattern for album-only controls

When Albums is selected, the Search view will show two labeled rows below the existing type pills:

- Quality: All, Max, Lossless, High
- Rating: All, Explicit, Clean

Controls will be native buttons using the existing pill visual language, visible focus, and `aria-pressed`. They will remain hidden for other search types. Selections persist across searches and view rerenders for the current app session, then reset to All on reload.

The TIDAL album count will show the filtered count and original count when a filter is active. If no current albums match, the result area will explain that filters removed all matches and provide a Clear filters action. Clearing restores All for both dimensions without another request.

### Display independent metadata badges on album cards

Every TIDAL album card will show a resolution badge: MAX, LOSSLESS, HIGH, LOW, or UNKNOWN. ATMOS appears as an additional badge when advertised, and E appears only when the album is explicitly marked. Clean albums need no extra badge. Unknown rating remains visually unmarked but does not pass Explicit or Clean filters.

Badges are derived only from the serialized search payload. No card-level request or speculative quality inference is added.

## Risks / Trade-offs

- [TIDAL omits or changes album metadata] → Serialize unknown values, keep them under All, and never fail the surrounding search.
- [A matching result exists beyond the first page] → State clearly that filters refine the current result set; do not add pagination traffic in this change.
- [Tracks within one album differ] → Present badges as TIDAL album-edition metadata, not measured per-track file properties.
- [Atmos and Hi-Res coexist] → Serialize and display the two dimensions independently so Max filtering remains accurate.
- [Filter controls crowd narrow layouts] → Reuse the existing wrapping pill layout and cover the narrow breakpoint in static UI checks.

## Verification

- Python tests cover normalized album serialization for Hi-Res plus Atmos, Lossless, explicit false, explicit unknown, and missing quality.
- Bun tests cover each single filter, combined filters, unknown exclusion, current-session state, filtered counts, clear behavior, and absence of extra API calls.
- Static checks cover native button semantics, `aria-pressed`, album-only visibility, and required badges.
- Existing relevant Python, Bun, Rust, packaging, documentation, OpenSpec, and release-version checks pass before binaries are built.

## Migration Plan

1. Ship as an additive GUI search feature with both filters defaulted to All.
2. No config, database, or persisted browser-state migration runs.
3. Roll back the GUI/API changes together if catalog metadata proves unreliable; stored user data is unaffected.

## Open Questions

None.
