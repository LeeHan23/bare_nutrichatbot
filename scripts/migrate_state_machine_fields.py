"""
migrate_state_machine_fields.py — Add external state-machine columns to patients.

New columns (owned by the care-path/rehab state machine + risk-scoring module,
both built outside this repo — see docs/state_machine_contract.md):
  - care_path
  - objective_ids
  - difficulty_ceiling
  - clinical_risk_tier

Idempotent — safe to run multiple times.

Usage:
    /home/han/Desktop/projects/bare_NutriChatbot/.venv/bin/python scripts/migrate_state_machine_fields.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

import database as db

NEW_COLUMNS = [
    ("care_path", "VARCHAR"),
    ("objective_ids", "JSON DEFAULT '[]'::json"),
    ("difficulty_ceiling", "VARCHAR"),
    ("clinical_risk_tier", "VARCHAR"),
]


def main():
    db.create_db_and_tables()
    inspector = inspect(db.engine)
    existing_cols = {col["name"] for col in inspector.get_columns("patients")}

    added, skipped = [], []
    with db.engine.begin() as conn:
        for col_name, col_type in NEW_COLUMNS:
            if col_name in existing_cols:
                skipped.append(col_name)
                continue
            conn.execute(text(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}"))
            added.append(col_name)

    print(f"Added {len(added)} columns: {added}")
    if skipped:
        print(f"Skipped {len(skipped)} (already exist): {skipped}")


if __name__ == "__main__":
    main()
