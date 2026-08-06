## Why

TIDAL album search results already carry edition-level quality and explicit-content metadata, but the GUI search serializer discards both fields. Users must open albums one by one to identify the preferred resolution or determine whether an edition is explicit.

## What Changes

- Preserve normalized album resolution, Dolby Atmos availability, and explicit-content state in the existing search API response.
- Show visible Quality and Rating filter rows when Albums is the active search type.
- Filter the current TIDAL album result set in memory without repeating the catalog request.
- Show resolution, Atmos, and explicit badges on TIDAL album cards.
- Add focused Python and Bun regression coverage plus user-facing documentation.

## Capabilities

### New Capabilities

- `album-search-filtering`: Defines metadata, filtering, badges, counts, and accessibility for TIDAL album search results.

### Modified Capabilities

None.

## Impact

- Affected code: `tidaldl-py/tidal_dl/gui/api/search.py`, `tidaldl-py/tidal_dl/gui/static/api.js`, `tidaldl-py/tidal_dl/gui/static/views.js`, and `tidaldl-py/tidal_dl/gui/static/style.css`.
- Affected tests and documentation: focused Python API tests, Bun view-decision tests, README search guidance, and `tidaldl-py/updatelog.md`.
- Dependencies: no new runtime or build dependencies.
- Systems: browser and desktop GUI search behavior only; CLI, Discord bot, local-library search, and TIDAL request volume remain unchanged.
