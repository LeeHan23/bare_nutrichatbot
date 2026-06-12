"""
migrate_whatsapp_columns.py — Add whatsapp_opted_out column to patients.

Safe to run multiple times (checks before altering).

Usage:
    /home/han/miniconda3/bin/python scripts/migrate_whatsapp_columns.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, create_db_and_tables


def migrate():
    create_db_and_tables()
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE patients ADD COLUMN whatsapp_opted_out BOOLEAN DEFAULT FALSE"))
            conn.commit()
            print("  Added column: whatsapp_opted_out")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("  Column already exists: whatsapp_opted_out — skipping")
            else:
                print(f"  Error adding whatsapp_opted_out: {e}")

    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
