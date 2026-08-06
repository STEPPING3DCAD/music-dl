## ADDED Requirements

### Requirement: Album search metadata
The TIDAL search API SHALL serialize normalized resolution, Dolby Atmos availability, and explicit-content state for album results without performing a per-album follow-up request.

#### Scenario: Hi-Res Atmos explicit album
- **WHEN** a TIDAL album search item advertises Hi-Res Lossless, Dolby Atmos, and explicit content
- **THEN** the serialized album identifies Max resolution, Atmos availability, and explicit content independently

#### Scenario: Clean Lossless album
- **WHEN** a TIDAL album search item advertises Lossless quality and an explicit value of false
- **THEN** the serialized album identifies Lossless resolution and Clean content

#### Scenario: Album metadata is missing
- **WHEN** a TIDAL album search item omits or provides unrecognized resolution or explicit metadata
- **THEN** the search succeeds and serializes each unavailable dimension as unknown

### Requirement: Album-only filter controls
The Search view SHALL show accessible Quality and Rating filter controls only while Albums is the active search type.

#### Scenario: Albums is selected
- **WHEN** the user selects Albums search
- **THEN** visible native-button controls offer Quality values All, Max, Lossless, and High plus Rating values All, Explicit, and Clean

#### Scenario: Another search type is selected
- **WHEN** Tracks, Artists, or Playlists is active
- **THEN** the album Quality and Rating controls are not shown

#### Scenario: Filter button is selected with a keyboard
- **WHEN** a keyboard user activates an album filter button
- **THEN** the control updates its visible selected state and `aria-pressed` state

### Requirement: In-memory TIDAL album filtering
Album filters SHALL refine only the current cached TIDAL album result set and SHALL NOT issue another catalog request.

#### Scenario: Quality filter is applied
- **WHEN** the user selects Max, Lossless, or High
- **THEN** only TIDAL albums whose normalized resolution matches that tier remain visible

#### Scenario: Rating filter is applied
- **WHEN** the user selects Explicit or Clean
- **THEN** only TIDAL albums with the corresponding known explicit-content state remain visible

#### Scenario: Both filters are active
- **WHEN** the user selects both a non-All Quality filter and a non-All Rating filter
- **THEN** only TIDAL albums matching both selections remain visible

#### Scenario: Metadata is unknown
- **WHEN** an album has unknown resolution or rating metadata
- **THEN** it appears only while the corresponding filter is All

#### Scenario: Local-library albums are present
- **WHEN** unified search also contains local-library album results
- **THEN** changing TIDAL album filters does not hide or relabel the local-library albums

### Requirement: Album metadata badges
Every TIDAL album card SHALL identify its normalized resolution and SHALL independently identify Atmos and explicit availability when present.

#### Scenario: Album offers Hi-Res and Atmos
- **WHEN** an album advertises both Hi-Res resolution and Dolby Atmos
- **THEN** its card shows MAX and ATMOS badges and the album matches the Max filter

#### Scenario: Album offers Atmos without known Hi-Res
- **WHEN** an album advertises Atmos but no recognized Hi-Res resolution
- **THEN** its card shows ATMOS and UNKNOWN badges and the album does not match the Max filter

#### Scenario: Album is explicit
- **WHEN** an album's explicit state is true
- **THEN** its card shows an E badge

#### Scenario: Album is clean or unknown
- **WHEN** an album's explicit state is false or unknown
- **THEN** its card does not show an E badge

### Requirement: Filter state, counts, and empty results
Album filters SHALL default to All, persist for the current app session, report their effect on the current result count, and be clearable without another catalog request.

#### Scenario: Search starts with default filters
- **WHEN** the app loads without prior in-memory filter state
- **THEN** Quality and Rating both select All and the existing unfiltered album search behavior is preserved

#### Scenario: Filter remains active during the session
- **WHEN** the user changes searches or navigates away and back without reloading the app
- **THEN** the selected album filters remain active

#### Scenario: A filter reduces results
- **WHEN** active filters retain 12 albums from a 50-album TIDAL response
- **THEN** the TIDAL album section reports 12 of 50 albums

#### Scenario: No albums match
- **WHEN** active filters remove every TIDAL album result
- **THEN** the view explains that no albums match the filters and offers a Clear filters action

#### Scenario: User clears filters
- **WHEN** the user activates Clear filters
- **THEN** both filters return to All and the cached unfiltered TIDAL album results reappear without another catalog request
