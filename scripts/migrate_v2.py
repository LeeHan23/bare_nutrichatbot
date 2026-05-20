"""
Add v2 cardiac-priority columns to the patients table.
Idempotent — safe to run multiple times.

New columns:
  - fat_intake_level       (T1 cardiac)
  - fat_sources            (T2 cardiac)
  - medication_compliance  (T2 cardiac)
  - activity_types         (T2 cardiac)
  - personalization_level  (L0/L1/L2/L3 — dietitian-assigned)
"""
import sys
sys.path.insert(0, '/mnt/ssd/bare_NutriChatbot')

from sqlalchemy import text, inspect
import database as db

NEW_COLUMNS = [
    # (column_name, sql_type)
    ("fat_intake_level",      "VARCHAR"),
    ("fat_sources",           "JSON DEFAULT '[]'::json"),
    ("medication_compliance", "VARCHAR"),
    ("activity_types",        "JSON DEFAULT '[]'::json"),
    ("personalization_level", "VARCHAR"),
]

def main():
    inspector = inspect(db.engine)
    existing_cols = {col["name"] for col in inspector.get_columns("patients")}

    added = []
    skipped = []

    with db.engine.begin() as conn:
        for col_name, col_type in NEW_COLUMNS:
            if col_name in existing_cols:
                skipped.append(col_name)
                continue
            sql = f'ALTER TABLE patients ADD COLUMN {col_name} {col_type}'
            conn.execute(text(sql))
            added.append(col_name)

    print(f"Added {len(added)} columns: {added}")
    if skipped:
        print(f"Skipped {len(skipped)} (already exist): {skipped}")

    inspector = inspect(db.engine)
    final_cols = [col["name"] for col in inspector.get_columns("patients")]
    new_total = len([c for c in final_cols if c in {n for n, _ in NEW_COLUMNS}])
    print(f"\nv2 columns now in patients table: {new_total}/{len(NEW_COLUMNS)}")

if __name__ == "__main__":
    main()
