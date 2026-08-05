# Album Search Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for every behavior change and superpowers:verification-before-completion before release work. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users identify and filter current TIDAL album search results by resolution tier and explicit-content state without extra catalog requests.

**Architecture:** Extend only album serialization in the existing search API, then apply a pure browser-side filter to the cached TIDAL album payload. Keep controls, cards, and styles in the existing Search view files; local-library results and non-album search responses remain unchanged.

**Tech Stack:** Python 3.12+, FastAPI serializers, vanilla JavaScript, CSS, Bun tests, pytest, OpenSpec, Tauri v2 release workflow.

---

## File map

- Create `tidaldl-py/tests/test_album_search_filters.py`: direct unit coverage for album-only TIDAL metadata serialization.
- Modify `tidaldl-py/tidal_dl/gui/api/search.py`: album serializer only; track, artist, and playlist responses stay unchanged.
- Modify `tidaldl-py/tidal_dl/gui/static/api.js`: current-session album filter state.
- Modify `tidaldl-py/tidal_dl/gui/static/views.js`: pure filtering, visible controls, cached rerender, counts, empty copy, and album badges.
- Modify `tidaldl-py/tidal_dl/gui/static/style.css`: filter-row, focus, badge, and narrow-layout styling.
- Modify `tidaldl-py/tests/views-decisions.test.js`: executable filter-decision coverage.
- Modify `tidaldl-py/tests/test_static_assets.py`: dependency-free UI/accessibility marker coverage.
- Modify `README.md`, `tidaldl-py/README.md`, and `tidaldl-py/updatelog.md`: user-facing feature and release notes.
- Modify existing version files only during the post-merge v1.7.0 release step through `scripts/release_version.py`; do not hand-edit them.

No new product module, dependency, backend query parameter, database field, or persistent browser preference is needed.

### Task 1: Serialize album resolution, Atmos, and explicit state

**Files:**
- Create: `tidaldl-py/tests/test_album_search_filters.py`
- Modify: `tidaldl-py/tidal_dl/gui/api/search.py:95-127`

- [x] **Step 1: Write failing album serializer tests**

Create direct tests that never start the FastAPI lifespan:

```python
from types import SimpleNamespace

from tidal_dl.gui.api.search import _serialize_album, _serialize_item


def _album(**overrides):
    values = {
        "id": 42,
        "name": "Edition",
        "artist": SimpleNamespace(name="Artist"),
        "num_tracks": 8,
        "media_metadata_tags": [],
        "audio_modes": [],
        "audio_quality": None,
        "explicit": None,
        "image": lambda size: f"https://example.test/{size}.jpg",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_album_serializer_keeps_hires_atmos_and_explicit_independent():
    result = _serialize_album(_album(
        media_metadata_tags=["HIRES_LOSSLESS", "DOLBY_ATMOS"],
        audio_quality="LOSSLESS",
        explicit=True,
    ))
    assert result["quality"] == "HI_RES_LOSSLESS"
    assert result["atmos"] is True
    assert result["explicit"] is True


def test_album_serializer_keeps_clean_lossless_state():
    result = _serialize_album(_album(audio_quality="LOSSLESS", explicit=False))
    assert (result["quality"], result["atmos"], result["explicit"]) == (
        "LOSSLESS", False, False,
    )


def test_album_serializer_marks_missing_metadata_unknown():
    result = _serialize_album(_album())
    assert result["quality"] == "UNKNOWN"
    assert result["atmos"] is False
    assert result["explicit"] is None


def test_generic_item_serializer_does_not_add_album_metadata():
    result = _serialize_item(SimpleNamespace(
        id=7, name="Artist", image=lambda size: "", roles=[],
    ))
    assert "quality" not in result
    assert "atmos" not in result
    assert "explicit" not in result
```

- [x] **Step 2: Run tests and verify RED**

Run from `tidaldl-py/`:

