## ADDED Requirements

### Requirement: Codec determines local audio quality
The application SHALL classify a local track from its detected codec, independent of its container extension.

#### Scenario: M4A contains AAC
- **WHEN** a local M4A file has detected codec AAC
- **THEN** every local track view labels it Lossy

#### Scenario: M4A contains ALAC
- **WHEN** a local M4A file has detected codec ALAC
- **THEN** every local track view labels it Lossless

#### Scenario: Codec is unknown
- **WHEN** no recognized codec is available
- **THEN** every local track view labels quality Unknown rather than guessing from format or bit depth

### Requirement: Local quality views share persisted facts
The library scanner SHALL persist normalized codec and the API SHALL return it with local track data so table, player, and ranking logic use the same `(quality, format, codec)` tuple.

#### Scenario: Same local track appears in multiple views
- **WHEN** a local track is rendered in the library table and Now Playing
- **THEN** both views derive the same quality tier from the same persisted fields
