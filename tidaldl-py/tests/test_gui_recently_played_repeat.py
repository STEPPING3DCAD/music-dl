from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
from tests.gui_js_source import read_gui_js


def test_recently_played_cards_seed_queue_before_playback():
    source = read_gui_js()

    assert "function startPlaybackFromList(track, tracks)" in source
    assert "startPlaybackFromList(track, recentlyPlayed);" in source
