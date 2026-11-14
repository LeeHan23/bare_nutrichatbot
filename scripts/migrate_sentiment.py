"""
migrate_sentiment.py — Create the patient_sentiment table.

One row per classified patient turn (sentiment.py), read by the
/team/sentiment dashboard (team_router.py). Brand new table, so
create_db_and_tables() creates it without any ALTER. Safe to run repeatedly.

Usage:
    .venv/bin/python scripts/migrate_sentiment.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from database import engine, create_db_and_tables

if __name__ == "__main__":
    create_db_and_tables()
    ok = "patient_sentiment" in inspect(engine).get_table_names()
    print("  patient_sentiment table is present" if ok else "  patient_sentiment NOT found — check errors above")
