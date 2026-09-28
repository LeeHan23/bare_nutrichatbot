"""
One-time migration: add `id` (stable, 1-based) and `approved` fields to every
record in data/exercise_video_lookup.json, so the exercise catalog can be
reviewed/approved/edited via the docs-api /eka-review UI (Exercise Catalog
tab). Existing entries default to approved=true -- they're already live,
patient-facing content today; this migration only adds the bookkeeping
fields, it doesn't change what the bot serves. A future entry added by
re-running scripts/build_exercise_video_lookup.py would need this run again
(that script does a full overwrite -- see its docstring).

Idempotent: entries that already have both fields are left untouched.

Usage:
    python scripts/migrate_exercise_catalog_fields.py
"""
import json
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_PROJECT_ROOT, "data", "exercise_video_lookup.json")


def migrate() -> int:
    with open(_PATH, encoding="utf-8") as f:
        records = json.load(f)

    changed = 0
    for i, r in enumerate(records, start=1):
        if "id" not in r:
            r["id"] = i
            changed += 1
        if "approved" not in r:
            r["approved"] = True
            changed += 1

    if changed:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    return changed


if __name__ == "__main__":
    n = migrate()
    print(f"{'Migrated' if n else 'No changes needed'} — {n} field(s) added across the catalog.")
