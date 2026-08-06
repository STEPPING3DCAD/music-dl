## ADDED Requirements

### Requirement: Initially visible album art is eager
The system SHALL request the first visible artist-album row without native lazy-load deferral and SHALL keep later artwork lazy.

#### Scenario: Artist gallery initially renders
- **WHEN** an artist gallery contains album cover URLs
- **THEN** the first six images use eager loading and subsequent images use lazy loading

#### Scenario: Artwork request fails
- **WHEN** an album image cannot load
- **THEN** the existing generated gradient fallback remains visible
