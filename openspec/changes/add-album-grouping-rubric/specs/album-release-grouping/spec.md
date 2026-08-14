## ADDED Requirements

### Requirement: Rich release metadata collection
The system SHALL retain nullable album artist, release date, track number, embedded track total, disc number, embedded disc total, MusicBrainz release identifiers, provider album identity, and barcode metadata when those values are available during the existing scan.

#### Scenario: Existing tags contain release metadata
- **WHEN** a scanned audio file exposes supported release metadata
- **THEN** the system stores those values with the existing scanned-track record without requiring another scan service

#### Scenario: Release metadata is unavailable
- **WHEN** a scanned audio file lacks one or more supported release fields
- **THEN** the system stores those fields as unavailable and keeps the file usable in the library

### Requirement: Safe duplicate-release candidate discovery
The system SHALL preserve exact-title Local Album Groups and SHALL create a Duplicate Release Candidate only for an identical authoritative release identity, equal non-empty normalized album artist plus compatible full/base title, or equal album artist plus exact ISRC overlap of at least `min(2, smaller Recording Slot count)` and at least 50 percent of the smaller group.

#### Scenario: Parenthetical title difference creates a candidate
- **WHEN** two Local Album Groups share a normalized album artist and compatible base title but differ by a parenthetical title such as `(En Vivo)`
- **THEN** the system assesses them as a candidate without grouping them from title similarity alone

#### Scenario: Different edition titles are considered
- **WHEN** standard and extended edition titles normalize to a compatible base title
- **THEN** the system retains their original titles and edition markers for contradiction checks

#### Scenario: Recording overlap is too weak
- **WHEN** same-artist Local Album Groups have incompatible titles and ISRC overlap below either candidate threshold
- **THEN** the system does not create a candidate from that overlap

### Requirement: Provenance-aware confidence rubric
The system SHALL produce a deterministic Grouping Assessment using the specified integer point table, one-to-one recording matching, capped score families, qualifying provenance sources, hard vetoes, and final 0-to-100 clamping.

| Score family | Points | Cap |
|---|---:|---:|
| Authoritative release identity | MusicBrainz Release ID 100; same provider namespace and album ID 95; barcode/UPC 80; MusicBrainz Release Group ID 20 | 100 |
| Recording agreement | `floor(40 * ISRC matches / N)` plus `floor(25 * fallback matches / N)` | 55 |
| Release metadata | normalized album artist 6; compatible title 5; compatible date/year 4; equal embedded track total 6; equal embedded disc total 4 | 25 |
| Catalog corroboration | same TIDAL release 10; same MusicBrainz release 10, without repeating authoritative identity | 20 |
| Weak presentation evidence | intersecting artwork digest sets 3; intersecting normalized parent-directory sets 2 | 5 |
| Source diversity | 5 per qualifying provenance source after the first | 15 |

#### Scenario: Correlated metadata is capped
- **WHEN** many matching fields belong to one score family
- **THEN** their combined contribution does not exceed that score-family cap and their shared provenance counts once

#### Scenario: Independent sources agree
- **WHEN** positive non-weak evidence agrees across additional provenance sources
- **THEN** the system adds five points per qualifying source after the first up to 15 points

#### Scenario: Weak source does not qualify
- **WHEN** filesystem artwork or path similarity is the only additional provenance
- **THEN** it may contribute at most five weak points but does not satisfy source diversity or earn a diversity bonus

#### Scenario: Recording matches are calculated
- **WHEN** two candidate summaries are scored
- **THEN** equal single valid ISRCs from unambiguous Recording Slots match first and remaining slots match one-to-one only on normalized artist/title, equal non-null track position, compatible disc position, and duration within five seconds

#### Scenario: Physical copies disagree on ISRC
- **WHEN** compatible rows in one Recording Slot carry more than one valid ISRC
- **THEN** the slot earns no ISRC points, its identifiers cannot create a veto, and it remains eligible for fallback and catalog evidence

#### Scenario: Recording points are calculated
- **WHEN** the smaller group has `N` distinct recordings
- **THEN** ISRC points equal `floor(40 * ISRC matches / N)`, fallback points equal `floor(25 * fallback matches / N)`, and their sum is capped at 55

