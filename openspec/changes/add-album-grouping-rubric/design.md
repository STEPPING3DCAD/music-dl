## Context

Local album browsing currently groups `scanned` rows by exact album-title text. This is fast but treats spelling, capitalization, accent, and parenthetical differences as separate cards even when the files represent the same published release. Cover equality cannot resolve the ambiguity because distinct editions commonly reuse artwork.

The existing scanner stores track artist, title, album, duration, ISRC, quality, format, codec, and artwork availability. It does not retain enough release-level metadata to distinguish duplicate copies from extended, remastered, clean, instrumental, or other editions. The packaged application also does not bundle Chromaprint or `fpcalc`, so acoustic fingerprints cannot be required.

The feature must remain deterministic, offline-capable, non-destructive, and understandable without DJAI. Optional catalog evidence may improve confidence after scanning but must not block rendering. Non-veto evidence preserves explicit user decisions; newly established safety vetoes supersede unsafe grouping.

## Goals / Non-Goals

**Goals:**

- Present duplicate or partial copies of one Release as one album card.
- Preserve distinct Releases as separate cards.
- Make every decision reproducible and explainable through capped evidence families and hard vetoes.
- Reward both track coverage and agreement across independent sources.
- Keep ambiguous cases visible and reviewable without interrupting scans.
- Persist decisions while invalidating them when release-identity membership materially changes; a duration-only replacement that preserves the Recording Slot set is evidence refresh, not an identity change.

**Non-Goals:**

- Delete, move, rename, retag, or otherwise clean up audio files.
- Combine standard, extended, deluxe, remastered, clean, explicit, instrumental, commentary, or bonus-disc editions.
- Require TIDAL, MusicBrainz, network access, AI, Chromaprint, or a new package.
- Add an edition selector or DJAI integration.
- Detect byte-for-byte duplicate files; the existing duplicate-file workflow remains separate.

## Decisions

### 1. Preserve exact-title groups as the input boundary

The current exact-title query remains the first grouping step and produces Local Album Groups. Candidate discovery compares summaries of those groups instead of replacing `GROUP BY album` with destructive normalization.

Text normalization performs Unicode NFKD decomposition, removes combining marks, case-folds, replaces non-alphanumeric runs with one space, and collapses whitespace. Base-title normalization additionally removes all trailing balanced `(...)` or `[...]` segments before applying the same normalization. Two titles are compatible when either their full normalized titles or base titles are equal.

Album artist uses the embedded album artist when present, otherwise the one common normalized track artist; mixed track artists have no fallback album artist. Candidate discovery pairs groups when either:

- an identical MusicBrainz Release ID or identical provider namespace and album ID agrees; or
- non-empty normalized album artists and compatible titles agree; or
- non-empty normalized album artists agree and exact ISRC overlap contains at least `min(2, smaller Recording Slot count)` slots and at least 50% of the smaller group.

Normalization only creates a Duplicate Release Candidate. It never decides grouping, and the original title and edition markers remain available to the rubric.

Alternative rejected: normalize titles directly in SQL. It would incorrectly collapse distinct editions before contradictions could be evaluated.

### 2. Extend scan metadata instead of adding a second scanner

The existing local scan path will additionally retain nullable release metadata already present in file tags or download metadata:

- album artist;
- release date or year;
- track number and embedded track total;
- disc number and embedded disc total;
- MusicBrainz release and release-group identifiers;
- provider namespace and album identifier when available;
- barcode or UPC when available.

Unavailable fields stay null. Observed local file count never substitutes for an embedded or catalog track total because partial libraries are valid.

Alternative rejected: rescan files in a separate grouping service. That duplicates decoding work, metadata rules, and error handling.

### 3. Use one pure scorer with capped evidence families

A single pure function accepts two Local Album Group summaries and returns a Grouping Assessment containing:

- stable left and right group signatures;
- evidence items with value, one or more provenance sources, score family, contribution, and explanation;
- family subtotals and diversity bonus;
- hard vetoes;
- final score from 0 through 100;
- outcome: `auto_group`, `review`, or `separate`.

