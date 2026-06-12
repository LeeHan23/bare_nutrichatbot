"""
migrate_content_delivery_log.py — Make content_delivery_log.day_offset nullable.

EKA (weekly Exercise/Knowledge/Activity) materials have day_offset=NULL, but
delivery log entries for them previously violated the NOT NULL constraint on
content_delivery_log.day_offset. This makes the column nullable so EKA
deliveries can be logged.

Safe to run multiple times.

Usage:
    /home/han/miniconda3/bin/python scripts/migrate_content_delivery_log.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, create_db_and_tables


def migrate():
    create_db_and_tables()
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE content_delivery_log ALTER COLUMN day_offset DROP NOT NULL"))
            conn.commit()
            print("  day_offset is now nullable")
        except Exception as e:
            print(f"  day_offset already nullable or error: {e}")

    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