#### Scenario: Fallback provenance is assigned
- **WHEN** a fallback match uses local artist/title/position tags and decoded duration
- **THEN** its one recording contribution cites both `local_tags` and `decoded_audio` as provenance sources

#### Scenario: Assessment explanation is requested
- **WHEN** the client loads a Grouping Assessment
- **THEN** the response identifies every contribution, score family, provenance sources, family subtotal, diversity bonus, veto, final score, and outcome

#### Scenario: One catalog corroborates the pair
- **WHEN** both Local Album Groups resolve to one source release by direct source ID or by matching source album artist plus at least `min(3, local slot count)` slots covering 90 percent of each local group
- **THEN** that catalog contributes 10 points without duplicating authoritative identity points

### Requirement: Conservative automatic grouping
The system SHALL automatically group a Duplicate Release Candidate only when its score is at least 85, it has no hard veto, at least two qualifying provenance sources agree, at least three Recording Slots match, and matches cover at least 90 percent of the smaller group's slots.

#### Scenario: High-confidence partial copy
- **WHEN** a four-slot Local Album Group matches four slots in a 30-slot group, both report the same 30-track Release, at least two qualifying provenance sources agree, and the score is at least 85
- **THEN** the system presents them as one Release card containing 30 distinct recordings

#### Scenario: Direct authoritative identity
- **WHEN** two Local Album Groups have the same MusicBrainz Release ID or the same provider namespace and album ID and no veto applies
- **THEN** the direct identity bypasses the source-diversity, three-match, and 90-percent coverage gates

#### Scenario: Cover is the only agreement
- **WHEN** two Local Album Groups share artwork but lack enough corroborating evidence
- **THEN** the system keeps them separate

#### Scenario: Threshold boundaries
- **WHEN** candidates without vetoes score 59, 60, 84, and 85 while the 85-point candidate passes every auto gate
- **THEN** their rubric outcomes are respectively separate, review, review, and auto-group

#### Scenario: High score misses an auto gate
- **WHEN** a candidate scores at least 85 without direct identity but lacks source diversity, three matches, or 90-percent coverage
- **THEN** the system routes it to review instead of automatically grouping it

### Requirement: Distinct edition protection
The system MUST keep distinct Releases separate when authoritative or independently corroborated evidence establishes incompatible release identities, disc or track totals, positioned recordings, or edition-specific content.

#### Scenario: Extended edition has additional tracks
- **WHEN** one candidate is confirmed as a 30-track Release and the other as a 36-track extended Release
- **THEN** a hard veto prevents automatic or rubric-based grouping

#### Scenario: Same title refers to different recordings
- **WHEN** the same disc and track position maps to independently verified different recordings
- **THEN** a hard veto prevents automatic grouping

#### Scenario: Edition marker lacks corroboration
- **WHEN** titles differ by an edition marker but release totals and recording sets do not establish different Releases
- **THEN** the marker alone is neither a hard veto nor proof of identity

#### Scenario: One local contradiction is unconfirmed
- **WHEN** an incompatible release-level value does not repeat on at least three distinct Recording Slots, or every slot in a smaller group, and lacks authoritative catalog confirmation
- **THEN** the contradiction routes to review instead of becoming a hard veto

#### Scenario: Both release totals are confirmed
- **WHEN** incompatible totals repeat on at least three distinct Recording Slots per group, or every slot in a group smaller than three, or are directly confirmed by authoritative catalogs
- **THEN** the contradiction becomes a hard veto

### Requirement: Partial-library tolerance
The system SHALL distinguish observed local file count from embedded or catalog release totals and SHALL calculate recording coverage against Recording Slots in the smaller Local Album Group.

#### Scenario: Local group contains only part of a release
- **WHEN** a Local Album Group contains four distinct recordings but its trusted metadata reports a 30-track Release
- **THEN** the system does not treat four versus 30 observed files as a release-total contradiction

#### Scenario: Duplicate physical files exist
- **WHEN** a Local Album Group contains multiple files representing the same recording
- **THEN** those copies count once in recording coverage and presented track count

### Requirement: Human review for ambiguous candidates
The system SHALL keep review outcomes as separate cards, mark them as possible duplicates, and provide non-blocking side-by-side review with canonical-title choice, `Group together`, and `Keep separate` actions.

