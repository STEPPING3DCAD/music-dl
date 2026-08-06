## ADDED Requirements

### Requirement: Local results route to local playback
The system SHALL serialize a usable local path for local library, favorite, playlist, and Tidal-matched results, and SHALL route those results through the local playback endpoint.

#### Scenario: Search result matches a live local ISRC
- **WHEN** a Tidal track's ISRC resolves to a live library row
- **THEN** the result is local and includes its local path, quality, and format

#### Scenario: Favorite has a local path
- **WHEN** a favorited track references a local library file
- **THEN** selecting it uses the local playback endpoint rather than a Tidal stream identifier

#### Scenario: Local path uses either supported payload key
- **WHEN** a local track contains `local_path` or `path`
- **THEN** playback URL-encodes that path for `/api/playback/local`

#### Scenario: Original local-search regression
- **WHEN** Tidal search returns an ISRC-matched result and the user selects it
- **THEN** the response carries its `local_path`, playback requests `/api/playback/local`, and no Tidal stream URL is requested

#### Scenario: Original favorite regression
- **WHEN** a local favorite is serialized with `path` and selected
- **THEN** playback accepts the `path` payload and does not request a `null` or `undefined` stream identifier

### Requirement: Remote results remain honest
The system SHALL classify a result as remote when no usable local path exists, SHALL label its source as Tidal, and SHALL NOT claim a codec that is not known.

#### Scenario: ISRC has no live local row
- **WHEN** a Tidal track does not resolve to a live local file
- **THEN** it remains remote, its format is blank, and playback uses `/api/playback/stream/{id}`

### Requirement: Tidal status reflects observed knowledge
The system SHALL distinguish locally saved, unexpired credentials from verified playback availability and SHALL mark playback unavailable after an observed remote stream failure.

#### Scenario: Saved unexpired credentials
- **WHEN** local token data is present and unexpired but no stream has been attempted
- **THEN** the API reports `credentials_ready`, status copy says credentials are saved, and neither status surface presents a verified green connection

#### Scenario: Missing or expired credentials
- **WHEN** local token data is absent or expired
- **THEN** the existing logged-out or expired status is shown and playback availability is not claimed

#### Scenario: Remote stream fails
- **WHEN** the media element reports an error for a remote track, including a stream route returning an HTTP error
- **THEN** both Tidal status surfaces continue to say playback is unavailable after re-render and no local-track auto-skip occurs

#### Scenario: Later remote stream succeeds
- **WHEN** remote playback successfully starts after an earlier remote failure
- **THEN** Tidal status returns to neutral credential-ready copy without claiming a verified persistent connection

#### Scenario: Local playback event
- **WHEN** a local track starts or fails
- **THEN** Tidal status is unchanged

#### Scenario: Consecutive local failures
- **WHEN** multiple local tracks fail
- **THEN** the aggregate error describes local file access and does not instruct the user to check Tidal
