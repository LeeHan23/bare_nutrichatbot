"""
migrate_component_columns.py — Add columns for the MyHeartCoach 10-Component
taxonomy (see taxonomy.py): content_materials.component and
patients.onboarding_stage. Both nullable, no backfill (existing rows stay
NULL — legacy/general, not guessed at).

Safe to run multiple times (checks before altering).

Usage:
    /home/han/Desktop/projects/bare_NutriChatbot/.venv/bin/python scripts/migrate_component_columns.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, create_db_and_tables


def migrate():
    create_db_and_tables()
    with engine.connect() as conn:
        for table, col, definition in [
            ("content_materials", "component", "VARCHAR DEFAULT NULL"),
            ("patients", "onboarding_stage", "VARCHAR DEFAULT NULL"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                conn.commit()
                print(f"  Added column: {table}.{col}")
            except Exception as e:
                conn.rollback()  # required: a failed statement aborts the
                # connection's transaction — without this, every subsequent
                # statement on this connection fails with
                # InFailedSqlTransaction even if it would otherwise succeed.
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"  Column already exists: {table}.{col} — skipping")
                else:
                    print(f"  Error adding {table}.{col}: {e}")

        for idx_name, table, col in [
            ("ix_content_materials_component", "content_materials", "component"),
            ("ix_patients_onboarding_stage", "patients", "onboarding_stage"),
        ]:
            try:
                conn.execute(text(f"CREATE INDEX {idx_name} ON {table} ({col})"))
                conn.commit()
                print(f"  Created index: {idx_name}")
            except Exception:
                conn.rollback()
                print(f"  Index already exists: {idx_name} — skipping")

    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
