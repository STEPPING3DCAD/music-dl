const { describe, expect, test } = require('bun:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const viewsSource = readFileSync(
  join(import.meta.dir, '../tidal_dl/gui/static/views.js'),
  'utf8',
);
const apiSource = readFileSync(
  join(import.meta.dir, '../tidal_dl/gui/static/api.js'),
  'utf8',
);

function loadQualityTier() {
  const helperSource = apiSource.match(
    /function _qualityTier\(q, fmt(?:, codec)?\) \{[\s\S]*?\n\}/,
  );
  if (!helperSource) throw new Error('quality tier helper not found');
  return new Function(`${helperSource[0]}\nreturn _qualityTier;`)();
}

function loadArtistGroupingHelper() {
  const functionBody = viewsSource
    .split('function _groupArtistTracks(tracks) {')[1]
    ?.split('\nasync function loadLibraryArtistGrouped')[0];

  if (!functionBody) throw new Error('artist grouping helper not found');

  return new Function(
    `function _groupArtistTracks(tracks) {${functionBody}\nreturn _groupArtistTracks;`,
  )();
}

function loadHomeArtistSelection() {
  const helperSource = viewsSource.match(
    /function _homeArtistSelection\(data\) \{[\s\S]*?\n\}/,
  );

  if (!helperSource) throw new Error('home artist selection helper not found');
  return new Function(`${helperSource[0]}\nreturn _homeArtistSelection;`)();
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
    deps.initialPoll === undefined ? 42 : deps.initialPoll,
  );
}

describe('library view decisions', () => {
  test('uses stream codec instead of M4A container for quality tier', () => {
    const qualityTier = loadQualityTier();

    expect(qualityTier('44100Hz/16bit', 'M4A', 'flac').tier).toBe('Lossless');
    expect(qualityTier('44100Hz/16bit', 'M4A', 'aac').tier).toBe('Lossy');
  });

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

describe('home view decisions', () => {
  test('keeps all-time principal artist and two secondary artist cards', () => {
    const selectArtists = loadHomeArtistSelection();
    const data = {
      top_artist: { name: 'Principal', play_count: 100 },
      top_artists: [
        { name: 'Principal', play_count: 100 },
        { name: 'Second', play_count: 50 },
        { name: 'Third', play_count: 25 },
      ],
      this_week: {
        top_artist: { name: 'Weekly', play_count: 8 },
        top_artists: [
          { name: 'Weekly', play_count: 8 },
          { name: 'Weekly second', play_count: 2 },
        ],
      },
    };

    const selection = selectArtists(data);

    expect(selection.hero.name).toBe('Principal');
    expect(selection.secondary.map(artist => artist.name)).toEqual([
      'Second',
      'Third',
    ]);
  });
});

describe('Tidal connection reset decisions', () => {
  test('shows reset only for existing or unhealthy credentials', () => {
    const { _authStateCanReset } = loadTidalResetHelpers();

    expect(_authStateCanReset('connected')).toBe(true);
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
    });

    const result = await helpers._resetTidalConnection(container);

    expect(result).toBe(true);
    expect(calls.filter(call => call[0] === 'api')).toEqual([
      ['api', '/auth/reset', { method: 'POST' }],
    ]);
    expect(calls).toContainEqual(['clearInterval', 42]);
    expect(calls).toContainEqual(['dismiss']);
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
