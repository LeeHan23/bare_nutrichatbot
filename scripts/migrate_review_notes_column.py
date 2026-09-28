"""
migrate_review_notes_column.py — Add content_materials.review_notes (JSON,
default '[]'), the reviewer-comments field for the /eka-review "Notes"
section. Nullable-equivalent (defaults to an empty list), no backfill.

Safe to run multiple times (checks before altering).

Usage:
    /home/han/Desktop/projects/bare_NutriChatbot/.venv/bin/python scripts/migrate_review_notes_column.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, create_db_and_tables


def migrate():
    create_db_and_tables()
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE content_materials ADD COLUMN review_notes JSON DEFAULT '[]'::json"
            ))
            conn.commit()
            print("  Added column: content_materials.review_notes")
        except Exception as e:
            conn.rollback()  # required: a failed statement aborts the
            # connection's transaction — without this, every subsequent
            # statement on this connection fails with
            # InFailedSqlTransaction even if it would otherwise succeed.
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("  Column already exists: content_materials.review_notes — skipping")
            else:
                print(f"  Error adding content_materials.review_notes: {e}")

        conn.execute(text(
            "UPDATE content_materials SET review_notes = '[]'::json WHERE review_notes IS NULL"
        ))
        conn.commit()

    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
