## 1. Baseline and metadata contract

- [x] 1.1 Add a focused failing fixture for the Marcos Witt exact-title split: one complete 30-track group and one partial four-recording group with duplicate physical files.
- [x] 1.2 Add failing metadata-reader tests for album artist, release date, track/disc positions and totals, MusicBrainz IDs, provider identity, and barcode across supported tag formats.
- [x] 1.3 Extend the existing idempotent SQLite migration with nullable release metadata columns and update schema documentation.
- [x] 1.4 Extend the existing metadata scan pass to persist supported release fields without adding another scanner.
- [x] 1.5 Verify old databases migrate in place and files lacking release metadata remain browsable.

## 2. Pure grouping rubric

- [x] 2.1 Add failing pure tests for exact candidate normalization, album-artist fallback, ISRC-overlap thresholds, and retained original edition markers.
- [x] 2.2 Add failing scorer tests for deterministic Recording Slot clustering/ordinals, conflicting ISRC tags, one-to-one ISRC/fallback formulas, multi-source fallback provenance, family caps, qualifying sources, diversity bonus, and 0-to-100 clamping.
- [x] 2.3 Add table-driven gate tests for scores 59, 60, 84, and 85; source/match/coverage gates; and the exact direct-identity bypass.
- [x] 2.4 Add failing veto tests for confirmed release-ID conflicts, incompatible totals, positioned recording conflicts, corroborated edition differences, and explicit keep-separate decisions.
- [x] 2.5 Implement one pure album-grouping module with exact candidate discovery, versioned canonical-JSON signatures, scoring, decision precedence, vetoes, outcomes, clique validation, stable card IDs, and canonical-title selection.
- [x] 2.6 Add boundary tests proving cover-only matches remain separate, scores 60 through 84 require review, and scores below 60 remain separate.
- [x] 2.7 Reuse the existing artwork extraction path to build deterministic candidate artwork-digest and parent-directory sets on demand and test weak caps, row-order independence, and post-scan recomputation.

## 3. Assessment persistence

- [x] 3.1 Add failing database tests for storing assessment evidence, vetoes, score, outcome, catalog attempt/result timestamps, optional user decision, and validated canonical title in one row per signature pair.
- [x] 3.2 Add the `album_grouping_assessments` migration and minimal indexes for pair/signature lookup.
- [x] 3.3 Implement assessment read/write and current-signature lookup using the existing LibraryDB structure.
- [x] 3.4 Verify restart/rescan persistence, release-identity membership invalidation, signature stability across format upgrades or extra physical copies, and duration-only reassessment that preserves the current user decision.

## 4. Optional catalog corroboration

- [x] 4.1 Add failing per-source eligibility and queue tests for current signatures, coalescing, skipped user decisions/vetoes/direct identities/source-success caches, mixed success/failure, and post-scan-only scheduling.
- [x] 4.2 Add failing tests showing unauthenticated TIDAL, offline MusicBrainz, timeouts, malformed responses, and rate limits leave local assessment usable and retry no sooner than 24 hours after a later scan.
- [x] 4.3 Implement optional TIDAL corroboration through the existing authenticated session without prompting for login.
- [x] 4.4 Implement cached MusicBrainz JSON lookup with an identifying User-Agent and a process-wide maximum of one request per second using existing HTTP facilities.
- [x] 4.5 Add disagreement and precedence tests proving ordinary catalog evidence preserves user decisions while a new hard veto safely supersedes grouping and exposes the reason.

## 5. Library API and review UI

- [x] 5.1 Add failing API tests for stable grouped-card IDs, clique and conflicting-user-title behavior, distinct recording count, unioned tracks, every canonical-title tie-break, possible-duplicate references, and explainable assessment payloads.
- [x] 5.2 Apply current Grouping Decisions consistently to all albums, recent albums, artist albums, local search, home/recent surfaces, and ID-based album detail while reusing existing track deduplication and quality preference.
- [x] 5.3 Add failing endpoint tests for `Group together`, `Keep separate`, current-member canonical-title selection, stale signatures, superseded decisions, and input validation.
- [x] 5.4 Add minimal decision endpoints and persist decisions/title only for current assessment signatures and current member titles.
- [x] 5.5 Add frontend behavior tests for the subtle possible-duplicate badge and non-blocking side-by-side evidence review.
- [x] 5.6 Render the review surface with family subtotals, contradictions, score, member-title choice, and grouping actions while preserving keyboard and screen-reader access.

## 6. Verification and documentation

- [x] 6.1 Run focused Python and frontend tests, then the relevant full suites and static checks with Bun and UV.
- [x] 6.2 Verify a real local-library scan groups the approved Marcos Witt case into one 30-recording card while a 30-versus-36 edition fixture remains separate.
- [x] 6.3 Verify library rendering never waits for network access, enrichment runs only after scan, successful evidence is not polled, failed evidence obeys retry timing, and MusicBrainz traffic respects the current one-request-per-second limit.
- [x] 6.4 Perform Ponytail review and remove any speculative abstraction, duplicated metadata pass, dependency, or DJAI/fingerprint scope.
- [x] 6.5 Update README/backend documentation and the existing design authority with user-visible grouping, review, offline, and non-destructive behavior.
- [x] 6.6 Run `openspec validate add-album-grouping-rubric --strict`, documentation checks, and `git diff --check`; record automated and manual evidence separately.

## Verification evidence

Automated:

- `PYTHONNOUSERSITE=1 uv run --extra test python -m pytest -q`: 707 passed, 1 skipped.
- `bun test`: 41 passed.
- `uv run pytest -q ../tests/test_documentation.py`: 2 passed.
- Focused grouping/API/database/frontend suite: 204 Python checks and 16 frontend checks passed.
- `openspec validate add-album-grouping-rubric --strict`: valid.
- `git diff --check`: passed.

Manual/read-only:

- Read the existing local library SQLite database in read-only mode. The Marcos Witt groups resolved to 30 Recording Slots for `25 Concierto Conmemorativo` and 4 Recording Slots from 16 physical files for `25 Concierto Conmemorativo (En Vivo)`.
- Applying the approved `Group together` decision produced one card with 30 distinct recordings.
- The 30-versus-36 fixture remained separate because confirmed release-ID and track-total conflicts are hard vetoes.
