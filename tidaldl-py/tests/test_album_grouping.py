"""Deterministic local album-release grouping rubric."""

from copy import deepcopy

from tests.album_grouping_fixtures import marcos_witt_split_rows
from tidal_dl.helper.album_grouping import (
    GroupingAssessment,
    accepted_components,
    assess_pair,
    base_title,
    build_local_album_groups,
    canonical_title,
    card_id,
    decide_outcome,
    find_candidates,
    normalize_text,
    weak_evidence_sets,
)


def _row(path: str, *, album: str = "Album", title: str = "Song", track: int = 1, **values) -> dict:
    return {
        "path": path,
        "artist": "Artist",
        "album_artist": "Artist",
        "title": title,
        "album": album,
        "duration": 180,
        "isrc": None,
        "track_number": track,
        "track_total": 10,
        "disc_number": 1,
        "disc_total": 1,
        "release_date": "2020",
        **values,
    }


def _groups(rows: list[dict]):
    return {group.title: group for group in build_local_album_groups(rows)}


def test_candidate_normalization_retains_exact_titles_and_matches_trailing_markers():
    assert normalize_text("  Canción—VIVA  ") == "cancion viva"
    assert base_title("Album (En Vivo) [Remaster]") == "album"

    groups = _groups([
        _row("/a.flac", album="Álbum"),
        _row("/b.flac", album="Album (En Vivo)"),
    ])

    assert {group.title for group in groups.values()} == {"Álbum", "Album (En Vivo)"}
    assert len(find_candidates(list(groups.values()))) == 1


def test_exact_title_groups_keep_distinct_signatures_after_normalization():
    groups = build_local_album_groups([
        _row("/a.flac", album="Álbum"),
        _row("/b.flac", album="Album"),
    ])

    assert groups[0].signature != groups[1].signature


def test_album_artist_falls_back_only_to_one_common_track_artist():
    common = build_local_album_groups([
        {**_row("/a.flac"), "album_artist": None},
        {**_row("/b.flac", track=2), "album_artist": None},
    ])[0]
    mixed = build_local_album_groups([
        {**_row("/c.flac", album="Mixed"), "album_artist": None},
        {**_row("/d.flac", album="Mixed", track=2), "artist": "Other", "album_artist": None},
    ])[0]

    assert common.album_artist == "artist"
    assert mixed.album_artist is None


def test_isrc_overlap_candidate_requires_half_and_at_least_two_slots():
    left_rows = [_row(f"/left/{n}.flac", album="Left", track=n, isrc=f"USAAA20000{n:02d}") for n in range(1, 5)]
    right_rows = [
        _row(f"/right/{n}.flac", album="Unrelated", track=n, isrc=f"USAAA20000{n:02d}" if n < 3 else f"USBBB20000{n:02d}")
        for n in range(1, 5)
    ]

    assert len(find_candidates(build_local_album_groups(left_rows + right_rows))) == 1
    right_rows[1]["isrc"] = "USBBB2000099"
    assert find_candidates(build_local_album_groups(left_rows + right_rows)) == []


def test_marcos_fixture_collapses_duplicate_formats_into_four_partial_slots():
    groups = _groups(marcos_witt_split_rows())

    assert len(groups["25 Concierto Conmemorativo"].slots) == 30
    assert len(groups["25 Concierto Conmemorativo (En Vivo)"].slots) == 4


def test_recording_slots_are_deterministic_and_conflicting_isrc_is_noisy():
    rows = [
        _row("/z.m4a", duration=184, isrc="US-AAA-20-00001"),
        _row("/a.flac", duration=180, isrc="USBBB2000001"),
        _row("/other.flac", duration=190, isrc="USCCC2000001"),
    ]

    forward = build_local_album_groups(rows)[0]
    reverse = build_local_album_groups(list(reversed(rows)))[0]

    assert [slot.key for slot in forward.slots] == [slot.key for slot in reverse.slots]
    assert len(forward.slots) == 2
    assert forward.slots[0].isrcs == {"USAAA2000001", "USBBB2000001"}
    assert forward.slots[0].isrc is None


def test_scorer_matches_isrc_first_then_fallback_and_records_sources():
    left = build_local_album_groups([
        _row("/l1.flac", album="Album", track=1, title="One", isrc="USAAA2000001"),
        _row("/l2.flac", album="Album", track=2, title="Two", isrc=None),
    ])[0]
    right = build_local_album_groups([
        _row("/r1.flac", album="Album (Live)", track=1, title="One", isrc="USAAA2000001"),
        _row("/r2.flac", album="Album (Live)", track=2, title="Two", isrc=None, duration=183),
    ])[0]

    assessment = assess_pair(left, right)

    assert assessment.isrc_matches == 1
    assert assessment.fallback_matches == 1
    assert assessment.family_scores["recording"] == 32
    fallback = next(item for item in assessment.evidence if item.code == "fallback_recordings")
    assert fallback.sources == frozenset({"local_tags", "decoded_audio"})


def test_score_caps_and_clamps_to_100_with_independent_catalogs():
    groups = _groups([
        _row("/a.flac", album="Album", barcode="123", musicbrainz_release_group_id="rg"),
        _row("/b.flac", album="Album (Live)", barcode="123", musicbrainz_release_group_id="rg"),
    ])

    assessment = assess_pair(
        groups["Album"],
        groups["Album (Live)"],
        catalog_results={"tidal": {"same_release": True}, "musicbrainz": {"same_release": True}},
    )

    assert assessment.family_scores["identity"] == 100
    assert assessment.family_scores["catalog"] == 20
    assert assessment.diversity_bonus == 15
    assert assessment.score == 100


