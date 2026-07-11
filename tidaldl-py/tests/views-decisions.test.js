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
