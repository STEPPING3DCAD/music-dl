"""Local album grouping API integration."""

import inspect
import time
from pathlib import Path

from tidal_dl.helper.library_db import LibraryDB


def _seed_pair(db: LibraryDB, *, provider_id: str | None = None) -> None:
    for album, suffix in (("Album", "a"), ("Album (Live)", "b")):
        for track in range(1, 5):
            db.record(
                f"/music/{suffix}{track}.flac",
                status="tagged",
                artist="Artist",
                album_artist="Artist",
                title=f"Song {track}",
                album=album,
                duration=180 + track,
                isrc=f"USAAA20{track:05d}",
                track_number=track,
                track_total=10,
                disc_number=1,
                disc_total=1,
                provider_namespace="tidal" if provider_id else None,
                provider_album_id=provider_id,
                art_available=False,
            )
    db.commit()


def test_direct_identity_returns_one_stable_release_card(tmp_path):
    from tidal_dl.gui.api.library import _album_cards

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_pair(db, provider_id="123")

    cards = _album_cards(db)

    assert len(cards) == 1
    assert cards[0]["id"].startswith("release:")
    assert cards[0]["members"] == ["Album", "Album (Live)"]
    assert cards[0]["track_count"] == 4
    assert cards[0]["possible_duplicate"] is False
    db.close()


def test_review_cards_expose_explainable_assessment(tmp_path):
    from tidal_dl.gui.api.library import _album_cards

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_pair(db)

    cards = _album_cards(db)

    assert len(cards) == 2
    assert all(card["possible_duplicate"] for card in cards)
    assessment = cards[0]["assessments"][0]
    assert assessment["score"] >= 60
    assert assessment["family_scores"]
    assert assessment["evidence"]
    db.close()


def test_grouping_decision_endpoint_validates_title_and_release_detail(client, tmp_path):
    from tidal_dl.gui.api import library as library_api

    db = LibraryDB(Path(tmp_path) / "library.db")
    db.open()
    _seed_pair(db)
    cards = library_api._album_cards(db)
    pair = cards[0]["assessments"][0]
    db.close()
    library_api._invalidate_db_cache()

    invalid = client.post(
        "/api/library/grouping/decision",
        headers=client._headers,
        json={
            "left_signature": pair["left_signature"],
            "right_signature": pair["right_signature"],
            "decision": "group_together",
            "canonical_title": "Not a member",
        },
    )
    assert invalid.status_code == 422

    accepted = client.post(
        "/api/library/grouping/decision",
        headers=client._headers,
        json={
            "left_signature": pair["left_signature"],
            "right_signature": pair["right_signature"],
            "decision": "group_together",
            "canonical_title": "Album",
        },
    )
    assert accepted.status_code == 200

    albums = client.get("/api/library/albums", headers=client._host_header).json()["albums"]
    assert len(albums) == 1
    detail = client.get(
        "/api/library/releases/" + albums[0]["id"].split(":", 1)[1] + "/tracks",
        headers=client._host_header,
    )
    assert detail.status_code == 200
    assert detail.json()["total"] == 4


def test_new_hard_veto_exposes_why_an_old_grouping_decision_was_superseded(tmp_path):
    from tidal_dl.gui.api.library import _album_cards

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    for album, release_id, total in (("Album", "left", 30), ("Album (Live)", "right", 36)):
        for track in range(1, 4):
            db.record(
                f"/{release_id}{track}.flac", status="tagged", artist="Artist",
                album_artist="Artist", title=f"Song {track}", album=album,
                duration=180, track_number=track, track_total=total,
                musicbrainz_release_id=release_id,
            )
    db.commit()
    pair = _album_cards(db)[0]["assessments"][0]
    assert db.set_grouping_decision(
        pair["left_signature"], pair["right_signature"],
        decision="group_together", canonical_title="Album",
    )
    db.commit()

    cards = _album_cards(db)

    assert all(card["possible_duplicate"] for card in cards)
    assessment = cards[0]["assessments"][0]
    assert assessment["user_decision_superseded"] is True
    assert {veto["code"] for veto in assessment["vetoes"]} >= {
        "musicbrainz_release_conflict", "track_total_conflict",
    }
    db.close()


