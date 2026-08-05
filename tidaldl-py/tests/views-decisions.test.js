const { describe, expect, test } = require('bun:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const viewsSource = readFileSync(
  join(import.meta.dir, '../tidal_dl/gui/static/views.js'),
  'utf8',
);

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
    'window',
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
    deps.window || { confirm: () => true },
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

  test('cancel sends no request and preserves login polling', async () => {
    let requests = 0;
    const helpers = loadTidalResetHelpers({
      window: { confirm: () => false },
      api: async () => { requests += 1; },
    });

    const result = await helpers._resetTidalConnection({ marker: 'connected' });

    expect(result).toBe(false);
    expect(requests).toBe(0);
    expect(helpers.getLoginPoll()).toBe(42);
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
