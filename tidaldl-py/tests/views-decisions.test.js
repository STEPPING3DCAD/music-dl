const { describe, expect, test } = require('bun:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const viewsSource = readFileSync(
  join(import.meta.dir, '../tidal_dl/gui/static/views.js'),
  'utf8',
);

function loadHomeRenderer(api) {
  const functionBody = viewsSource
    .split('async function renderHome(container) {')[1]
    ?.split('\nfunction _getContinueListeningState')[0];
  if (!functionBody) throw new Error('Home renderer not found');

  function element(tag) {
    return {
      tag,
      children: [],
      isConnected: true,
      classList: { add() {}, remove() {} },
      appendChild(child) { this.children.push(child); return child; },
      remove() {},
      set textContent(value) { this._text = String(value); this.children = []; },
      get textContent() { return (this._text || '') + this.children.map(child => child.textContent).join(''); },
    };
  }
  const h = (tag, props = {}, ...children) => {
    const node = element(tag);
    Object.assign(node, props);
    children.forEach(child => node.appendChild(child));
    return node;
  };
  const textEl = (tag, value, className) => h(tag, { textContent: value, className });

  return new Function(
    'api', 'h', 'textEl', 'document', '_greeting', '_renderContinueListening',
    '_renderHomeCold', '_renderHomeGrid', '_renderRecentStrip', 'recentlyPlayed',
    `async function renderHome(container) {${functionBody}\nreturn renderHome;`,
  )(
    api, h, textEl, { createTextNode: value => h('span', { textContent: value }) },
    () => 'Good afternoon,', () => {},
    () => {}, () => {}, () => {}, [],
  );
}

describe('Home view decisions', () => {
  test('shows an honest error instead of an empty-library state when Home fails', async () => {
    const renderHome = loadHomeRenderer(async () => { throw new Error('HTTP 500'); });
    const container = { children: [], appendChild(child) { this.children.push(child); } };

    await renderHome(container);

    const text = container.children[0].textContent;
    expect(text).toContain('Could not load Home');
    expect(text).toContain('could not load your library summary');
    expect(text).not.toContain("I'm feeling lucky");
  });
});

function loadGroupingDecisionPayload() {
  const helperSource = viewsSource.match(
    /function _groupingDecisionPayload\(assessment, decision, canonicalTitle\) \{[\s\S]*?\n\}/,
  );
  if (!helperSource) throw new Error('grouping decision helper not found');
  return new Function(`${helperSource[0]}\nreturn _groupingDecisionPayload;`)();
}

