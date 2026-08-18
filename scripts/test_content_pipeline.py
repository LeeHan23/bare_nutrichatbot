"""
test_content_pipeline.py — Smoke tests for the content generation pipeline.

Tests:
  1. Migration check — content_materials, content_delivery_log, first_chat_at exist
  2. first_chat_at tracking — set_first_chat_at is idempotent (second call is a no-op)
  3. Content generation — General group, Day 3 (dry run, no DB writes)
  4. Scheduler dry run — prints due patients and materials, no DB writes
  5. EKA migration check — content_type and week_number columns exist (columns are kept and
     reused by the taxonomy-driven pipeline even though the LLM-hallucinated weekly
     generate_weekly_eka.py/weekly_eka_scheduler.py itself was retired — see
     docs/component_taxonomy_contract.md)
  6. EKA upsert idempotency — upsert_eka_material skips duplicate (group/type/week/topic)
  7. EKA expiry and cleanup — expires_at set on insert; cleanup_expired_eka_materials deletes only expired
  8. Content API DB layer — get_materials_by_filters and get_weekly_feed_for_conditions work

Usage:
    # Run all tests
    python scripts/test_content_pipeline.py

    # Run only EKA tests
    python scripts/test_content_pipeline.py --test eka_migration
    python scripts/test_content_pipeline.py --test eka_idempotency
    python scripts/test_content_pipeline.py --test eka_api_db

    # Seed demo patients with first_chat_at dates for scheduler test
    python scripts/test_content_pipeline.py --seed-dates

    # Clear first_chat_at from all demo patients (reset)
    python scripts/test_content_pipeline.py --reset-dates

    # Run a single original test by name
    python scripts/test_content_pipeline.py --test migration
    python scripts/test_content_pipeline.py --test first_chat
    python scripts/test_content_pipeline.py --test generation
    python scripts/test_content_pipeline.py --test scheduler
"""
import sys
import os
import argparse
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db_module
from generate_content import SCHEDULE_DAYS

# Demo patients: (username, target_day_offset)
# Spread across schedule days so scheduler test finds at least one due patient
TEST_PATIENTS = [
    ("ahmad.fadzillah",   3),
    ("lim.siewching",     5),
    ("kavitha.subra",     7),
    ("hafizuddin.salleh", 14),
    ("tan.weiloong",      21),
    ("nuraini.zulkifli",  3),
    ("sitihajar.mnasir",  5),
    ("rajendran.muthu",   7),
]

PASS = "PASS"
FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session():
    db_module.create_db_and_tables()
    return db_module.SessionLocal()