Each evidence item has one score family and a set of provenance sources. Provenance sources are `local_tags`, `decoded_audio`, `filesystem`, `download_history`, `tidal`, and `musicbrainz`. ISRC evidence cites `local_tags`; fallback recording evidence cites both `local_tags` and `decoded_audio`; release fields cite the source from which that field was stored; catalog evidence cites its catalog. A source qualifies for auto-group diversity only when it contributes positive non-weak evidence; filesystem artwork/path evidence never satisfies that gate or earns a diversity bonus.

Before scoring, each Local Album Group collapses physical copies into Recording Slots. Rows are partitioned by normalized track artist/title and disc/track position. Within each partition, rows sorted by integer duration then path join the first duration cluster whose minimum and maximum would remain no more than five seconds apart; otherwise they start a new cluster. Clusters receive a zero-based ordinal by minimum duration then path. This handles unpositioned repeated titles without depending on database row order.

A slot key is normalized track artist, normalized title, disc number, track number, and cluster ordinal. It never contains ISRC or duration, so adding a compatible physical copy cannot change an existing key. A valid ISRC is uppercased, stripped of separators, and must match `[A-Z]{2}[A-Z0-9]{3}[0-9]{7}`. Each slot retains its set of valid ISRCs. A slot with more than one ISRC is internally conflicted: it earns no ISRC points and its ISRCs cannot create a veto. Format, quality, path, and artwork are also excluded from the key.

Recording matching is deterministic and one-to-one:

1. Pair equal single valid ISRCs from unambiguous slots, sorted by slot key.
2. For remaining slots, require equal normalized track artist and title, equal non-null track number, disc numbers that are equal or both absent, and duration difference no greater than five seconds.
3. When multiple fallback pairs are possible, choose smallest duration difference and then recording-key order.

Let `N` be Recording Slots in the smaller group. ISRC contribution is `floor(40 * isrc_matches / N)`. Fallback contribution is `floor(25 * fallback_matches / N)`. Total recording contribution is capped at 55, and total coverage is `(isrc_matches + fallback_matches) / N`.

The scorer uses these family caps:

| Evidence family | Contribution | Cap |
|---|---:|---:|
| Authoritative release identity | MusicBrainz Release ID 100; exact provider namespace and album ID 95; barcode/UPC 80; MusicBrainz Release Group ID 20 | 100 |
| Recording agreement | ISRC coverage up to 40; unmatched title + position + duration coverage up to 25 | 55 |
| Release metadata | album artist 6; compatible title 5; date/year 4; embedded track total 6; disc total 4 | 25 |
| Optional catalog corroboration | TIDAL confirmation 10; MusicBrainz confirmation 10, excluding facts already counted as authoritative identity | 20 |
| Weak presentation evidence | artwork digest 3; compatible path organization 2 | 5 |
| Independent-source diversity | 5 for each qualifying provenance source after the first | 15 |

Contributions are integer points, clamped to family caps, then summed and clamped to 100. Album artist contributes on exact normalized equality; title contributes on Decision 1 compatibility; date contributes when full dates agree or years agree when either side supplies only a year; disc/track totals contribute on equal non-null embedded values. Multiple tags from one file lineage increase coverage inside a family but count as one provenance source.

A catalog source corroborates the pair only when both Local Album Groups resolve to the same source release entity. Without a direct source ID, each local group must match the source album artist and at least `min(3, local slot count)` Recording Slots covering at least 90% of that local group. TIDAL and MusicBrainz then contribute 10 points each. Facts already counted as authoritative identity are not counted again as catalog corroboration.

Artwork digest is computed only for candidate pairs by hashing artwork bytes from every member path with available local art through the existing extraction path, then deduplicating and sorting the digest set. Artwork contributes three points when group digest sets intersect. Path evidence uses the sorted set of base-title-normalized parent directory names from every member path and contributes two points when those sets intersect. Neither is a scanned column; both are recomputed when a scan touches a member path. Both remain weak evidence.

Automatic grouping requires all of:

- score at least 85;
- no hard veto;
- at least two qualifying provenance sources;
- at least three matched recordings;
- matched Recording Slots cover at least 90% of slots in the smaller group.

An identical MusicBrainz Release ID or identical provider namespace and album ID bypasses the source-diversity, three-match, and 90-percent coverage gates because it is a direct release identity. A hard veto always produces `separate`. Otherwise, score 85 or greater with failed auto gates produces `review`, scores 60 through 84 produce `review`, and scores below 60 produce `separate`.