def test_thresholds_and_auto_gates_are_exact():
    assert decide_outcome(59) == "separate"
    assert decide_outcome(60) == "review"
    assert decide_outcome(84) == "review"
    assert decide_outcome(85, source_count=2, matched=3, coverage=0.9) == "auto_group"
    assert decide_outcome(85, source_count=1, matched=3, coverage=0.9) == "review"
    assert decide_outcome(95, direct_identity=True) == "auto_group"


def test_confirmed_different_release_ids_and_totals_veto_grouping():
    left_rows = [
        _row(f"/l{n}.flac", album="Album", track=n, musicbrainz_release_id="left", track_total=30)
        for n in range(1, 4)
    ]
    right_rows = [
        _row(f"/r{n}.flac", album="Album (Live)", track=n, musicbrainz_release_id="right", track_total=36)
        for n in range(1, 4)
    ]
    left, right = build_local_album_groups(left_rows + right_rows)

    assessment = assess_pair(left, right, user_decision="group_together")

    assert assessment.outcome == "separate"
    assert {veto.code for veto in assessment.vetoes} >= {"musicbrainz_release_conflict", "track_total_conflict"}
    assert assessment.user_decision_superseded is True


def test_confirmed_positioned_recording_conflict_is_a_veto():
    left = build_local_album_groups([
        _row("/l.flac", album="Album", isrc="USAAA2000001")
    ])[0]
    right = build_local_album_groups([
        _row("/r.flac", album="Album (Live)", isrc="USBBB2000001")
    ])[0]

    assessment = assess_pair(left, right)

    assert "positioned_recording_conflict" in {veto.code for veto in assessment.vetoes}
    assert assessment.outcome == "separate"


def test_user_decision_precedence_and_cover_only_boundary():
    left, right = build_local_album_groups([
        _row(
            "/a.flac", album="Alpha", title="One", artist="Left",
            album_artist=None, duration=None, track=None, track_total=None,
            disc_number=None, disc_total=None, release_date=None,
        ),
        _row(
            "/b.flac", album="Beta", title="Two", artist="Right",
            album_artist=None, duration=None, track=None, track_total=None,
            disc_number=None, disc_total=None, release_date=None,
        ),
    ])

    cover_only = assess_pair(left, right, artwork_digests=({"same"}, {"same"}))
    grouped = assess_pair(left, right, user_decision="group_together")
    separate = assess_pair(left, right, user_decision="keep_separate")

    assert cover_only.score == 3
    assert cover_only.outcome == "separate"
    assert grouped.outcome == "auto_group"
    assert separate.outcome == "separate"


def test_signatures_ignore_copy_format_isrc_and_duration_when_slot_set_is_stable():
    rows = [_row("/a.flac", duration=180, isrc="USAAA2000001")]
    original = build_local_album_groups(rows)[0]
    with_copy = build_local_album_groups(rows + [
        _row("/copy.m4a", duration=184, isrc="USBBB2000001", format="M4A")
    ])[0]
    duration_changed = build_local_album_groups([
        _row("/replacement.flac", duration=300, isrc=None)
    ])[0]
    identity_changed = build_local_album_groups([
        _row("/replacement.flac", title="Different", duration=300, isrc=None)
    ])[0]

    assert original.signature == with_copy.signature == duration_changed.signature
    assert identity_changed.signature != original.signature


def test_multi_group_components_require_every_pair_to_be_accepted():
    groups = build_local_album_groups([
        _row("/a.flac", album="A"),
        _row("/b.flac", album="B"),
        _row("/c.flac", album="C"),
    ])
    accepted = {}
    for left, right in ((groups[0], groups[1]), (groups[1], groups[2])):
        accepted[frozenset({left.signature, right.signature})] = GroupingAssessment(
            left.signature, right.signature, score=100, outcome="auto_group",
        )

    components, review = accepted_components(groups, accepted)

    assert [len(component) for component in components] == [1, 1, 1]
    assert review == {group.signature for group in groups}

    accepted[frozenset({groups[0].signature, groups[2].signature})] = GroupingAssessment(
        groups[0].signature, groups[2].signature, score=100, outcome="auto_group",
    )
    components, review = accepted_components(groups, accepted)
    assert [len(component) for component in components] == [3]
    assert review == set()


def test_card_id_and_canonical_title_are_deterministic():
    groups = build_local_album_groups([
        _row("/a.flac", album="Album", track_total=30),
        _row("/b.flac", album="Album (En Vivo)", track_total=None),
    ])

    assert card_id(groups) == card_id(list(reversed(groups)))
    assert card_id(groups).startswith("release:")
    assert canonical_title(groups) == "Album"
    assert canonical_title(groups, user_titles=["Album (En Vivo)"]) == "Album (En Vivo)"
    assert canonical_title(
        groups,
        catalog_titles=[
            {"source": "musicbrainz", "title": "ALBUM"},
            {"source": "tidal", "title": "Album"},
        ],
    ) == "Album"


def test_weak_evidence_sets_use_all_paths_and_are_order_independent():
    rows = [
        _row("/music/Album (Live)/b.flac"),
        _row("/music/Album/a.flac"),
    ]
    artwork = {rows[0]["path"]: b"two", rows[1]["path"]: b"one"}

    forward = weak_evidence_sets(rows, artwork.get)
    reverse = weak_evidence_sets(list(reversed(deepcopy(rows))), artwork.get)

    assert forward == reverse
    assert forward[1] == ("album",)
    assert len(forward[0]) == 2
