"""Local album grouping API integration."""

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
    from fastapi import HTTPException
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
    assert grouped_artists
    assert all(artists == {"Sandy, PAPO"} for artists in grouped_artists)

    grouped_artists.clear()
    try:
        library_api.release_tracks("0" * 40)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("unknown release must 404")
    assert grouped_artists == []
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

    from fastapi import HTTPException
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

    started = time.perf_counter()
    try:
        library_api.release_tracks("0" * 40)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("unknown release must 404")
    missing_ms = (time.perf_counter() - started) * 1000

    assert albums["total"] == 1
    assert detail["total"] == 9
    assert artist_ms < 250
    assert release_ms < 250
    assert missing_ms < 50
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
