"""
content_scheduler.py — Daily content delivery scheduler.

For each patient whose (first_chat_at + N days) = today:
  - Finds active content materials matching their conditions
  - Logs a delivery entry in content_delivery_log (status=queued or no_material)

Run daily via cron:
    0 8 * * * /home/han/miniconda3/bin/python /mnt/ext/bare_NutriChatbot/scripts/content_scheduler.py

Usage:
    # Normal run (writes to DB)
    python scripts/content_scheduler.py

    # Dry run — prints who is due and what they'd receive, no DB writes
    python scripts/content_scheduler.py --dry-run

    # Run for a specific client only
    python scripts/content_scheduler.py --client-id 4

    # Simulate as if today were a specific date (for testing)
    python scripts/content_scheduler.py --dry-run --as-of 2026-06-01
"""
import argparse
import sys
import os
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_content import SCHEDULE_DAYS, conditions_to_groups


def run_scheduler(dry_run: bool = False, client_id: int = None, as_of: date = None):
    import database as db_module

    db_module.create_db_and_tables()
    session = db_module.SessionLocal()
    today = as_of or date.today()
    today_dt = datetime.combine(today, datetime.min.time())

    print(f"\n{'[DRY RUN] ' if dry_run else ''}NutriBot Content Scheduler — {today}")
    print(f"  Schedule days: {SCHEDULE_DAYS}\n")

    patients = db_module.get_all_patients_with_first_chat(session)
    if client_id:
        patients = [p for p in patients if p.client_id == client_id]

    if not patients:
        print("  No patients with first_chat_at set.")
        session.close()
        return

    queued = 0
    no_material = 0
    already_logged = 0

    for patient in patients:
        days_elapsed = (today - patient.first_chat_at.date()).days

        if days_elapsed not in SCHEDULE_DAYS:
            continue

        groups = conditions_to_groups(patient.conditions or [])
        print(f"  Patient {patient.id}: {patient.name} — Day {days_elapsed} — groups: {groups}")

        for group in groups:
            # Check if already logged for this patient + day + group today
            existing = session.query(db_module.ContentDeliveryLog).filter(
                db_module.ContentDeliveryLog.patient_id == patient.id,
                db_module.ContentDeliveryLog.day_offset == days_elapsed,
                db_module.ContentDeliveryLog.condition_group == group,
            ).first()

            if existing:
                print(f"    [{group}] already logged (status={existing.status}) — skip")
                already_logged += 1
                continue

            # Find active material for this group + day
            materials = db_module.get_active_materials_for_conditions(
                session, [group], days_elapsed
            )

            if materials:
                mat = materials[0]
                status = "queued"
                mat_id = mat.id
                print(f"    [{group}] QUEUED — material: {mat.title!r}")
                queued += 1
            else:
                status = "no_material"
                mat_id = None
                print(f"    [{group}] no active material yet — logged as no_material")
                no_material += 1

            if not dry_run:
                db_module.log_content_delivery(
                    session,
                    patient_id=patient.id,
                    day_offset=days_elapsed,
                    condition_group=group,
                    scheduled_date=today_dt,
                    material_id=mat_id,
                    status=status,
                )

    session.close()

    print(f"\nSummary: queued={queued}, no_material={no_material}, already_logged={already_logged}")
    if dry_run:
        print("(Dry run — nothing written to DB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NutriBot daily content delivery scheduler")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing to DB")
    parser.add_argument("--client-id", type=int, help="Limit to one client")
    parser.add_argument("--as-of", type=str, help="Simulate a specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    as_of = None
    if args.as_of:
        as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()

    run_scheduler(dry_run=args.dry_run, client_id=args.client_id, as_of=as_of)