```shell
PYTHONNOUSERSITE=1 uv run --extra test python -m pytest -q tests/test_album_search_filters.py
```

Expected: collection fails because `_serialize_album` does not exist.

- [x] **Step 3: Add the minimum album-only serializer**

Keep `_serialize_track()` and `_serialize_item()` unchanged. Add one album wrapper:

```python
def _serialize_album(item: Any) -> dict:
    result = _serialize_item(item)
    tags = {str(tag).upper() for tag in (getattr(item, "media_metadata_tags", None) or [])}
    modes = {str(mode).upper() for mode in (getattr(item, "audio_modes", None) or [])}
    raw_quality = str(getattr(item, "audio_quality", "") or "").upper()

    if "HIRES_LOSSLESS" in tags:
        quality = "HI_RES_LOSSLESS"
    elif "HIRES" in tags:
        quality = "HI_RES"
    elif raw_quality in {"HI_RES_LOSSLESS", "HI_RES", "LOSSLESS", "HIGH", "LOW"}:
        quality = raw_quality
    else:
        quality = "UNKNOWN"

    explicit = getattr(item, "explicit", None)
    result.update({
        "quality": quality,
        "atmos": "DOLBY_ATMOS" in tags or "DOLBY_ATMOS" in modes,
        "explicit": explicit if isinstance(explicit, bool) else None,
    })
    return result
```

In `search()`, choose `_serialize_album` only when `type == "albums"`; continue using `_serialize_item` for artists and playlists.

- [x] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: 4 passed.

- [x] **Step 5: Commit backend metadata support**

```shell
git add tidaldl-py/tests/test_album_search_filters.py tidaldl-py/tidal_dl/gui/api/search.py
git commit -m "feat(search): expose album quality metadata"
```

### Task 2: Add pure in-memory album filter decisions

**Files:**
- Modify: `tidaldl-py/tests/views-decisions.test.js:1-143`
- Modify: `tidaldl-py/tidal_dl/gui/static/views.js:717-719`
- Modify: `tidaldl-py/tidal_dl/gui/static/api.js:145-161`

- [ ] **Step 1: Write failing Bun decision tests**

Add a source loader beside the existing helpers:

```javascript
function loadAlbumFilterHelper() {
  const helperSource = viewsSource.match(
    /function _filterTidalAlbums\(items, qualityFilter, ratingFilter\) \{[\s\S]*?\n\}/,
  );
  if (!helperSource) throw new Error('album filter helper not found');
  return new Function(`${helperSource[0]}\nreturn _filterTidalAlbums;`)();
}
```

Add cases using this payload:

```javascript
const albums = [
  { id: 1, quality: 'HI_RES_LOSSLESS', explicit: true },
  { id: 2, quality: 'HI_RES', explicit: false },
  { id: 3, quality: 'LOSSLESS', explicit: false },
  { id: 4, quality: 'HIGH', explicit: true },
  { id: 5, quality: 'UNKNOWN', explicit: null, atmos: true },
];
```

Assert All returns all five; Max returns IDs 1 and 2; Lossless plus Clean returns ID 3; High plus Explicit returns ID 4; unknown metadata passes only All.

- [ ] **Step 2: Run tests and verify RED**

```shell
bun test tests/views-decisions.test.js
```

Expected: `album filter helper not found`.

- [ ] **Step 3: Implement one pure filter helper and session state**

Add before `renderSearch()`:

```javascript
function _filterTidalAlbums(items, qualityFilter, ratingFilter) {
  return (items || []).filter(item => {
    const qualityMatches = qualityFilter === 'all'
      || (qualityFilter === 'max' && ['HI_RES_LOSSLESS', 'HI_RES'].includes(item.quality))
      || item.quality === qualityFilter.toUpperCase();
    const ratingMatches = ratingFilter === 'all'
      || (ratingFilter === 'explicit' ? item.explicit === true : item.explicit === false);
    return qualityMatches && ratingMatches;
  });
}
```

