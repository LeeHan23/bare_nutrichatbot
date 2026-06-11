"""
migrate_eka_columns.py — Add content_type and week_number columns to content_materials.

Safe to run multiple times (checks before altering).

Usage:
    /home/han/miniconda3/bin/python scripts/migrate_eka_columns.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, create_db_and_tables


def migrate():
    create_db_and_tables()
    with engine.connect() as conn:
        for col, definition in [
            ("content_type", "VARCHAR(1) DEFAULT NULL"),
            ("week_number",  "INTEGER DEFAULT NULL"),
            ("expires_at",   "TIMESTAMP DEFAULT NULL"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE content_materials ADD COLUMN {col} {definition}"))
                conn.commit()
                print(f"  Added column: {col}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"  Column already exists: {col} — skipping")
                else:
                    print(f"  Error adding {col}: {e}")

        # day_offset must be nullable for EKA rows (which have no day offset)
        try:
            conn.execute(text("ALTER TABLE content_materials ALTER COLUMN day_offset DROP NOT NULL"))
            conn.commit()
            print("  day_offset is now nullable")
        except Exception:
            print("  day_offset already nullable — skipping")

        # Add indexes if not present
        for idx_name, col in [
            ("ix_content_materials_content_type", "content_type"),
            ("ix_content_materials_week_number",  "week_number"),
            ("ix_content_materials_expires_at",   "expires_at"),
        ]:
            try:
                conn.execute(text(
                    f"CREATE INDEX {idx_name} ON content_materials ({col})"
                ))
                conn.commit()
                print(f"  Created index: {idx_name}")
            except Exception:
                print(f"  Index already exists: {idx_name} — skipping")

    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
