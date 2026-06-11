"""
weekly_eka_scheduler.py — Cron entry point for weekly E/K/A content generation.

Runs every Monday at 06:00 via cron:
    0 6 * * 1 /home/han/miniconda3/bin/python /mnt/ext/bare_NutriChatbot/scripts/weekly_eka_scheduler.py

What it does each Monday:
  1. Deletes expired EKA materials (expires_at < now, set to created_at + 14 days)
     → materials generated 2 weeks ago are removed on this run
  2. Checks if content for THIS week already exists (idempotent — won't regenerate unless --force)
  3. Generates all 21 E/K/A items (7 groups × 3 types, 4-week topic rotation)
  4. Saves to DB (is_active=False pending admin review)
  5. Exports Excel to materials/ for the design team

Expiry lifecycle example:
  Mon week 22: cleanup (nothing old) → generate week 22 (expires_at = +14 days = end of week 23)
  Mon week 23: cleanup (nothing old yet) → generate week 23
  Mon week 24: cleanup DELETES week 22 (expires_at passed) → generate week 24

Usage:
    python scripts/weekly_eka_scheduler.py
    python scripts/weekly_eka_scheduler.py --dry-run
    python scripts/weekly_eka_scheduler.py --force        # overwrite existing rows
    python scripts/weekly_eka_scheduler.py --week 22      # generate for specific week
"""
import argparse, sys, os
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _week_already_generated(iso_week: int) -> bool:
    """Return True if at least one EKA material exists for this week (not yet expired)."""
    import database as db_module
    session = db_module.SessionLocal()
    try:
        count = session.query(db_module.ContentMaterial).filter(
            db_module.ContentMaterial.week_number == iso_week,
            db_module.ContentMaterial.content_type.isnot(None),
        ).count()
        return count > 0
    finally:
        session.close()


def _cleanup(dry_run: bool) -> int:
    """Delete expired EKA materials. Returns count of deleted rows."""
    import database as db_module
    session = db_module.SessionLocal()
    try:
        if dry_run:
            count = session.query(db_module.ContentMaterial).filter(
                db_module.ContentMaterial.content_type.isnot(None),
                db_module.ContentMaterial.expires_at.isnot(None),
                db_module.ContentMaterial.expires_at < datetime.utcnow(),
            ).count()
            return count
        return db_module.cleanup_expired_eka_materials(session)
    finally:
        session.close()


def run(dry_run: bool = False, force: bool = False, iso_week: int = None, client_id: int = 4):
    if iso_week is None:
        iso_week = date.today().isocalendar()[1]

    print(f"\nNutriBot Weekly EKA Scheduler — {date.today()}  (ISO week {iso_week})")

    # Step 1: cleanup expired materials
    expired_count = _cleanup(dry_run)
    if expired_count:
        tag = "[DRY RUN] Would delete" if dry_run else "Deleted"
        print(f"  {tag} {expired_count} expired EKA material(s) from previous weeks")
    else:
        print("  No expired materials to clean up")

    # Step 2: idempotency check
    if not force and not dry_run and _week_already_generated(iso_week):
        print(f"  Week {iso_week} content already exists — skipping. Use --force to regenerate.")
        return

    # Step 3: generate
    from generate_weekly_eka import generate_weekly_eka
    generate_weekly_eka(
        iso_week=iso_week,
        client_id=client_id,
        dry_run=dry_run,
        force=force,
    )

    if not dry_run:
        print(f"\nScheduler done. Materials saved to DB (is_active=False, expires in 14 days).")
        print(f"Approve via: POST /content/materials/{{id}}/approve  (X-Admin-Password required)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weekly EKA content scheduler")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--force",     action="store_true", help="Overwrite existing rows")
    parser.add_argument("--week",      type=int, help="ISO week number (default: current)")
    parser.add_argument("--client-id", type=int, default=4)
    args = parser.parse_args()

    run(dry_run=args.dry_run, force=args.force, iso_week=args.week, client_id=args.client_id)