Add to existing `state` in `api.js`:

```javascript
albumQualityFilter: 'all',
albumRatingFilter: 'all',
```

Do not use `localStorage`; current-session state is enough.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all view-decision tests pass.

- [ ] **Step 5: Commit filter decisions**

```shell
git add tidaldl-py/tests/views-decisions.test.js tidaldl-py/tidal_dl/gui/static/views.js tidaldl-py/tidal_dl/gui/static/api.js
git commit -m "feat(search): filter cached Tidal albums"
```

### Task 3: Render accessible controls, counts, and filtered empty state

**Files:**
- Modify: `tidaldl-py/tests/test_static_assets.py:63-145`
- Modify: `tidaldl-py/tidal_dl/gui/static/views.js:719-1112`

- [ ] **Step 1: Write failing dependency-free UI contract test**

Add to `TestAppJsFeatureMarkers`:

```python
def test_has_accessible_album_search_filters_without_catalog_refetch(self):
    js = read_gui_js()
    source = js.split("function _renderAlbumFilterControls(")[1].split(
        "function renderSearch(container) {"
    )[0]
    assert "albumQualityFilter: 'all'" in js
    assert "albumRatingFilter: 'all'" in js
    assert "aria-pressed" in source
    assert "Clear filters" in source
    assert "_rerenderCachedSearch(resultsArea)" in source
    assert "doSearch(" not in source
    assert "Tidal Albums" in js
    assert "querySelector('.album-search-filters')" in js
    assert "No albums match these filters" in js
```

- [ ] **Step 2: Run test and verify RED**

```shell
PYTHONNOUSERSITE=1 uv run --extra test python -m pytest -q \
  tests/test_static_assets.py::TestAppJsFeatureMarkers::test_has_accessible_album_search_filters_without_catalog_refetch
```

Expected: split marker fails because the controls do not exist.

- [ ] **Step 3: Render controls from current state**

Add `_rerenderCachedSearch(resultsArea)` that calls `renderUnifiedSearchResults()` using only `state.searchResults`. Add `_renderAlbumFilterControls(container, resultsArea)` that:

- empties and rebuilds its own container;
- renders native `button` elements for the approved Quality and Rating values;
- sets `type="button"`, selected class, and `aria-pressed`;
- updates one state field on click, rebuilds its own buttons, and calls `_rerenderCachedSearch(resultsArea)`;
- shows one `Clear filters` button whenever either value is not All;
- resets both fields and rerenders cached data when Clear is clicked.

Mount one filter container under the existing type pills. Keep it mounted and set `hidden` unless `state.searchType === 'albums'`, because type-pill clicks do not rebuild the Search shell. Synchronize `hidden` in both paths that change `state.searchType`: the type-pill click handler and the recent-search chip handler in `_renderRecentSearches()`. The recent-search path can find the mounted container through `input.closest('.search-area')?.querySelector('.album-search-filters')`. Type changes may keep their existing TIDAL request; album filter clicks must never call `doSearch()`.

- [ ] **Step 4: Filter only the TIDAL album section**

In `renderUnifiedSearchResults()`:

1. Keep `localItems` unchanged.
2. Preserve the original TIDAL array and its count.
3. Apply `_filterTidalAlbums()` only when `type === 'albums'`.
4. Pass a shallow copied response with filtered `albums` and an `unfiltered_total` field to `renderSearchResults()`.
5. Render the TIDAL section even when filters reduce a non-empty payload to zero.
6. Avoid the generic duplicate `No results found` message in that filtered-zero case.

Album mode must have exactly one retained count path:

- `renderUnifiedSearchResults()` always creates one `Tidal Albums` results header for a non-empty original album payload, after any local-library section.
- That header shows `50 albums` when unfiltered or `12 of 50 albums` when filtered.
- Do not add the existing album divider in addition to this header.
- Add a `showHeader = true` parameter to `renderSearchResults()` and call it with `false` for Albums so its generic `Search Results` header is not created. Keep `true` for every existing non-album call so track, artist, and playlist rendering remains unchanged.

