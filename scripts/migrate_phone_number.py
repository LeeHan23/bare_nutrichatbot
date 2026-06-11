"""
Add phone_number column to patients table.
Safe to run multiple times — skips if column already exists.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text


def run():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE patients ADD COLUMN phone_number VARCHAR"))
            conn.commit()
            print("✓ Added phone_number column to patients.")
        except Exception as exc:
            msg = str(exc).lower()
            if "already exists" in msg or "duplicate column" in msg:
                print("phone_number already exists — skipping.")
            else:
                raise


if __name__ == "__main__":
    run()