#### Scenario: Ambiguous assessment appears in library
- **WHEN** a candidate scores between 60 and 84 without a hard veto
- **THEN** both cards remain visible with a subtle possible-duplicate indicator and scanning is not interrupted

#### Scenario: User groups an ambiguous candidate
- **WHEN** the user selects one current member title and `Group together`
- **THEN** the system stores the decision and selected canonical title for the current group signatures and presents one Release card

#### Scenario: User rejects an ambiguous candidate
- **WHEN** the user selects `Keep separate`
- **THEN** the system stores the decision for the current group signatures and later online evidence does not override it

### Requirement: Safe decision precedence
The system MUST apply current keep-separate decisions first, then other hard vetoes, then current group-together decisions, then the automatic rubric. Non-veto catalog evidence SHALL NOT override a current user decision, while a newly established hard veto MUST supersede unsafe grouping and explain why it was revoked.

#### Scenario: Score changes after user decision
- **WHEN** non-veto catalog evidence changes the score for current signatures with a user decision
- **THEN** the stored user decision remains effective

#### Scenario: Hard veto appears after grouping
- **WHEN** authoritative or independently corroborated evidence establishes a hard veto after `Group together`
- **THEN** the system keeps the Releases separate, marks the old choice superseded, and explains why grouping was revoked

### Requirement: Stable assessment persistence and invalidation
The system SHALL persist assessments and user decisions by versioned SHA-256 signatures over canonical JSON containing exact display album title, normalized album title and album artist, locally stored release identity metadata and totals, and sorted Recording Slot keys based on normalized artist/title, disc/track position, and deterministic duration-cluster ordinal. Exact display title SHALL distinguish exact-title groups that otherwise normalize identically. ISRC, raw duration, paths, format, quality, artwork, online responses, and duplicate physical copies SHALL be excluded from the signature payload beyond those slot keys. Changed duration evidence SHALL trigger reassessment without invalidating a current user decision when the signature remains unchanged.

#### Scenario: Application restarts without membership changes
- **WHEN** the application restarts or rescans the same represented recordings
- **THEN** the current assessment and user decision remain applicable

#### Scenario: Release-identity membership materially changes
- **WHEN** represented Recording Slots are added or removed, or a slot's normalized artist, title, disc position, or track position changes
- **THEN** the group signature changes and the system reevaluates the candidate before applying an old decision

#### Scenario: Only recording duration changes
- **WHEN** a represented recording is replaced with the same normalized artist, title, disc position, and track position but a materially different duration without adding or removing a Recording Slot
- **THEN** the system recomputes the automatic assessment while keeping the group signature and current user decision applicable

#### Scenario: File format is upgraded
- **WHEN** a represented recording changes file format or gains another physical copy without changing recording identity
- **THEN** the group signature remains stable

#### Scenario: Recording lacks ISRC
- **WHEN** a represented recording has no valid ISRC
- **THEN** its signature slot key remains normalized track artist/title, disc and track position, and deterministic duration-cluster ordinal

#### Scenario: Compatible copy introduces conflicting ISRC
- **WHEN** another physical copy joins an existing five-second Recording Slot but carries a different ISRC
- **THEN** the slot key and group signature remain stable while the slot records noisy ISRC evidence

### Requirement: Optional non-blocking catalog corroboration
The system SHALL complete local assessment and library rendering without network access and MAY enqueue a current `(candidate, source)` after scan only when the pair has no user decision or hard veto and that source has neither a direct authoritative identity nor a successful result for the current signatures.

#### Scenario: TIDAL session is already authenticated
- **WHEN** an eligible candidate needs enrichment and the existing TIDAL session is authenticated
- **THEN** the system may cache TIDAL corroboration without prompting for login

#### Scenario: MusicBrainz is queried
- **WHEN** an eligible candidate needs MusicBrainz corroboration
- **THEN** the system uses an identifying User-Agent, makes no more than one request per second, and caches the response

#### Scenario: Online source fails
- **WHEN** a catalog request times out, is rate-limited, loses authentication, or returns malformed data
- **THEN** the system records that source as unavailable and preserves the local assessment without failing scan or render

