## Why

The local library currently creates album cards from exact album-title tags, so harmless title variants can split one release across multiple cards while still showing the same artwork. Title or cover similarity alone cannot safely distinguish duplicate copies from extended, remastered, live, clean, or otherwise distinct editions.

## What Changes

- Assess likely duplicate local release cards with a deterministic, explainable confidence rubric.
- Reward agreement across independent evidence families while capping correlated evidence from one provenance.
- Automatically group only assessments scoring at least 85 with no hard veto, at least two qualifying provenance sources, at least three matched tracks, and at least 90% coverage of the smaller local group.
- Keep distinct editions separate and route scores from 60 through 84 to non-blocking human review.
- Recompute automatic assessments when local evidence changes while invalidating saved grouping decisions only when release-identity membership changes.
- Optionally enrich ambiguous assessments from cached TIDAL and MusicBrainz metadata without blocking offline scans or library rendering.
- Change presentation only; do not delete files, rewrite tags, or require AI, network access, or a new external dependency.

## Capabilities

### New Capabilities

- `album-release-grouping`: Evidence collection, deterministic duplicate-release assessment, safe automatic grouping, human review, canonical title selection, and optional non-blocking catalog corroboration.

### Modified Capabilities

None.

## Impact

- Extends local scan metadata and the existing SQLite library schema.
- Adds deterministic assessment logic and cached grouping decisions to local library services.
- Changes local album API responses and album-card presentation to expose grouped releases and reviewable candidates.
- Adds optional use of the existing authenticated TIDAL session and public MusicBrainz metadata; failures leave offline behavior unchanged.
- Adds no AI dependency, external package, destructive cleanup, retagging, or edition selector.
