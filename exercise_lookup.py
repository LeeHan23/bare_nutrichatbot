"""
Deterministic exercise-video lookup — sibling to image_handler.py's
IMAGE_ANNOTATIONS pattern. Loaded once from data/exercise_video_lookup.json
(built by scripts/build_exercise_video_lookup.py from the client's
"Exercise Video Intensity.xlsx"). No DB, no per-request xlsx parsing.

The YouTube link returned here must be attached to a chat response in code
(rag.py), never passed to the LLM to reproduce — see get_rag_response().
"""
import json
import os
import re

_LOOKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exercise_video_lookup.json")


def _load() -> list[dict]:
    if not os.path.exists(_LOOKUP_PATH):
        return []
    with open(_LOOKUP_PATH, encoding="utf-8") as f:
        return json.load(f)


EXERCISE_VIDEOS = _load()


def _parse_allowed_levels(allowed_level: str | None) -> set[str]:
    """'L2–L0' -> {'L0','L1','L2'}; 'L0 sahaja' -> {'L0'}."""
    if not allowed_level:
        return set()
    nums = [int(n) for n in re.findall(r"L(\d)", allowed_level)]
    if not nums:
        return set()
    return {f"L{i}" for i in range(min(nums), max(nums) + 1)}


def find_exercise_video(
    personalization_level: str | None,
    intensity_hint: str | None = None,
    body_focus_hint: str | None = None,
) -> dict | None:
    """Deterministic filter — no fuzzy scoring. Returns the first matching
    record's public fields, or None if nothing matches (e.g. personalization
    level unset — err on returning nothing rather than an unfiltered video).
    """
    if not EXERCISE_VIDEOS or not personalization_level:
        return None

    for r in EXERCISE_VIDEOS:
        if personalization_level not in _parse_allowed_levels(r.get("allowed_level")):
            continue
        if intensity_hint and (r.get("intensity_tier") or "").lower() != intensity_hint.lower():
            continue
        if body_focus_hint and body_focus_hint.lower() not in (r.get("body_focus") or "").lower():
            continue
        return {
            "title": r.get("exercise_title"),
            "type": r.get("type"),
            "youtube_url": r.get("youtube_link"),
            "intensity_tier": r.get("intensity_tier"),
            "allowed_level": r.get("allowed_level"),
            "body_focus": r.get("body_focus"),
            "video_duration": r.get("video_duration"),
        }
    return None


def list_exercise_samples_for_level(
    personalization_level: str | None, per_type: int = 3
) -> list[dict]:
    """Grounded, level-filtered sample of the catalog (a few per exercise
    type) for general exercise Q&A context — e.g. "what exercise should I
    do", not just literal video requests. No youtube_link included; the
    deterministic citation path (find_exercise_video) stays the only place
    a link is ever surfaced. Capped per type since the full catalog can be
    ~150+ rows for a given level — too large for a prompt.
    """
    if not EXERCISE_VIDEOS or not personalization_level:
        return []
    seen_per_type: dict[str, int] = {}
    out = []
    for r in EXERCISE_VIDEOS:
        if personalization_level not in _parse_allowed_levels(r.get("allowed_level")):
            continue
        exercise_type = r.get("type") or "Other"
        if seen_per_type.get(exercise_type, 0) >= per_type:
            continue
        seen_per_type[exercise_type] = seen_per_type.get(exercise_type, 0) + 1
        out.append({
            "title": r.get("exercise_title"),
            "type": exercise_type,
            "intensity_tier": r.get("intensity_tier"),
            "body_focus": r.get("body_focus"),
            "video_duration": r.get("video_duration"),
        })
    return out
