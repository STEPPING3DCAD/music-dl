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

function loadRepeatHandler(state) {
  const section = playerSource
    .split("btnRepeat.addEventListener('click', () => {")[1]
    .split('\nfunction _updateRepeatIcon')[0];
  const handlerBody = section.slice(0, section.lastIndexOf('});'));

  if (!handlerBody) throw new Error('repeat handler not found');

  const noop = () => {};
  const btnRepeat = {
    classList: { toggle: noop },
    querySelector: () => null,
    title: '',
  };
  return new Function(
    'state',
    'btnRepeat',
    '_updateRepeatIcon',
    '_saveQueue',
    '_savePlayerPrefs',
    `return () => {${handlerBody}};`,
  )(state, btnRepeat, noop, noop, noop);
}

function loadPlayButtonHandler(audio, state, playTrack) {
  const section = playerSource
    .split("btnPlay.addEventListener('click', () => {")[1]
    .split("\nbtnNext.addEventListener('click', () => {")[0];
  const handlerBody = section.slice(0, section.lastIndexOf('});'));

  if (!handlerBody) throw new Error('play button handler not found');

  return new Function(
    'audio',
    'state',
    'location',
    'playTrack',
    'updatePlayButton',
    `return () => {${handlerBody}};`,
  )(audio, state, { href: 'http://localhost/' }, playTrack, () => {});
}

function loadUpgradeQualityJump(qualityTitle) {
  const helperSource = playerSource.match(
    /function _upgradeQualityJump\(result\) \{[\s\S]*?\n\}/,
  );

  if (!helperSource) throw new Error('upgrade quality label helper not found');

  return new Function(
    'qualityTitle',
    `${helperSource[0]}\nreturn _upgradeQualityJump;`,
  )(qualityTitle);
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

  test('repeat one preserves the current queue and position', () => {
    const queue = [{ name: 'First' }, { name: 'Current' }, { name: 'Last' }];
    const state = { repeat: 'all', queue, queueIndex: 1 };
    const toggleRepeat = loadRepeatHandler(state);

    toggleRepeat();

    expect(state.repeat).toBe('one');
    expect(state.queue).toEqual(queue);
    expect(state.queueIndex).toBe(1);
  });

  test('play starts a restored queue when no resume position supplied a source', () => {
    const current = { name: 'Restored track', is_local: true };
    const state = { playing: false, queue: [current], queueIndex: 0 };
    const audio = {
      src: '',
      paused: true,
      play: () => Promise.resolve(),
      pause: () => {},
    };
    let startedTrack = null;
    const clickPlay = loadPlayButtonHandler(audio, state, track => {
      startedTrack = track;
    });

    clickPlay();

    expect(startedTrack).toBe(current);
  });

  test('queue prevents removing the active track', () => {
    expect(playerSource).toContain('remove.disabled = i === state.queueIndex;');
  });

  test('upgrade results keep distinct high-resolution quality descriptions', () => {
    const qualityDescriptions = {
      '44100Hz/24bit': '44100Hz/24bit · Hi-Res',
      HI_RES_LOSSLESS: 'Hi-Res Lossless · 24-bit FLAC',
    };
    const qualityJump = loadUpgradeQualityJump(quality => qualityDescriptions[quality]);

    expect(qualityJump({
      current_quality: '44100Hz/24bit',
      available_quality: 'HI_RES_LOSSLESS',
    })).toBe('44100Hz/24bit · Hi-Res → Hi-Res Lossless · 24-bit FLAC');
  });

  test('remote stream failures do not auto-skip through more Tidal tracks', () => {
    expect(playerSource).toContain('if (!current || !current.is_local) {');
    expect(playerSource).toContain("toast('Tidal stream unavailable \\u2014 try again later', 'error');");
    expect(playerSource).toContain('const canAutoSkip = state.queueIndex < state.queue.length - 1;');
  });
});
