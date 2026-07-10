const { describe, expect, test } = require('bun:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const playerSource = readFileSync(
  join(import.meta.dir, '../tidal_dl/gui/static/player.js'),
  'utf8',
);

function loadDecisionHelpers() {
  const helperSource = playerSource.match(
    /function _setupMustBlock\(setupData\) \{[\s\S]*?\n\}\n\nfunction _authStateNeedsExpiredBanner\(authState\) \{[\s\S]*?\n\}/,
  );

  if (!helperSource) throw new Error('Player decision helpers not found');

  return new Function(`${helperSource[0]}\nreturn { _setupMustBlock, _authStateNeedsExpiredBanner };`)();
}

function loadSearchRefreshHelper(state, document, doSearch) {
  const helperSource = playerSource.match(
    /async function _refreshSearchAfterLogin\(\) \{[\s\S]*?\n\}/,
  );

  if (!helperSource) throw new Error('Search refresh helper not found');

  return new Function(
    'state',
    'document',
    'doSearch',
    `${helperSource[0]}\nreturn _refreshSearchAfterLogin;`,
  )(state, document, doSearch);
}

function loadPlayTrack(audio, state) {
  const functionSource = playerSource.split('function playTrack(track) {')[1]
    .split('\nfunction updateNowPlaying(track) {')[0];

  if (!functionSource) throw new Error('playTrack function not found');

  const noop = () => {};
  return new Function(
    'audio',
    'state',
    '_resetPlayCount',
    '_recordRecentlyPlayed',
    'toast',
    'updatePlayButton',
    'updateNowPlaying',
    'handleLyricsTrackChange',
    '_updateMediaSession',
    '_fetchWaveform',
    'highlightPlayingTrack',
    'updatePlayerHeart',
    '_saveQueue',
    `function playTrack(track) {${functionSource}\nreturn playTrack;`,
  )(audio, state, noop, noop, noop, noop, noop, noop, noop, noop, noop, noop, noop);
}

describe('player onboarding decisions', () => {
  test('blocks only when scan paths are missing', () => {
    const { _setupMustBlock } = loadDecisionHelpers();

    expect(_setupMustBlock({ logged_in: true, scan_paths_configured: false })).toBe(true);
    expect(_setupMustBlock({ logged_in: false, scan_paths_configured: true })).toBe(false);
  });

  test('shows expired banner only for an expired auth state', () => {
    const { _authStateNeedsExpiredBanner } = loadDecisionHelpers();

    expect(_authStateNeedsExpiredBanner('not_configured')).toBe(false);
    expect(_authStateNeedsExpiredBanner('expired')).toBe(true);
  });

  test('clears cached Tidal auth state and reruns the active search after login', async () => {
    const state = {
      view: 'search',
      searchQuery: 'coast',
      searchResults: { local: { tracks: [] }, tidal: null, tidalAuthRequired: true },
    };
    const resultsArea = { id: 'search-results' };
    const doSearch = async area => {
      expect(area).toBe(resultsArea);
      expect(state.searchResults).toBeNull();
      state.searchResults = { local: { tracks: [] }, tidal: { tracks: [{ id: '1' }] }, tidalAuthRequired: false };
    };
    const refreshSearch = loadSearchRefreshHelper(state, {
      querySelector: selector => selector === '.results' ? resultsArea : null,
    }, doSearch);

    await refreshSearch();

    expect(state.searchResults.tidalAuthRequired).toBe(false);
    expect(state.searchResults.tidal.tracks).toHaveLength(1);
  });

  test('clears a stale auth-required result without rerunning an inactive search', async () => {
    const state = {
      view: 'library',
      searchQuery: 'coast',
      searchResults: { local: { tracks: [] }, tidal: null, tidalAuthRequired: true },
    };
    const doSearch = async () => {
      throw new Error('inactive search should not rerun');
    };
    const refreshSearch = loadSearchRefreshHelper(state, {
      querySelector: () => ({ id: 'search-results' }),
    }, doSearch);

    await refreshSearch();

    expect(state.searchResults).toBeNull();
  });
});

describe('local playback decisions', () => {
  test('loads a selected local source after installing the readiness listener', () => {
    const calls = [];
    const state = { playing: false };
    const audio = {
      src: '',
      muted: false,
      pause: () => calls.push('pause'),
      addEventListener: eventName => calls.push(eventName),
      load: () => {
        expect(state.playing).toBe(true);
        calls.push('load');
      },
      play: () => Promise.resolve(),
    };
    const playTrack = loadPlayTrack(audio, state);

    playTrack({ is_local: true, local_path: '/music/local track.flac' });

    expect(audio.src).toBe('/api/playback/local?path=%2Fmusic%2Flocal%20track.flac');
    expect(calls).toEqual(['pause', 'canplay', 'load']);
  });
});
