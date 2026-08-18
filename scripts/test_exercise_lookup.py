"""
Smoke test for exercise_lookup.py — run after
scripts/build_exercise_video_lookup.py has produced data/exercise_video_lookup.json.

    python scripts/test_exercise_lookup.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exercise_lookup import _parse_allowed_levels, find_exercise_video, EXERCISE_VIDEOS


def test_parse_allowed_levels():
    assert _parse_allowed_levels("L2–L0") == {"L0", "L1", "L2"}
    assert _parse_allowed_levels("L0 sahaja") == {"L0"}
    assert _parse_allowed_levels("L1–L0") == {"L0", "L1"}
    assert _parse_allowed_levels(None) == set()
    assert _parse_allowed_levels("") == set()
    print("test_parse_allowed_levels: OK")


def test_find_exercise_video():
    assert EXERCISE_VIDEOS, "data/exercise_video_lookup.json missing/empty — run scripts/build_exercise_video_lookup.py first"

    # L3 (highest risk) should never get a Vigorous-only ("L0 sahaja") video
    result = find_exercise_video("L3")
    if result:
        assert "L3" in _parse_allowed_levels(result["allowed_level"])

    # No personalization_level -> no video (fail closed, not unfiltered)
    assert find_exercise_video(None) is None

    # A real video for L0 should exist and carry a real youtube.com/youtu.be link
    result = find_exercise_video("L0")
    assert result is not None
    assert result["youtube_url"] and ("youtu" in result["youtube_url"])

    # Intensity filter narrows correctly
    result = find_exercise_video("L0", intensity_hint="Light")
    assert result is not None
    assert result["intensity_tier"].lower() == "light"

    print("test_find_exercise_video: OK")


if __name__ == "__main__":
    test_parse_allowed_levels()
    test_find_exercise_video()
    print("All exercise-lookup smoke tests passed.")
