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