def _seed_album(db: LibraryDB, *, artist: str, album: str, tracks: int, prefix: str) -> None:
    for track in range(1, tracks + 1):
        db.record(
            f"/music/{prefix}/{track}.flac",
            status="tagged",
            artist=artist,
            album_artist=artist,
            title=f"Song {track}",
            album=album,
            duration=180,
            track_number=track,
            track_total=tracks,
            disc_number=1,
            disc_total=1,
            art_available=False,
        )
    db.commit()


def _raise_if_whole_library():
    raise AssertionError("single-artist/release reads must not load the whole library")


def test_artist_albums_groups_only_that_artists_rows(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.helper import album_grouping

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    for index in range(40):
        _seed_album(
            db,
            artist=f"Unrelated {index}",
            album=f"Other Album {index}",
            tracks=3,
            prefix=f"other{index}",
        )
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    grouped_artists: list[set[str]] = []
    real_build = album_grouping.build_local_album_groups

    def spy_build(rows):
        grouped_artists.append({str(row.get("artist") or "") for row in rows})
        return real_build(rows)

    monkeypatch.setattr(album_grouping, "build_local_album_groups", spy_build)

    payload = library_api.artist_albums("Sandy, PAPO")

    assert payload["total"] == 1
    assert payload["albums"][0]["name"] == "Otra Vez"
    assert payload["albums"][0]["track_count"] == 9
    assert payload["albums"][0]["id"].startswith("release:")
    assert grouped_artists
    assert all(artists == {"Sandy, PAPO"} for artists in grouped_artists)
    db.close()


def test_release_tracks_and_unknown_release_do_not_group_unrelated_artists(
    tmp_path, monkeypatch,
):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.helper import album_grouping

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    for index in range(40):
        _seed_album(
            db,
            artist=f"Unrelated {index}",
            album=f"Other Album {index}",
            tracks=3,
            prefix=f"other{index}",
        )
    monkeypatch.setattr(library_api, "_get_db", lambda: db)

    grouped_artists: list[set[str]] = []
    real_build = album_grouping.build_local_album_groups

    def spy_build(rows):
        grouped_artists.append({str(row.get("artist") or "") for row in rows})
        return real_build(rows)

    monkeypatch.setattr(album_grouping, "build_local_album_groups", spy_build)

    albums = library_api.artist_albums("Sandy, PAPO")
    release_hash = albums["albums"][0]["id"].split(":", 1)[1]
    db.all_tracks = _raise_if_whole_library
    grouped_artists.clear()

    detail = library_api.release_tracks(release_hash)

    assert detail["total"] == 9
    assert detail["album"] == "Otra Vez"
    assert detail["id"] == "release:" + release_hash
    assert "cover_url" in detail
    assert grouped_artists
    assert all(artists == {"Sandy, PAPO"} for artists in grouped_artists)
    db.close()


def test_artist_album_tracks_groups_only_that_artists_rows(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.helper import album_grouping

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    _seed_album(db, artist="Unrelated", album="Other Album", tracks=3, prefix="other")
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    grouped_artists: list[set[str]] = []
    real_build = album_grouping.build_local_album_groups

    def spy_build(rows):
        grouped_artists.append({str(row.get("artist") or "") for row in rows})
        return real_build(rows)

    monkeypatch.setattr(album_grouping, "build_local_album_groups", spy_build)

    payload = library_api.artist_album_tracks("Sandy, PAPO", "Otra Vez")

    assert payload["total"] == 9
    assert grouped_artists
    assert all(artists == {"Sandy, PAPO"} for artists in grouped_artists)
    db.close()


def test_one_artist_and_release_reads_are_cheap_on_a_12k_row_library(tmp_path, monkeypatch):
    import time

    from tidal_dl.gui.api import library as library_api

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    assert db._conn
    db._conn.executemany(
        """INSERT INTO scanned (path, status, artist, title, album, album_artist,
                                duration, track_number, track_total, scanned_at)
           VALUES (?, 'tagged', ?, ?, ?, ?, 180, 1, 1, 0)""",
        [
            (
                f"/music/bulk/{index}.flac",
                f"Unrelated {index // 6}",
                f"Song {index}",
                f"Other Album {index // 6}",
                f"Unrelated {index // 6}",
            )
            for index in range(12_000)
        ],
    )
    db.commit()
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    started = time.perf_counter()
    albums = library_api.artist_albums("Sandy, PAPO")
    artist_ms = (time.perf_counter() - started) * 1000
    release_hash = albums["albums"][0]["id"].split(":", 1)[1]

    started = time.perf_counter()
    detail = library_api.release_tracks(release_hash)
    release_ms = (time.perf_counter() - started) * 1000

    assert albums["total"] == 1
    assert detail["total"] == 9
    assert artist_ms < 250
    assert release_ms < 250
    db.close()


def test_artist_scoped_cards_keep_full_library_release_ids(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.gui.api.library import _album_cards

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_pair(db, provider_id="123")
    _seed_album(db, artist="Unrelated", album="Other Album", tracks=2, prefix="other")
    monkeypatch.setattr(library_api, "_get_db", lambda: db)

    full_ids = {card["id"] for card in _album_cards(db)}
    payload = library_api.artist_albums("Artist")

    assert {album["id"] for album in payload["albums"]} <= full_ids
    assert payload["total"] == 1
    assert payload["albums"][0]["track_count"] == 4
    db.close()


def test_release_tracks_recovers_a_real_hash_when_stamps_are_missing(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.helper import album_grouping

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    _seed_album(db, artist="Unrelated", album="Other Album", tracks=3, prefix="other")
    monkeypatch.setattr(library_api, "_get_db", lambda: db)

    release_hash = library_api.artist_albums("Sandy, PAPO")["albums"][0]["id"].split(":", 1)[1]
    db.clear_release_ids()
    db.commit()
    assert db.tracks_for_release("release:" + release_hash) == []

    full_walks = {"count": 0}
    real_all_tracks = db.all_tracks

    def count_all_tracks():
        full_walks["count"] += 1
        return real_all_tracks()

    db.all_tracks = count_all_tracks
    grouped_artists: list[set[str]] = []
    real_build = album_grouping.build_local_album_groups

    def spy_build(rows):
        grouped_artists.append({str(row.get("artist") or "") for row in rows})
        return real_build(rows)

    monkeypatch.setattr(album_grouping, "build_local_album_groups", spy_build)

    detail = library_api.release_tracks(release_hash)

    assert detail["album"] == "Otra Vez"
    assert detail["total"] == 9
    assert detail["id"] == "release:" + release_hash
    assert full_walks["count"] == 1

    grouped_artists.clear()
    db.all_tracks = _raise_if_whole_library
    try:
        library_api.release_tracks("0" * 40)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("unknown release must 404")
    assert grouped_artists == []
    db.close()


def _seed_mac_like_library(db: LibraryDB, *, tracks: int = 11_974, albums: int = 1_565) -> None:
    """~12k-row / ~1.5k-album fixture matching the live Mac library shape."""
    assert db._conn
    tracks_per_album = 7
    bulk_albums = albums - 1
    rows = []
    scanned_at = 1_700_000_000
    for album_index in range(bulk_albums):
        artist = f"Artist {album_index // 80}"
        album = f"Album {album_index:04d}"
        album_time = scanned_at + album_index
        for track in range(1, tracks_per_album + 1):
            rows.append((
                f"/music/{artist}/{album}/{track:02d}.flac",
                "tagged",
                artist,
                f"Song {track}",
                album,
                artist,
                180,
                track,
                tracks_per_album,
                album_time,
            ))
    remainder = tracks - len(rows)
    for extra in range(max(remainder, 0)):
        rows.append((
            f"/music/pad/{extra}.flac",
            "tagged",
            "Pad Artist",
            f"Pad {extra}",
            "Pad Album",
            "Pad Artist",
            180,
            extra + 1,
            remainder,
            scanned_at,
        ))
    db._conn.executemany(
        """INSERT INTO scanned (path, status, artist, title, album, album_artist,
                                duration, track_number, track_total, scanned_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    db.commit()


def test_recent_albums_groups_only_the_page_not_the_whole_library(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.helper import album_grouping

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    assert db._conn
    db._conn.executemany(
        """INSERT INTO scanned (path, status, artist, title, album, album_artist,
                                duration, track_number, track_total, scanned_at)
           VALUES (?, 'tagged', ?, ?, ?, ?, 180, 1, 1, 0)""",
        [
            (
                f"/music/bulk/{index}.flac",
                f"Unrelated {index}",
                f"Song {index}",
                f"Other Album {index}",
                f"Unrelated {index}",
            )
            for index in range(80)
        ],
    )
    db.commit()
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    grouped_artists: list[set[str]] = []
    real_build = album_grouping.build_local_album_groups

    def spy_build(rows):
        grouped_artists.append({str(row.get("artist") or "") for row in rows})
        return real_build(rows)

    monkeypatch.setattr(album_grouping, "build_local_album_groups", spy_build)

    expected_id = library_api.artist_albums("Sandy, PAPO")["albums"][0]["id"]
    payload = library_api.library_recent_albums(limit=12, offset=0)
    sandy = next(album for album in payload["albums"] if album["name"] == "Otra Vez")

    assert sandy["id"] == expected_id
    assert payload["total"] >= 12
    assert grouped_artists
    assert all(len(artists) < 80 for artists in grouped_artists)
    db.close()


def test_recent_albums_does_not_expand_page_artists_or_use_art_subquery():
    from tidal_dl.gui.api.library import library_recent_albums
    from tidal_dl.helper.library_db.browse import BrowseMixin

    endpoint = inspect.getsource(library_recent_albums)
    page_sql = inspect.getsource(BrowseMixin.recent_albums_page)

    assert "tracks_for_albums" in endpoint
    assert "tracks_for_artist" not in endpoint
    assert "s2.art_available" not in page_sql
    assert "s2.album" not in page_sql


def test_recent_albums_first_page_is_cheap_on_a_12k_row_library(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_mac_like_library(db)
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    library_api.library_recent_albums(limit=50, offset=0)
    started = time.perf_counter()
    payload = library_api.library_recent_albums(limit=50, offset=0)
    warmed_ms = (time.perf_counter() - started) * 1000

    assert payload["limit"] == 50
    assert len(payload["albums"]) == 50
    assert payload["total"] >= 1_565
    assert all(album["id"].startswith("release:") for album in payload["albums"])
    assert all("cover_url" in album for album in payload["albums"])
    # Was 500–800ms on this fixture (correlated cover-art subquery) and ~3s
    # on the NAS-backed Mac library. After the slim page query: ~16ms for
    # limit=12 and ~36ms for the UI's limit=50. 250ms matches artist/release.
    assert warmed_ms < 250
    db.close()


def test_recent_albums_keeps_ids_flags_order_and_various_artists(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.gui.api.library import _album_cards
    from tidal_dl.helper import album_grouping

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_pair(db, provider_id="123")
    for track, artist in enumerate(("Comp A", "Comp B"), start=1):
        db.record(
            f"/music/comp/{track}.flac",
            status="tagged",
            artist=artist,
            album_artist="Various Artists",
            title=f"Comp Song {track}",
            album="Hits",
            duration=180,
            track_number=track,
            track_total=2,
        )
    assert db._conn
    db._conn.execute(
        "UPDATE scanned SET scanned_at = 9000000000 WHERE album = 'Hits'"
    )
    for index in range(40):
        _seed_album(
            db,
            artist="Artist",
            album=f"Back Catalog {index}",
            tracks=2,
            prefix=f"back{index}",
        )
    for index in range(20):
        _seed_album(
            db,
            artist="Zzz Filler",
            album=f"Filler {index}",
            tracks=1,
            prefix=f"filler{index}",
        )
    db._conn.execute(
        "UPDATE scanned SET scanned_at = 2 WHERE album LIKE 'Filler %'"
    )
    db._conn.execute(
        "UPDATE scanned SET scanned_at = 1 WHERE album LIKE 'Back Catalog %'"
    )
    db.commit()
    monkeypatch.setattr(library_api, "_get_db", lambda: db)

    full_ids = {card["id"] for card in _album_cards(db)}
    grouped_albums: list[set[str]] = []
    real_build = album_grouping.build_local_album_groups

    def spy_build(rows):
        grouped_albums.append({str(row.get("album") or "") for row in rows})
        return real_build(rows)

    monkeypatch.setattr(album_grouping, "build_local_album_groups", spy_build)

    payload = library_api.library_recent_albums(limit=12, offset=0)
    names = [album["name"] for album in payload["albums"]]
    by_name = {album["name"]: album for album in payload["albums"]}

    assert names[0] == "Hits"
    assert by_name["Hits"]["artist"] == "Various Artists"
    assert {album["id"] for album in payload["albums"]} <= full_ids
    assert "Album" in by_name
    assert by_name["Album"]["id"] in full_ids
    assert payload["total"] >= 12
    assert grouped_albums
    assert all(
        not any(title.startswith("Back Catalog") for title in albums)
        for albums in grouped_albums
    )
    db.close()


def _stamp_unique_album_release_ids(db: LibraryDB) -> None:
    """Pre-stamp one release id per album title without a full regroup."""
    assert db._conn
    albums = [
        row["album"]
        for row in db._conn.execute(
            "SELECT DISTINCT album FROM scanned "
            "WHERE album IS NOT NULL AND status != 'unreadable'"
        )
    ]
    db._conn.executemany(
        "UPDATE scanned SET release_id = ? WHERE album = ?",
        [(f"release:{index:040d}", album) for index, album in enumerate(albums)],
    )
    db.commit()


def test_all_albums_is_cheap_on_a_12k_row_library(tmp_path, monkeypatch):
    from tidal_dl.gui.api import library as library_api

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_mac_like_library(db)
    _stamp_unique_album_release_ids(db)
    assert db.release_stamps_complete()
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    started = time.perf_counter()
    payload = library_api.all_albums(q="")
    warmed_ms = (time.perf_counter() - started) * 1000

    assert payload["total"] >= 1_565
    assert len(payload["albums"]) >= 1_565
    assert all(album["id"].startswith("release:") for album in payload["albums"])
    assert all("cover_url" in album for album in payload["albums"])
    # Same <250ms budget as artist/release and warmed recent-albums.
    # Full regroup of this fixture is combinations(~1565, 2) and is too
    # slow for CI; stamps must be the gallery path.
    assert warmed_ms < 250
    db.close()


def test_all_albums_keeps_review_identity_various_artists_and_query(
    tmp_path, monkeypatch,
):
    from tidal_dl.gui.api import library as library_api
    from tidal_dl.gui.api.library import _album_cards

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_pair(db)
    for album, suffix in (("Identity", "ia"), ("Identity (Deluxe)", "ib")):
        for track in range(1, 5):
            db.record(
                f"/music/{suffix}{track}.flac",
                status="tagged",
                artist="Identity Artist",
                album_artist="Identity Artist",
                title=f"Song {track}",
                album=album,
                duration=180 + track,
                isrc=f"USBBB20{track:05d}",
                track_number=track,
                track_total=10,
                disc_number=1,
                disc_total=1,
                provider_namespace="tidal",
                provider_album_id="identity-1",
                art_available=False,
            )
    for track, artist in enumerate(("Comp A", "Comp B"), start=1):
        db.record(
            f"/music/comp/{track}.flac",
            status="tagged",
            artist=artist,
            album_artist="Various Artists",
            title=f"Comp Song {track}",
            album="Hits",
            duration=180,
            track_number=track,
            track_total=2,
        )
    db.commit()
    _album_cards(db)
    monkeypatch.setattr(library_api, "_get_db", lambda: db)
    db.all_tracks = _raise_if_whole_library

    payload = library_api.all_albums(q="")
    by_name = {album["name"]: album for album in payload["albums"]}
    review = [album for album in payload["albums"] if album["name"] in {"Album", "Album (Live)"}]
    identity = [
        album for album in payload["albums"]
        if album["name"] in {"Identity", "Identity (Deluxe)"}
        or "Identity" in album.get("members", [])
    ]

    assert len(review) == 2
    assert all(album["possible_duplicate"] for album in review)
    assert all(album["assessments"] for album in review)
    assert all(album["assessments"][0]["score"] >= 60 for album in review)
    assert len(identity) == 1
    assert identity[0]["possible_duplicate"] is False
    assert by_name["Hits"]["artist"] == "Various Artists"

    filtered = library_api.all_albums(q="Hits")
    assert filtered["total"] == 1
    assert filtered["albums"][0]["name"] == "Hits"
    assert library_api.all_albums(q="zzzz-no-match")["total"] == 0
    db.close()


def test_all_albums_does_not_regroup_whole_library_when_stamps_are_complete(
    tmp_path, monkeypatch,
):
    from tidal_dl.gui.api import library as library_api

    db = LibraryDB(tmp_path / "library.db")
    db.open()
    _seed_album(db, artist="Sandy, PAPO", album="Otra Vez", tracks=9, prefix="sandy")
    _stamp_unique_album_release_ids(db)
    monkeypatch.setattr(library_api, "_get_db", lambda: db)

    calls: list[object] = []
    real = library_api._album_cards

    def spy(db_arg, rows=None, **kwargs):
        calls.append(rows)
        return real(db_arg, rows, **kwargs)

    monkeypatch.setattr(library_api, "_album_cards", spy)

    payload = library_api.all_albums(q="")

    assert payload["total"] == 1
    assert all(rows is not None for rows in calls)
    db.close()