Alternative rejected: a strict decision tree cannot degrade gracefully when tags are incomplete. A learned classifier is opaque, has no trustworthy training set, and would introduce an unnecessary runtime dependency.

### 4. Contradictions override coincidence

Hard vetoes apply only to authoritative or independently corroborated contradictions:

- confirmed different MusicBrainz Release IDs;
- confirmed incompatible barcodes or same-provider album identities;
- different embedded or catalog disc/track totals, such as 30 versus 36;
- the same disc and track position mapping to different verified recordings;
- edition markers supported by a different tracklist, totals, or recording set;
- a persisted `keep_separate` decision for the current pair signatures.

A locally embedded release-level value is confirmed when the same non-empty value appears on at least three distinct recordings in its Local Album Group, or on every recording when the group has fewer than three. A catalog value is confirmed by a direct authoritative identity lookup. A positioned recording conflict is verified by differing valid ISRCs or differing authoritative catalog recording IDs. Both sides of a contradiction must be confirmed before it becomes a hard veto; one uncorroborated contradiction routes to review.

A title marker such as `(En Vivo)` is neither positive proof nor a veto by itself. Likewise, observed local file counts may differ because one group is incomplete. Title spelling or styling disagreements between catalogs are not material release contradictions.

Decision precedence is fixed:

1. Ignore stored decisions whose group signatures are no longer current.
2. A current `keep_separate` decision produces `separate`.
3. Any other current hard veto produces `separate`; if it appeared after `group_together`, the old choice is marked superseded and the assessment explains why grouping was revoked.
4. A current `group_together` decision groups regardless of score or non-veto catalog evidence.
5. Without a user decision, apply the rubric outcome.

Ordinary new catalog points cannot override a current user choice. Safety vetoes can because distinct Releases must never be silently combined.

### 5. Persist assessment and user choice in one table

Add one `album_grouping_assessments` table rather than separate cache and decision layers. Each row stores the sorted pair key, both group signatures, score, outcome, veto and evidence JSON, optional user decision, optional selected canonical title, catalog attempt/result timestamps, and evaluation timestamp.

A version-1 group signature is SHA-256 over UTF-8 canonical JSON with sorted keys, non-ASCII characters preserved, and compact separators. The payload contains the exact display album title and its normalized form, normalized album artist, locally stored release date, embedded disc/track totals, locally stored MusicBrainz/provider/barcode identifiers, and the sorted Recording Slot keys defined in Decision 3. The display title prevents two exact-title SQL groups that normalize identically from colliding. Paths, format, quality, artwork, online catalog responses, raw duration, and duplicate physical copies are excluded. Adding, removing, or changing a represented slot's identity fields changes the signature; duration-only replacements that preserve the Recording Slot set, format upgrades, and extra copies do not. The pair key is SHA-256 over the two sorted group signatures.

The current-signature row is the only applicable decision. A release-identity membership change creates a new signature and forces reevaluation before any old decision applies. When a scan detects only changed duration evidence for current signatures, it recomputes and overwrites the automatic assessment in the same row while preserving the current user decision. This deliberately treats duration as matching evidence rather than release identity.

Alternative rejected: store the pair decision on every track. That duplicates state and makes invalidation inconsistent.

### 6. Keep online enrichment optional, cached, and off the render path

Local assessment runs after scan metadata is committed. A `(candidate, source)` work item is eligible for enrichment when it has current signatures, no user decision, no hard veto, no direct authoritative identity for that source, and no successful result from that source for those signatures. Eligible work items enter one coalescing FIFO background queue after the scan completes:

- TIDAL only when the existing session is already authenticated;
- MusicBrainz without user authentication, with a meaningful music-dl User-Agent, no more than one request per second, and cached responses;
- timeouts, rate limits, authentication loss, malformed responses, and network failures recorded as unavailable evidence rather than user-facing scan failures;
- each source result and attempt timestamp cached independently for the lifetime of the current signatures with no periodic refresh or polling;
- a failed source retried only on a later completed scan and no sooner than 24 hours after that source's previous attempt, even when another source already succeeded.