function loadDownloadHistoryRenderer(api) {
  const rendererSource = viewsSource.match(
    /async function loadDownloadHistory\(container\) \{[\s\S]*?\n\}\n\n\/\/ ---- SETTINGS VIEW ----/,
  );
  if (!rendererSource) throw new Error('download history renderer not found');

  function element(tag) {
    return {
      tag,
      children: [],
      style: {},
      classList: { add() {}, remove() {} },
      appendChild(child) { this.children.push(child); return child; },
      removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
      addEventListener() {},
      set textContent(value) { this._text = String(value); this.children = []; },
      get textContent() { return (this._text || '') + this.children.map(child => child.textContent).join(''); },
      get firstChild() { return this.children[0] || null; },
    };
  }

  const h = (tag, props = {}) => {
    const node = element(tag);
    Object.assign(node, props);
    return node;
  };
  const textEl = (tag, text, className) => {
    const node = element(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  };

  return new Function(
    'api',
    'h',
    'textEl',
    '_dlArtThumb',
    `const ICONS = {};
${rendererSource[0]}
return loadDownloadHistory;`,
  )(api, h, textEl, () => element('div'));
}

describe('album grouping review decisions', () => {
  test('keeps signatures and includes title only when grouping', () => {
    const payload = loadGroupingDecisionPayload();
    const assessment = { left_signature: 'left', right_signature: 'right' };

    expect(payload(assessment, 'group_together', 'Album')).toEqual({
      left_signature: 'left',
      right_signature: 'right',
      decision: 'group_together',
      canonical_title: 'Album',
    });
    expect(payload(assessment, 'keep_separate', 'Album')).toEqual({
      left_signature: 'left',
      right_signature: 'right',
      decision: 'keep_separate',
      canonical_title: null,
    });
  });
});

describe('download history decisions', () => {
  test('failed download history visibly renders persisted error reason', async () => {
    const reason = 'Quality mismatch: requested HI_RES_LOSSLESS but received HIGH with codec aac.';
    const loadDownloadHistory = loadDownloadHistoryRenderer(async () => ({
      downloads: [{ track_id: 118, name: 'Song', status: 'error', error: reason }],
    }));
    const container = { children: [], appendChild(child) { this.children.push(child); }, get firstChild() { return this.children[0] || null; }, removeChild() {} };

    await loadDownloadHistory(container);

    expect(container.children[0].textContent).toContain(reason);
    expect(container.children[0].textContent).toContain('Failed');
    expect(container.children[0].textContent).toContain('Retry');
  });

  test('failed download history without a reason retains retry controls', async () => {
    const loadDownloadHistory = loadDownloadHistoryRenderer(async () => ({
      downloads: [{ track_id: 118, name: 'Song', status: 'error', error: '' }],
    }));
    const container = { children: [], appendChild(child) { this.children.push(child); }, get firstChild() { return this.children[0] || null; }, removeChild() {} };

    await loadDownloadHistory(container);

    expect(container.children[0].textContent).toBe('SongFailedRetry');
  });
});

function loadArtistGroupingHelper() {
  const functionBody = viewsSource
    .split('function _groupArtistTracks(tracks) {')[1]
    ?.split('\nasync function loadLibraryArtistGrouped')[0];

  if (!functionBody) throw new Error('artist grouping helper not found');

  return new Function(
    `function _groupArtistTracks(tracks) {${functionBody}\nreturn _groupArtistTracks;`,
  )();
}

function loadTidalResetHelpers(deps = {}) {
  const helperSource = viewsSource.match(
    /function _authStateCanReset\(authState\) \{[\s\S]*?\n\}\n\nasync function _resetTidalConnection\(container\) \{[\s\S]*?\n\}/,
  );

  if (!helperSource) throw new Error('Tidal reset helpers not found');

  return new Function(
    'api',
    'clearInterval',
    '_dismissDeviceCodeModal',
    'loadAuthStatus',
    'refreshStatusLights',
    'toast',
    '_setRemotePlaybackUnavailable',
    'initialPoll',
    `let _loginPoll = initialPoll;
${helperSource[0]}
return { _authStateCanReset, _resetTidalConnection, getLoginPoll: () => _loginPoll };`,
  )(
    deps.api || (async () => ({})),
    deps.clearInterval || (() => {}),
    deps.dismiss || (() => {}),
    deps.loadAuthStatus || (async () => {}),
    deps.refreshStatusLights || (async () => {}),
    deps.toast || (() => {}),
    deps.clearRemote || (() => {}),
    deps.initialPoll === undefined ? 42 : deps.initialPoll,
  );
}

function wireTidalResetButton(deps = {}) {
  const block = viewsSource.match(
    /if \(_authStateCanReset\(data\.auth_state\)\) \{[\s\S]*?row\.appendChild\(resetBtn\);\n    \}/,
  );
  if (!block) throw new Error('Tidal reset button wiring not found');

  const listeners = [];
  const button = {
    addEventListener(type, listener) {
      if (type === 'click') listeners.push(listener);
    },
    click() {
      listeners.forEach(listener => listener());
    },
  };
  const row = { appendChild() {} };

  new Function(
    'data',
    '_authStateCanReset',
    'textEl',
    'inlineConfirm',
    '_resetTidalConnection',
    'container',
    'row',
    block[0],
  )(
    { auth_state: 'expired' },
    () => true,
    () => button,
    deps.inlineConfirm,
    deps.reset,
    {},
    row,
  );

  return button;
}

function loadAlbumFilterHelper() {
  const helperSource = viewsSource.match(
    /function _filterTidalAlbums\(items, qualityFilter, ratingFilter\) \{[\s\S]*?\n\}/,
  );
  if (!helperSource) throw new Error('album filter helper not found');
  return new Function(`${helperSource[0]}\nreturn _filterTidalAlbums;`)();
}

function loadRecentViewHelpers(recentlyPlayed, now) {
  const functionBody = viewsSource
    .split('function _recentFilterKey(playedAt) {')[1]
    ?.split('\nfunction renderRecentlyPlayed')[0];

  if (!functionBody) throw new Error('recent view helpers not found');

  return new Function(
    'recentlyPlayed',
    'Date',
    '_saveRecent',
    'navigate',
    'localStorage',
    `function _recentFilterKey(playedAt) {${functionBody}\nreturn { _recentFilterKey, _recentFilterCounts, _clearRecentOlderThan30Days };`,
  )(
    recentlyPlayed,
    { now: () => now },
    () => {},
    () => {},
    { getItem: () => null, setItem: () => {} },
  );
}

function loadRecentSync(recentlyPlayed, api) {
  const playerSource = readFileSync(join(import.meta.dir, '../tidal_dl/gui/static/player.js'), 'utf8');
  const functionBody = playerSource
    .split('async function _syncRecentFromServer() {')[1]
    ?.split('\nfunction updatePlayerHeart()')[0];

  if (!functionBody) throw new Error('recent sync helper not found');

  return new Function(
    'api',
    'recentlyPlayed',
    'MAX_RECENT',
    '_trackKey',
    '_saveRecent',
    'console',
    `async function _syncRecentFromServer() {${functionBody}\nreturn _syncRecentFromServer;`,
  )(
    api,
    recentlyPlayed,
    50,
    track => track.id || track.path || track.local_path || '',
    () => {},
    { warn: () => {} },
  );
}

describe('library view decisions', () => {
  test('keeps artists grouped when a later page crosses an artist boundary', () => {
    const groupArtistTracks = loadArtistGroupingHelper();
    const firstPage = [
      { artist: '*NSYNC', album: 'Hits', track_number: 1 },
      { artist: 'Adele', album: '19', track_number: 1 },
    ];
    const nextPage = [
      { artist: 'Adele', album: '21', track_number: 1 },
      { artist: 'Agnes Fredenberg', album: 'Solitude', track_number: 1 },
    ];

    const groups = groupArtistTracks(firstPage.concat(nextPage));

    expect(groups.map(group => group.artist)).toEqual([
      '*NSYNC',
      'Adele',
      'Agnes Fredenberg',
    ]);
    expect(groups[1].tracks).toHaveLength(2);
  });
});

describe('Tidal connection reset decisions', () => {
  test('shows reset only for existing or unhealthy credentials', () => {
    const { _authStateCanReset } = loadTidalResetHelpers();

    expect(_authStateCanReset('connected')).toBe(true);
    expect(_authStateCanReset('credentials_ready')).toBe(true);
    expect(_authStateCanReset('expired')).toBe(true);
    expect(_authStateCanReset('unavailable')).toBe(true);
    expect(_authStateCanReset('not_configured')).toBe(false);
  });

  test('waits for in-page confirmation before invoking reset', () => {
    let resetCalls = 0;
    let confirmation;
    const button = wireTidalResetButton({
      inlineConfirm: (message, onYes) => { confirmation = { message, onYes }; },
      reset: () => { resetCalls += 1; },
    });

    button.click();

    expect(resetCalls).toBe(0);
    expect(confirmation.message).toBe(
      'Reset the saved Tidal connection? You will need to log in again.',
    );
    confirmation.onYes();
    expect(resetCalls).toBe(1);
    expect(viewsSource).not.toContain("window.confirm('Reset the saved Tidal connection?");
  });

  test('confirm resets once without starting login and refreshes both auth surfaces', async () => {
    const calls = [];
    const container = { marker: 'connected' };
    const helpers = loadTidalResetHelpers({
      api: async (path, options) => { calls.push(['api', path, options]); },
      clearInterval: value => calls.push(['clearInterval', value]),
      dismiss: () => calls.push(['dismiss']),
      loadAuthStatus: async value => calls.push(['loadAuthStatus', value]),
      refreshStatusLights: async () => calls.push(['refreshStatusLights']),
      toast: (message, kind) => calls.push(['toast', message, kind]),
      clearRemote: value => calls.push(['clearRemote', value]),
    });

    const result = await helpers._resetTidalConnection(container);

    expect(result).toBe(true);
    expect(calls.filter(call => call[0] === 'api')).toEqual([
      ['api', '/auth/reset', { method: 'POST' }],
    ]);
    expect(calls).toContainEqual(['clearInterval', 42]);
    expect(calls).toContainEqual(['dismiss']);
    expect(calls).toContainEqual(['clearRemote', false]);
    expect(calls).toContainEqual(['loadAuthStatus', container]);
    expect(calls).toContainEqual(['refreshStatusLights']);
    expect(calls).toContainEqual(['toast', 'Tidal connection reset', 'success']);
    expect(helpers.getLoginPoll()).toBe(null);
  });

  test('failure keeps rendered status and reports error', async () => {
    const calls = [];
    const container = { marker: 'connected' };
    const helpers = loadTidalResetHelpers({
      api: async () => { throw new Error('local failure'); },
      loadAuthStatus: async () => calls.push(['loadAuthStatus']),
      refreshStatusLights: async () => calls.push(['refreshStatusLights']),
      toast: (message, kind) => calls.push(['toast', message, kind]),
    });

    const result = await helpers._resetTidalConnection(container);

    expect(result).toBe(false);
    expect(container.marker).toBe('connected');
    expect(calls).toEqual([['toast', 'Could not reset Tidal connection', 'error']]);
    expect(helpers.getLoginPoll()).toBe(42);
  });
});

describe('track source decisions', () => {
  test('shows local or Tidal source while leaving unknown remote format blank', () => {
    expect(viewsSource).toContain("track.is_local ? 'local' : 'tidal'");
    expect(viewsSource).toContain("className: 'source-tag ' + (track.is_local ? 'local-tag' : 'tidal-tag')");
    expect(viewsSource).toContain("if (track.format) return track.format.toUpperCase();\n  return '';");
  });
});

describe('recent history view decisions', () => {
  test('classifies a normalized current server play as Today', async () => {
    const now = 1_700_000_000_000;
    const recentlyPlayed = [];
    const syncRecentFromServer = loadRecentSync(recentlyPlayed, async () => ({
      tracks: [{ id: 'today', played_at: Math.floor(now / 1000) }],
    }));
    const views = loadRecentViewHelpers(recentlyPlayed, now);

    await syncRecentFromServer();

    expect(views._recentFilterKey(recentlyPlayed[0].played_at)).toBe('today');
    expect(views._recentFilterCounts()).toEqual({ all: 1, today: 1, week: 0, older: 0 });
  });

  test('classifies normalized weekly and older server plays', async () => {
    const now = 1_700_000_000_000;
    const recentlyPlayed = [];
    const syncRecentFromServer = loadRecentSync(recentlyPlayed, async () => ({
      tracks: [
        { id: 'week', played_at: Math.floor((now - 2 * 24 * 60 * 60 * 1000) / 1000) },
        { id: 'older', played_at: Math.floor((now - 31 * 24 * 60 * 60 * 1000) / 1000) },
      ],
    }));
    const views = loadRecentViewHelpers(recentlyPlayed, now);

    await syncRecentFromServer();

    expect(views._recentFilterCounts()).toEqual({ all: 2, today: 0, week: 1, older: 1 });
  });

  test('clears only server entries older than 30 days after normalization', async () => {
    const now = 1_700_000_000_000;
    const recentlyPlayed = [];
    const syncRecentFromServer = loadRecentSync(recentlyPlayed, async () => ({
      tracks: [
        { id: 'recent', played_at: Math.floor((now - 2 * 24 * 60 * 60 * 1000) / 1000) },
        { id: 'old', played_at: Math.floor((now - 31 * 24 * 60 * 60 * 1000) / 1000) },
      ],
    }));
    const views = loadRecentViewHelpers(recentlyPlayed, now);

    await syncRecentFromServer();
    views._clearRecentOlderThan30Days();

    expect(recentlyPlayed).toEqual([
      { id: 'recent', played_at: now - 2 * 24 * 60 * 60 * 1000 },
    ]);
  });
});

describe('download badge and requeue decisions', () => {
  test('badge is an absolute count from queue-state, not a local delta', () => {
    expect(viewsSource).toContain('function refreshDlBadge()');
    expect(viewsSource).toContain("api('/downloads/queue-state')");
    expect(viewsSource).toContain('setDlBadge(qs.active_count || 0)');
    expect(viewsSource).not.toMatch(/updateDlBadge\(\s*1\s*\)/);
    expect(viewsSource).not.toMatch(/updateDlBadge\(\s*-1\s*\)/);
    expect(viewsSource).not.toMatch(/updateDlBadge\(data\.count/);
    expect(viewsSource).not.toMatch(/updateDlBadge\(result\.missing\)/);
    expect(viewsSource).not.toMatch(/updateDlBadge\(missingTracks\.length\)/);
    expect(viewsSource).not.toMatch(/updateDlBadge\(nonLocal\.length\)/);
    expect(viewsSource).not.toMatch(/updateDlBadge\(resp\.count\)/);
  });

  test('clear history buttons refresh the Downloads badge', () => {
    const clearBlock = viewsSource.split("['Failed', 'Done', 'All'].forEach(label => {")[1];
    expect(clearBlock).toBeTruthy();
    expect(clearBlock).toContain("await api('/downloads/history' + qs, { method: 'DELETE' })");
    expect(clearBlock).toContain('refreshDlBadge()');
  });

  test('Cancel All clears the queued summary without waiting for SSE', () => {
    const cancelBlock = viewsSource.split("cancelBtn.textContent = 'Cancel All';")[1];
    expect(cancelBlock).toBeTruthy();
    expect(cancelBlock).toContain("await api('/downloads/cancel', { method: 'POST' })");
    expect(cancelBlock).toContain('_clearActiveDownloads()');
    expect(cancelBlock).toContain('_setQueuePaused(false)');
    expect(cancelBlock).toContain('refreshDlBadge()');
    expect(viewsSource).toContain('function _clearActiveDownloads()');
    expect(viewsSource).toContain("data.type === 'cancelled'");
    expect(viewsSource).toContain("data.type === 'progress' || data.type === 'complete' || data.type === 'error' || data.type === 'cancelled'");
    expect(viewsSource).toContain("queued === 1 ? ' track queued' : ' tracks queued'");
  });

  test('single-track download can be requeued after a missed terminal event', () => {
    const downloadTrack = viewsSource.split('async function downloadTrack(track, btn) {')[1];
    expect(downloadTrack).toBeTruthy();
    expect(downloadTrack).not.toContain('if (_downloading.has(track.id)) return;');
    expect(downloadTrack).toContain('refreshDlBadge()');
    expect(viewsSource).toContain('function _reconcileDownloadUi()');
    expect(viewsSource).toContain('_reconcileDownloadUi()');
    expect(viewsSource).toContain("activeEl.querySelector('.dl-batch-summary')");
    expect(viewsSource).toContain('setTimeout(_reconcileDownloadUi, 1500)');
  });
});

describe('Tidal album filter decisions', () => {
  test('filters albums by quality and rating', () => {
    const filterTidalAlbums = loadAlbumFilterHelper();
    const albums = [
      { id: 1, quality: 'HI_RES_LOSSLESS', explicit: true },
      { id: 2, quality: 'HI_RES', explicit: false },
      { id: 3, quality: 'LOSSLESS', explicit: false },
      { id: 4, quality: 'HIGH', explicit: true },
      { id: 5, quality: 'UNKNOWN', explicit: null, atmos: true },
    ];

    expect(filterTidalAlbums(albums, 'all', 'all')).toEqual(albums);
    expect(filterTidalAlbums(albums, 'max', 'all').map(album => album.id)).toEqual([1, 2]);
    expect(filterTidalAlbums(albums, 'lossless', 'all').map(album => album.id)).toEqual([3]);
    expect(filterTidalAlbums(albums, 'lossless', 'clean').map(album => album.id)).toEqual([3]);
    expect(filterTidalAlbums(albums, 'all', 'clean').map(album => album.id)).toEqual([2, 3]);
    expect(filterTidalAlbums(albums, 'high', 'explicit').map(album => album.id)).toEqual([4]);
    expect(filterTidalAlbums(albums, 'max', 'all').some(album => album.id === 5)).toBe(false);
    expect(filterTidalAlbums([{ id: 6, quality: 'MAX', explicit: false }], 'max', 'all')).toEqual([]);
    expect(filterTidalAlbums([{ id: 7, quality: 'HIGH', explicit: 'true' }], 'all', 'explicit')).toEqual([]);
  });
});
