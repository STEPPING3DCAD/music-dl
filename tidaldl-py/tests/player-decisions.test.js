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
});