def _print_result(name: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


# ---------------------------------------------------------------------------
# Seed / reset helpers
# ---------------------------------------------------------------------------

def seed_dates():
    """Set first_chat_at on demo patients so scheduler sees them as due today."""
    session = _get_session()
    today = date.today()
    seeded = 0
    for username, day_offset in TEST_PATIENTS:
        patient = session.query(db_module.Patient).filter_by(username=username).first()
        if not patient:
            print(f"  SKIP {username} (not found)")
            continue
        target_date = today - timedelta(days=day_offset)
        patient.first_chat_at = datetime.combine(target_date, datetime.min.time())
        seeded += 1
    session.commit()
    session.close()
    print(f"Seeded first_chat_at for {seeded} patients (offsets: {[d for _, d in TEST_PATIENTS]})")


def reset_dates():
    """Clear first_chat_at from all demo patients."""
    session = _get_session()
    cleared = 0
    for username, _ in TEST_PATIENTS:
        patient = session.query(db_module.Patient).filter_by(username=username).first()
        if not patient:
            continue
        patient.first_chat_at = None
        cleared += 1
    session.commit()
    session.close()
    print(f"Cleared first_chat_at from {cleared} patients.")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_migration():
    """Verify content_materials, content_delivery_log, and first_chat_at exist."""
    print("\n[1] Migration check")
    from sqlalchemy import inspect
    inspector = inspect(db_module.engine)
    tables = inspector.get_table_names()

    ok1 = _print_result("content_materials table", "content_materials" in tables)
    ok2 = _print_result("content_delivery_log table", "content_delivery_log" in tables)

    patient_cols = {c["name"] for c in inspector.get_columns("patients")}
    ok3 = _print_result("patients.first_chat_at column", "first_chat_at" in patient_cols)

    return ok1 and ok2 and ok3


def test_first_chat_at():
    """set_first_chat_at sets the timestamp once and ignores subsequent calls."""
    print("\n[2] first_chat_at idempotency")
    session = _get_session()

    patient = None
    for username, _ in TEST_PATIENTS:
        patient = session.query(db_module.Patient).filter_by(username=username).first()
        if patient:
            break

    if not patient:
        session.close()
        return _print_result("find demo patient", False, "no demo patients found — run seed_patients.py")

    original_value = patient.first_chat_at

    db_module.set_first_chat_at(session, patient.id)
    session.refresh(patient)
    first_set = patient.first_chat_at
    ok1 = _print_result("first call sets first_chat_at", first_set is not None)

    import time; time.sleep(1)
    db_module.set_first_chat_at(session, patient.id)
    session.refresh(patient)
    ok2 = _print_result("second call is no-op", patient.first_chat_at == first_set,
                        f"before={first_set}, after={patient.first_chat_at}")

    patient.first_chat_at = original_value
    session.commit()
    session.close()

    return ok1 and ok2


def test_generation():
    """
    Dry-run: verifies niche lookup and scheduling logic without calling Ollama.
    Pass --live to actually call Ollama and verify tips are returned.
    """
    live = os.environ.get("NUTRIBOT_TEST_LIVE") == "1"
    label = "Content generation — General / Day 3" + (" (live)" if live else " (dry run)")
    print(f"\n[3] {label}")
    try:
        from generate_content import generate_content
        results = generate_content(
            client_id=4,
            filter_group="General",
            filter_day=3,
            dry_run=not live,
            no_db=True,
            output_dir=None,
        )
        ok1 = _print_result("niche found for General / Day 3", len(results) > 0,
                            f"{len(results)} niche(s)")
        if live and results:
            tips = results[0].get("tips", [])
            ok2 = _print_result("tips generated", len(tips) > 0, f"{len(tips)} tips")
            return ok1 and ok2
        return ok1
    except Exception as e:
        return _print_result("generate_content", False, str(e))


def test_scheduler():
    """Dry-run the scheduler for today and verify it finds at least one due patient."""
    print("\n[4] Scheduler dry run")

    session = _get_session()
    patients_with_dates = db_module.get_all_patients_with_first_chat(session)
    session.close()

    if not patients_with_dates:
        print("  NOTE: No patients have first_chat_at set.")
        print("        Run: python scripts/test_content_pipeline.py --seed-dates")
        print("        Then re-run this test.")
        return _print_result("patients with first_chat_at", False, "none found — seed first")

    today = date.today()
    due = [
        p for p in patients_with_dates
        if (today - p.first_chat_at.date()).days in SCHEDULE_DAYS
    ]
    ok1 = _print_result("at least one patient due today", len(due) > 0,
                        f"{len(due)} due out of {len(patients_with_dates)} with dates")

    try:
        from content_scheduler import run_scheduler
        run_scheduler(dry_run=True)
        ok2 = _print_result("scheduler ran without errors", True)
    except Exception as e:
        ok2 = _print_result("scheduler ran without errors", False, str(e))

    return ok1 and ok2


# ---------------------------------------------------------------------------
# EKA tests
# ---------------------------------------------------------------------------

def test_eka_migration():
    """Verify content_type and week_number columns were added to content_materials."""
    print("\n[5] EKA migration check")
    from sqlalchemy import inspect
    inspector = inspect(db_module.engine)
    cols = {c["name"] for c in inspector.get_columns("content_materials")}
    ok1 = _print_result("content_type column", "content_type" in cols)
    ok2 = _print_result("week_number column", "week_number" in cols)
    return ok1 and ok2


def test_eka_idempotency():
    """upsert_eka_material skips duplicate rows; force=True overwrites."""
    print("\n[6] EKA upsert idempotency")
    session = _get_session()
    TEST_WEEK = 999  # sentinel week that won't clash with real data

    try:
        mat1 = db_module.upsert_eka_material(
            session,
            condition_group="General",
            condition_tags=[],
            content_type="K",
            week_number=TEST_WEEK,
            topic="test_idempotency_topic",
            title="Test Title v1",
            raw_content={"test": "v1"},
        )
        ok1 = _print_result("first insert created row", mat1.id is not None)

        mat2 = db_module.upsert_eka_material(
            session,
            condition_group="General",
            condition_tags=[],
            content_type="K",
            week_number=TEST_WEEK,
            topic="test_idempotency_topic",
            title="Test Title v2",
            raw_content={"test": "v2"},
        )
        ok2 = _print_result("second insert returns same row (no dup)", mat1.id == mat2.id,
                            f"id1={mat1.id} id2={mat2.id}")
        ok3 = _print_result("second insert did not overwrite content",
                            mat2.raw_tips.get("test") == "v1",
                            f"raw_tips={mat2.raw_tips}")

        mat3 = db_module.upsert_eka_material(
            session,
            condition_group="General",
            condition_tags=[],
            content_type="K",
            week_number=TEST_WEEK,
            topic="test_idempotency_topic",
            title="Test Title v3",
            raw_content={"test": "v3"},
            force=True,
        )
        ok4 = _print_result("force=True overwrites content",
                            mat3.raw_tips.get("test") == "v3",
                            f"raw_tips={mat3.raw_tips}")

        # Cleanup sentinel row
        session.delete(session.query(db_module.ContentMaterial).get(mat1.id))
        session.commit()

        return ok1 and ok2 and ok3 and ok4
    except Exception as e:
        return _print_result("upsert_eka_material", False, str(e))
    finally:
        session.close()


def test_eka_expiry():
    """expires_at is set on insert; cleanup_expired_eka_materials deletes only expired rows."""
    print("\n[7] EKA expiry and cleanup")
    from datetime import datetime, timedelta
    session = _get_session()
    TEST_WEEK = 997

    try:
        # Insert one row that expires in the past, one in the future
        now = datetime.utcnow()
        mat_old = db_module.ContentMaterial(
            condition_group="General", condition_tags=[], content_type="K",
            week_number=TEST_WEEK, day_offset=None, topic="expiry_old",
            title="Expired", raw_tips={}, is_active=False,
            created_at=now - timedelta(days=20),
            expires_at=now - timedelta(days=6),  # already expired
        )
        mat_fresh = db_module.ContentMaterial(
            condition_group="General", condition_tags=[], content_type="E",
            week_number=TEST_WEEK, day_offset=None, topic="expiry_fresh",
            title="Fresh", raw_tips={}, is_active=False,
            created_at=now,
            expires_at=now + timedelta(days=10),  # not yet expired
        )
        session.add(mat_old)
        session.add(mat_fresh)
        session.commit()

        ok1 = _print_result("both rows inserted", True)

        # upsert_eka_material sets expires_at automatically
        mat_auto = db_module.upsert_eka_material(
            session, "General", [], "A", TEST_WEEK, "expiry_auto",
            "Auto Expiry Test", {"auto": True}
        )
        ok2 = _print_result(
            "upsert_eka_material sets expires_at",
            mat_auto.expires_at is not None and mat_auto.expires_at > now,
            f"expires_at={mat_auto.expires_at}",
        )
        expected_expiry = now + timedelta(days=db_module.EKA_EXPIRY_DAYS)
        delta = abs((mat_auto.expires_at - expected_expiry).total_seconds())
        ok3 = _print_result(
            f"expires_at = created_at + {db_module.EKA_EXPIRY_DAYS} days",
            delta < 5,
            f"delta={delta:.1f}s",
        )

        # cleanup_expired_eka_materials deletes only the expired row
        deleted = db_module.cleanup_expired_eka_materials(session)
        ok4 = _print_result("cleanup deleted 1 expired row", deleted == 1, f"deleted={deleted}")

        remaining = session.query(db_module.ContentMaterial).filter(
            db_module.ContentMaterial.week_number == TEST_WEEK
        ).count()
        ok5 = _print_result("2 non-expired rows remain (fresh + auto)", remaining == 2,
                            f"remaining={remaining}")

        # get_materials_by_filters excludes expired by default
        visible = db_module.get_materials_by_filters(session, week_number=TEST_WEEK)
        ok6 = _print_result("get_materials_by_filters hides expired by default",
                            len(visible) == 2, f"visible={len(visible)}")

        return ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    except Exception as e:
        return _print_result("EKA expiry test", False, str(e))
    finally:
        try:
            for row in session.query(db_module.ContentMaterial).filter(
                db_module.ContentMaterial.week_number == TEST_WEEK
            ).all():
                session.delete(row)
            session.commit()
        except Exception:
            pass
        session.close()


def test_eka_api_db():
    """get_materials_by_filters and get_weekly_feed_for_conditions return correct results."""
    print("\n[8] Content API DB layer")
    session = _get_session()
    TEST_WEEK = 998

    try:
        # Seed two test rows
        m_e = db_module.upsert_eka_material(session, "T2DM", ["Type 2 Diabetes"],
                                             "E", TEST_WEEK, "api_test_e", "API Test E",
                                             {"exercise_type": "aerobic"})
        m_k = db_module.upsert_eka_material(session, "T2DM", ["Type 2 Diabetes"],
                                             "K", TEST_WEEK, "api_test_k", "API Test K",
                                             {"topic_summary": "test"})
        m_k.is_active = True
        session.commit()

        # Test get_materials_by_filters
        all_mats = db_module.get_materials_by_filters(session, week_number=TEST_WEEK)
        ok1 = _print_result("get_materials_by_filters: week filter returns 2",
                            len(all_mats) == 2, f"got {len(all_mats)}")

        type_filter = db_module.get_materials_by_filters(session, week_number=TEST_WEEK, content_type="K")
        ok2 = _print_result("get_materials_by_filters: type filter returns 1",
                            len(type_filter) == 1, f"got {len(type_filter)}")

        active_filter = db_module.get_materials_by_filters(session, week_number=TEST_WEEK, is_active=True)
        ok3 = _print_result("get_materials_by_filters: is_active filter returns 1 (only K was approved)",
                            len(active_filter) == 1, f"got {len(active_filter)}")

        # Test get_weekly_feed_for_conditions
        feed = db_module.get_weekly_feed_for_conditions(session, ["T2DM"], TEST_WEEK, is_active=True)
        ok4 = _print_result("get_weekly_feed_for_conditions: active only returns 1",
                            len(feed) == 1 and feed[0].content_type == "K",
                            f"got {[(m.content_type, m.is_active) for m in feed]}")

        feed_all = db_module.get_weekly_feed_for_conditions(session, ["T2DM"], TEST_WEEK, is_active=False)
        ok5 = _print_result("get_weekly_feed_for_conditions: is_active=False returns inactive",
                            len(feed_all) >= 1, f"got {len(feed_all)}")

        return ok1 and ok2 and ok3 and ok4 and ok5
    except Exception as e:
        return _print_result("content API DB layer", False, str(e))
    finally:
        # Cleanup sentinel rows
        try:
            for m in [m_e, m_k]:
                obj = session.query(db_module.ContentMaterial).get(m.id)
                if obj:
                    session.delete(obj)
            session.commit()
        except Exception:
            pass
        session.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_TESTS = {
    "migration":       test_migration,
    "first_chat":      test_first_chat_at,
    "generation":      test_generation,
    "scheduler":       test_scheduler,
    "eka_migration":   test_eka_migration,
    "eka_idempotency": test_eka_idempotency,
    "eka_expiry":      test_eka_expiry,
    "eka_api_db":      test_eka_api_db,
}


def main():
    parser = argparse.ArgumentParser(description="Content pipeline smoke tests")
    parser.add_argument("--seed-dates", action="store_true",
                        help="Set first_chat_at on demo patients to simulate schedule days")
    parser.add_argument("--reset-dates", action="store_true",
                        help="Clear first_chat_at from demo patients")
    parser.add_argument("--test", choices=list(ALL_TESTS.keys()),
                        help="Run a single test")
    args = parser.parse_args()

    if args.seed_dates:
        seed_dates()
        return
    if args.reset_dates:
        reset_dates()
        return

    print("\nNutriBot Content Pipeline — Smoke Tests")
    print("=" * 45)

    tests = {args.test: ALL_TESTS[args.test]} if args.test else ALL_TESTS
    results = {}
    for name, fn in tests.items():
        results[name] = fn()

    print("\n" + "=" * 45)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Result: {passed}/{total} passed")
    if passed < total:
        failed = [k for k, v in results.items() if not v]
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
