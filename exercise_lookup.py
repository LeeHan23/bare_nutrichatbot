"""
Deterministic exercise-video lookup — sibling to image_handler.py's
IMAGE_ANNOTATIONS pattern. Backed by data/exercise_video_lookup.json (built
by scripts/build_exercise_video_lookup.py from the client's "Exercise Video
Intensity.xlsx"). No DB, no per-request xlsx parsing.

The YouTube link returned here must be attached to a chat response in code
(rag.py), never passed to the LLM to reproduce — see get_rag_response().

Every entry has `id` (stable, assigned by scripts/migrate_exercise_catalog_fields.py)
and `approved` (bool) — added so the docs-api /eka-review "Exercise Catalog"
tab can approve/unapprove/edit entries (including fixing a broken YouTube
link) without a code deploy. find_exercise_video()/list_exercise_samples_for_level()
(the live-bot-facing reads) skip any entry with approved=False.

Cached with an mtime check rather than loaded once at import: docs_api.py
(a separate process/service from the live bot) writes to this same JSON
file when a reviewer edits an entry, and the live bot process needs to see
that edit without a restart. A stat() per call is cheap; the file is only
re-parsed when it actually changed.
"""
import json
import os
import re

_LOOKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exercise_video_lookup.json")

_cache = {"mtime": None, "data": []}


def _load_fresh() -> list[dict]:
    if not os.path.exists(_LOOKUP_PATH):
        return []
    with open(_LOOKUP_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_videos() -> list[dict]:
    try:
        mtime = os.path.getmtime(_LOOKUP_PATH)
    except OSError:
        return []
    if _cache["mtime"] != mtime:
        _cache["data"] = _load_fresh()
        _cache["mtime"] = mtime
    return _cache["data"]


# Static snapshot at import time — kept for existing direct importers (e.g.
# scripts/test_exercise_lookup.py's truthy check). Not live; internal reads
# below use _get_videos() instead.
EXERCISE_VIDEOS = _get_videos()


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
    videos = _get_videos()
    if not videos or not personalization_level:
        return None

    for r in videos:
        if r.get("approved") is False:
            continue
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
    videos = _get_videos()
    if not videos or not personalization_level:
        return []
    seen_per_type: dict[str, int] = {}
    out = []
    for r in videos:
        if r.get("approved") is False:
            continue
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


# ---------------------------------------------------------------------------
# Review/edit CRUD — used by docs_api.py's /eka-review "Exercise Catalog" tab.
# Unlike find_exercise_video()/list_exercise_samples_for_level() above, these
# are not level-filtered or approval-filtered — the review UI needs to see
# and act on every entry, approved or not.
# ---------------------------------------------------------------------------

_EDITABLE_FIELDS = {
    "type", "exercise_title", "explanation", "intensity_tier", "min_loop",
    "max_loop", "total_duration", "allowed_level", "body_focus",
    "suitable_for", "youtube_link", "video_duration",
}


def list_all() -> list[dict]:
    """Full catalog, including id/approved, for the review UI."""
    return list(_get_videos())


def get_by_id(entry_id: int) -> dict | None:
    for r in _get_videos():
        if r.get("id") == entry_id:
            return r
    return None


def create_entry(fields: dict, approved: bool = False) -> dict:
    """Add a brand-new catalog entry (the review UI's "Add Exercise" action).
    Defaults to approved=False — unlike the original 199 rows (migrated as
    already-live, see scripts/migrate_exercise_catalog_fields.py), a
    manually-added entry hasn't been reviewed yet, so it stays out of
    find_exercise_video()/list_exercise_samples_for_level() until someone
    explicitly approves it.
    """
    entries = list(_get_videos())
    new_id = max((r.get("id", 0) for r in entries), default=0) + 1
    entry = {k: fields.get(k) for k in _EDITABLE_FIELDS}
    entry["id"] = new_id
    entry["approved"] = approved
    entries.append(entry)
    _save_all(entries)
    return entry


def _save_all(entries: list[dict]) -> None:
    """Atomic write (temp file + os.replace) so a concurrent read from the
    live bot process never sees a half-written file."""
    tmp_path = _LOOKUP_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, _LOOKUP_PATH)
    _cache["data"] = entries
    _cache["mtime"] = os.path.getmtime(_LOOKUP_PATH)


def update_entry(entry_id: int, updates: dict) -> dict:
    """Apply `updates` (only _EDITABLE_FIELDS keys are honoured — id/approved
    are managed separately via set_approved()) to one entry and persist."""
    entries = list(_get_videos())
    for r in entries:
        if r.get("id") == entry_id:
            r.update({k: v for k, v in updates.items() if k in _EDITABLE_FIELDS})
            _save_all(entries)
            return r
    raise KeyError(f"No exercise catalog entry with id={entry_id}")


def set_approved(entry_id: int, approved: bool) -> dict:
    entries = list(_get_videos())
    for r in entries:
        if r.get("id") == entry_id:
            r["approved"] = approved
            _save_all(entries)
            return r
    raise KeyError(f"No exercise catalog entry with id={entry_id}")


def approve_all() -> int:
    """Approve every currently-unapproved entry. Returns how many changed."""
    entries = list(_get_videos())
    count = 0
    for r in entries:
        if not r.get("approved"):
            r["approved"] = True
            count += 1
    if count:
        _save_all(entries)
    return count
