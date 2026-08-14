"""Focused local-release fixtures shared by grouping tests."""


def marcos_witt_split_rows() -> list[dict]:
    """Return one 30-slot release plus a four-slot title variant with extra copies."""
    rows: list[dict] = []
    for track_number in range(1, 31):
        rows.append({
            "path": f"/music/Marcos Witt/25 Concierto Conmemorativo/{track_number:02d}.flac",
            "artist": "Marcos Witt",
            "album_artist": "Marcos Witt",
            "title": f"Song {track_number:02d}",
            "album": "25 Concierto Conmemorativo",
            "duration": 180 + track_number,
            "isrc": f"USAAA11{track_number:05d}",
            "track_number": track_number,
            "track_total": 30,
            "disc_number": 1,
            "disc_total": 1,
            "release_date": "2011",
        })
    for track_number in (2, 7, 14, 25):
        base = rows[track_number - 1]
        for extension in ("flac", "m4a"):
            rows.append({
                **base,
                "path": (
                    "/music/Marcos Witt/25 Concierto Conmemorativo (En Vivo)/"
                    f"{track_number:02d}.{extension}"
                ),
                "album": "25 Concierto Conmemorativo (En Vivo)",
            })
    return rows
