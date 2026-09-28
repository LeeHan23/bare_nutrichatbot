"""
Review storage for the judge-calibration tool (eval_api.py) — sibling to
exercise_lookup.py's JSON + mtime-cache + atomic-write pattern. No DB: this
is small, low-write-volume team review data, not patient data.

Keyed by "{judge_key}:{case_id}" -> list of review dicts, so multiple team
members can review the same case without overwriting each other.
"""
import json
import os
from datetime import datetime, timezone

_STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "eval_calibration_reviews.json")

_cache = {"mtime": None, "data": {}}


def _load_fresh() -> dict:
    if not os.path.exists(_STORE_PATH):
        return {}
    with open(_STORE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_store() -> dict:
    try:
        mtime = os.path.getmtime(_STORE_PATH)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        _cache["data"] = _load_fresh()
        _cache["mtime"] = mtime
    return _cache["data"]


def _save_all(store: dict) -> None:
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp_path = _STORE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, _STORE_PATH)
    _cache["data"] = store
    _cache["mtime"] = os.path.getmtime(_STORE_PATH)


def all_reviews() -> dict:
    return dict(_get_store())


def add_review(judge_key: str, case_id: int, reviewer: str, verdict: str, agree, notes: str) -> dict:
    store = dict(_get_store())
    key = f"{judge_key}:{case_id}"
    review = {
        "reviewer": reviewer,
        "verdict": verdict,
        "agree": agree,
        "notes": notes,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    store[key] = store.get(key, []) + [review]
    _save_all(store)
    return review