When filtered albums are empty but `unfiltered_total > 0`, the one outer header remains and the body shows `No albums match these filters` plus `Use Clear filters above to see every album.`

- [ ] **Step 5: Run focused Python and Bun checks**

Run the Step 2 command plus:

```shell
bun test tests/views-decisions.test.js
```

Expected: both pass.

- [ ] **Step 6: Commit interactive controls**

```shell
git add tidaldl-py/tests/test_static_assets.py tidaldl-py/tidal_dl/gui/static/views.js
git commit -m "feat(search): add album filter controls"
```

### Task 4: Add album metadata badges and responsive styling

**Files:**
- Modify: `tidaldl-py/tests/test_static_assets.py:63-145`
- Modify: `tidaldl-py/tidal_dl/gui/static/views.js:1072-1110`
- Modify: `tidaldl-py/tidal_dl/gui/static/style.css:389-418,1752-1772`

- [ ] **Step 1: Extend static test for badge and style contracts**

Assert GUI source contains MAX, LOSSLESS, HIGH, LOW, UNKNOWN, ATMOS, and E badge paths plus CSS contains `.album-search-filters`, `.album-search-badges`, `.album-search-badge`, and a visible `:focus-visible` rule.

- [ ] **Step 2: Run the focused static test and verify RED**

Use the exact pytest command from Task 3 Step 2. Expected: missing badge/style markers.

- [ ] **Step 3: Render independent badges on TIDAL album cards**

Only in the Albums branch, map resolution values with:

```javascript
const qualityLabel = {
  HI_RES_LOSSLESS: 'MAX',
  HI_RES: 'MAX',
  LOSSLESS: 'LOSSLESS',
  HIGH: 'HIGH',
  LOW: 'LOW',
}[item.quality] || 'UNKNOWN';
```

Append the resolution badge to an absolutely positioned badge container inside the artwork. Append ATMOS when `item.atmos === true` and E only when `item.explicit === true`. Do not add badges to artist, playlist, or local-library album cards.

- [ ] **Step 4: Add the minimum CSS**

Use existing colors, radii, mono typography, and `.pill` behavior. Add only:

- a wrapping album filter container and labeled filter groups;
- smaller filter buttons derived from `.pill`;
- visible `:focus-visible` outline;
- relative positioning for TIDAL album artwork;
- compact badge container and badge modifiers;
- one narrow-layout rule that stacks filter groups without horizontal overflow.

Do not create a new visual region, popover, framework, or animation.

- [ ] **Step 5: Run focused tests and inspect same-flow screenshot**

Run Bun and focused static tests. Start the GUI with an isolated test config, search Albums, capture the Search view at the same desktop width as the existing `docs/screenshots/search.png`, and compare controls, wrapping, counts, badges, focus, and empty state. Store evidence under ignored `output/issue-105/`; do not replace committed marketing screenshots unless the UI is release-ready and the user asks.

- [ ] **Step 6: Commit UI styling and badges**

```shell
git add tidaldl-py/tests/test_static_assets.py tidaldl-py/tidal_dl/gui/static/views.js tidaldl-py/tidal_dl/gui/static/style.css
git commit -m "feat(search): label album editions"
```

### Task 5: Document, verify, and review the feature diff

**Files:**
- Modify: `README.md:242-247`
- Modify: `tidaldl-py/README.md:19-28`
- Modify: `tidaldl-py/updatelog.md:21-23`
- Modify: `openspec/changes/add-album-search-filters/tasks.md`

- [ ] **Step 1: Update user-facing documentation before commit**

- Expand the root README TIDAL search bullet to mention album quality/content filters and badges.
- Add the same concise behavior to the package README.
- Add `## Unreleased` above v1.6.9 with one bullet for album filters and independent Max/Atmos/Explicit badges.