Each completed source result immediately recomputes and persists the assessment. Rendering always uses the latest persisted local or enriched assessment and never waits for either catalog. One uncorroborated material catalog contradiction forces `review`; an authoritative or independently corroborated contradiction becomes a hard veto under Decision 4. Non-veto online evidence cannot override a current user decision.

Alternative rejected: query catalogs while rendering album cards. It adds latency, makes offline output unstable, and risks excessive provider traffic.

### 7. Apply grouping at the existing album API boundary

The existing album browse service remains responsible for fetching Local Album Groups. A small album-grouping module performs candidate discovery and pure scoring; the API applies current Grouping Decisions before serialization.

Accepted pair relations form a graph. Multiple Local Album Groups form one card only when every pair in their connected component is accepted and no pair is separate, review, missing, or vetoed. A non-clique component remains separate and every implicated group is marked for review; this avoids arbitrary transitive grouping such as A↔B and B↔C when A conflicts with C.

Every presented card receives an opaque stable ID: `release:` plus SHA-256 of its sorted member group signatures. A single ungrouped Local Album Group uses the same formula with one member. This ID, not canonical title, drives album-detail navigation.

An accepted card returns tracks from all member Local Album Groups, deduplicated through the existing normalized-title/artist and quality-preference behavior. Track count means distinct presented recordings, not physical files. Grouping is applied consistently to all local album-card surfaces: all albums, recent albums, artist albums, local album search, home/recent surfaces, and album-detail navigation.

Canonical title priority is:

1. One normalized user-selected current member title. If accepted pair decisions in a clique store different normalized user titles, the clique returns to review until choices agree; equivalent display strings use original Unicode code-point order.
2. A title from a catalog identity directly matched to a locally stored source ID, preferring `tidal` then `musicbrainz`; ties use normalized title then original Unicode code-point order.
3. An exact normalized title agreed by at least two catalogs, choosing the display string by the same fixed source and lexical order.
4. The locally most complete group. Groups with trusted totals rank by Recording Slot count divided by trusted total; groups without totals rank after them. Remaining ties use Recording Slot count, normalized title, then original Unicode code-point order.

Ambiguous cards remain separate and expose a `possible_duplicate` assessment reference. The existing UI shows a subtle badge; selecting it opens side-by-side titles, counts, evidence-family contributions, contradictions, score, and `Group together` / `Keep separate` actions. Grouping review defaults the title choice to the computed canonical title and permits selecting one current member title before confirmation. Review never interrupts scanning.

One new scoring module is justified because retrieval and decision logic have different responsibilities and the scorer must be testable without SQLite, network, or UI state. No interface, factory, service layer, or new dependency is added.

## Risks / Trade-offs

- [Incorrect source independence inflates confidence] → Assign each signal fixed provenance sources, cap score families, and expose both dimensions.
- [Bad embedded identifiers create false certainty] → Require direct identity equality or independent corroboration; conflicting authoritative data vetoes automation.
- [Partial libraries look like different editions] → Use embedded/catalog totals rather than observed file count and calculate coverage against the smaller distinct recording set.
- [Catalog metadata changes after caching] → Cache by group signatures without polling; recompute on a new signature and let non-veto evidence preserve current user choices.
- [MusicBrainz throttles requests] → Identify music-dl, keep at or below one request per second, cache results, and treat 503 as unavailable evidence.
- [Background enrichment changes visible cards] → Apply refreshed decisions after assessment persistence, surface the evidence, and let hard vetoes supersede unsafe choices explicitly rather than silently.
- [Pairwise decisions conflict across three groups] → Require complete accepted cliques; keep non-clique components separate for review.
- [Schema growth slows scanning] → Read the added tags during the existing metadata pass and index only the assessment pair key/signatures needed for lookups.

## Migration Plan

1. Add nullable release metadata columns and the assessment table through the existing idempotent SQLite migration path.
2. Existing rows remain valid; added fields are populated on subsequent normal or targeted metadata scans.
3. Until enough evidence exists, existing exact-title cards remain separate.
4. Rollback ignores the added columns/table and returns to exact-title grouping; no audio files or tags require restoration.

## Open Questions

None. DJAI integration, fingerprints, destructive duplicate cleanup, and edition navigation require separate future changes.
