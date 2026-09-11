"""
backfill_legacy_eka_levels.py — Tag pre-existing content_materials rows (from
before the L0-L3/OB-track generation change) with a personalization_level,
using the same _GROUP_LEVEL per-condition-group mapping the generator already
uses for exercise-catalog sampling.

These are single generic rows, not per-level variants — regenerating them
would orphan existing review_notes/is_active state, so this backfills the tag
in place instead. Only touches rows where BOTH personalization_level and
onboarding_stage are NULL (never overwrites an already-tagged L-track/OB-track
row from the new generator).

Usage:
    /home/han/Desktop/projects/bare_NutriChatbot/.venv/bin/python scripts/backfill_legacy_eka_levels.py
    /home/han/Desktop/projects/bare_NutriChatbot/.venv/bin/python scripts/backfill_legacy_eka_levels.py --dry-run
"""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
from scripts.generate_weekly_eka import _GROUP_LEVEL


def backfill(dry_run: bool = False):
    session = db.SessionLocal()
    try:
        rows = (
            session.query(db.ContentMaterial)
            .filter(
                db.ContentMaterial.personalization_level.is_(None),
                db.ContentMaterial.onboarding_stage.is_(None),
            )
            .all()
        )
        print(f"Found {len(rows)} untagged legacy rows.")
        unmapped = sorted({r.condition_group for r in rows} - set(_GROUP_LEVEL))
        if unmapped:
            print(f"WARNING: no _GROUP_LEVEL entry for: {unmapped} — these rows will be skipped.")

        tagged = 0
        for r in rows:
            level = _GROUP_LEVEL.get(r.condition_group)
            if not level:
                continue
            print(f"  id={r.id} week={r.week_number} {r.condition_group}/{r.content_type} -> {level}")
            if not dry_run:
                r.personalization_level = level
            tagged += 1

        if not dry_run:
            session.commit()
        print(f"\n{'[DRY RUN] Would tag' if dry_run else 'Tagged'} {tagged}/{len(rows)} rows.")
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill personalization_level onto legacy content_materials rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