- [ ] **Step 2: Run isolated relevant and full checks**

From `tidaldl-py/`:

```shell
music_dl_test_config=$(mktemp -d)
MUSIC_DL_CONFIG_DIR="$music_dl_test_config" PYTHONNOUSERSITE=1 \
  uv run --extra test python -m pytest -q
bun test
cargo test --manifest-path src-tauri/Cargo.toml
```

From repository root:

```shell
PYTHONNOUSERSITE=1 uv run --project tidaldl-py --extra test python -m pytest -q \
  tests/test_documentation.py \
  tidaldl-py/tests/test_packaging.py \
  tests/test_release_version.py
uv run --project tidaldl-py python scripts/release_version.py check
openspec validate --strict add-album-search-filters
git diff --check
```

Expected: all checks pass, version remains 1.6.9 on the feature branch, and no Discord bot process or lockfile mutation remains.

- [ ] **Step 3: Run Ponytail review**

Confirm no new module/dependency/query parameter/persistence, no track serializer changes, and no duplicate filter implementation. Remove any speculative code or styles not exercised by approved requirements.

- [ ] **Step 4: Mark OpenSpec implementation tasks complete and validate again**

Check completed boxes only after their evidence exists, then rerun strict validation and `git diff --check`.

- [ ] **Step 5: Commit documentation and completion evidence**

```shell
git add README.md tidaldl-py/README.md tidaldl-py/updatelog.md \
  openspec/changes/add-album-search-filters/tasks.md
git commit -m "docs(search): document album filters"
```

### Task 6: Push, review, merge, and release v1.7.0 binaries

**Files:**
- Feature branch and PR: all files committed above
- Post-merge release metadata: files owned by `scripts/release_version.py`
- Release workflow: existing `.github/workflows/build-desktop.yml`

- [ ] **Step 1: Push feature branch and open PR closing issue #105**

Use SSH Git transport. PR body must summarize album-only scope, TDD evidence, screenshot evidence, full checks, and `Closes #105`. Do not tag a release from the feature branch.

- [ ] **Step 2: Review CI and merge only when clean**

Require all PR checks green and no merge conflict. Address findings through the same TDD/verification gates. Merge to `master` only after review approval.

- [ ] **Step 3: Prepare v1.7.0 metadata from current merged master**

Create an isolated release branch/worktree from freshly fetched `origin/master`, then run:

```shell
uv run --project tidaldl-py python scripts/release_version.py bump minor
uv run --project tidaldl-py python scripts/release_version.py check
PYTHONNOUSERSITE=1 uv run --project tidaldl-py --extra test python -m pytest -q \
  tests/test_release_version.py tidaldl-py/tests/test_packaging.py
```

Expected version: 1.7.0 across Python, Rust, Tauri, Cargo lock, UV lock, and changelog.

- [ ] **Step 4: Review and merge the release metadata PR**

Commit as `chore(release): prepare v1.7.0`, push through SSH, open a release PR, require green checks, and merge.

- [ ] **Step 5: Tag merged release commit and monitor binary builds**

From freshly fetched merged `master`, create annotated tag `v1.7.0` on the exact release commit and push the tag through SSH. Monitor `build-desktop` until Linux, macOS, Windows, and release-manifest jobs succeed.

- [ ] **Step 6: Verify published artifacts and install paths**

Confirm GitHub release v1.7.0 contains AppImage, DEB, DMG, signed updater archives/signatures, MSI/signature, checksums/digests, `latest.json`, and generated install notes. Smoke the macOS build locally and the Windows MSI on authorized PLEX-MINI without touching Hyper-V, networking, storage, or legacy `tidal-dl.exe`. Confirm album filters, badges, download action, and clean shutdown.

- [ ] **Step 7: Close completion loop**

Verify issue #105 closed by the feature PR, release points to the tagged commit, installers report v1.7.0, no test process remains, worktrees are clean, and all OpenSpec tasks have evidence.