#### Scenario: Catalog sources disagree
- **WHEN** optional catalogs provide materially conflicting release evidence
- **THEN** one uncorroborated contradiction routes the candidate to review and an authoritative or independently corroborated contradiction becomes a hard veto

#### Scenario: Successful evidence is cached
- **WHEN** a catalog succeeds for current group signatures
- **THEN** the system re-scores immediately, retains that source result for those signatures, and does not periodically poll that source

#### Scenario: Failed evidence is retried
- **WHEN** one catalog fails while another succeeds
- **THEN** the failed source remains independently eligible only after a later completed scan and at least 24 hours after its failed attempt

### Requirement: Non-destructive grouped presentation
The system SHALL apply Grouping Decisions consistently to all local album-card and detail surfaces and SHALL NOT delete, move, rename, or retag audio files.

#### Scenario: Accepted groups contain duplicate formats
- **WHEN** accepted Local Album Groups contain FLAC and M4A copies of the same recordings
- **THEN** the card presents each recording once using the existing quality preference while all physical files remain untouched

#### Scenario: Grouped album is opened
- **WHEN** the user opens a grouped Release card
- **THEN** the system returns the union of distinct recordings from its accepted Local Album Groups

#### Scenario: Grouped release appears across library surfaces
- **WHEN** Local Album Groups are accepted as one Release card
- **THEN** all albums, recent albums, artist albums, local search, home/recent surfaces, and album-detail navigation use the same grouped identity and canonical title

### Requirement: Stable grouped-card identity
The system SHALL identify each presented card as `release:` plus SHA-256 over sorted member group signatures and SHALL use that opaque ID for album-detail navigation.

#### Scenario: Canonical title changes
- **WHEN** a grouped card receives a different canonical title without member-signature changes
- **THEN** its grouped-card ID and detail navigation remain stable

### Requirement: Safe multi-group clustering
The system SHALL form a card from three or more Local Album Groups only when every pair in the connected candidate component is accepted and no pair is missing, separate, review, or vetoed.

#### Scenario: Three groups fully agree
- **WHEN** A-B, A-C, and B-C are all accepted
- **THEN** A, B, and C form one Release card

#### Scenario: Three-group relation conflicts
- **WHEN** A-B and B-C are accepted but A-C is missing, review, separate, or vetoed
- **THEN** the component remains separate and all implicated groups are marked for review

### Requirement: Deterministic canonical title
The system SHALL select the grouped card title by agreed normalized user choice; then directly matched local source identity with fixed source order TIDAL before MusicBrainz; then normalized agreement by two catalogs; then groups with trusted totals by slot-to-total ratio; then groups without totals; with remaining ties resolved by slot count, normalized title, and original Unicode code-point order.

#### Scenario: Catalog sources confirm title
- **WHEN** agreeing catalog evidence confirms one title and no user title exists
- **THEN** the grouped card uses the confirmed catalog title

#### Scenario: No catalog title is available
- **WHEN** no user or agreeing catalog title exists
- **THEN** the grouped card uses the title from the most complete local group with a deterministic tie-breaker

#### Scenario: User title is validated
- **WHEN** a grouping request supplies a title not belonging to a current member group
- **THEN** the system rejects the stale or invalid title instead of storing it

#### Scenario: User titles conflict inside a clique
- **WHEN** accepted pair decisions in one candidate clique store different normalized canonical titles
- **THEN** the component remains separate for review until the user choices agree

#### Scenario: Catalog display strings differ
- **WHEN** qualifying catalogs agree on normalized title but expose different display strings
- **THEN** the system chooses the display string using TIDAL-before-MusicBrainz source order, then normalized title and original Unicode code-point order

#### Scenario: Trusted totals are unavailable
- **WHEN** no candidate group has a trusted track total
- **THEN** the system ranks local titles by Recording Slot count, normalized title, and original Unicode code-point order

### Requirement: Deterministic weak evidence
The system SHALL compare sorted artwork-digest sets from all member paths with available art and sorted base-title-normalized parent-directory sets from all member paths.

#### Scenario: Groups contain multiple artworks and directories
- **WHEN** candidate groups span multiple files, artwork payloads, and parent directories
- **THEN** artwork contributes three points if digest sets intersect and path contributes two points if normalized directory sets intersect, independent of row order
