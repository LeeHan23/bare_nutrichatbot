"""
Add content pipeline tables and first_chat_at column.
Idempotent — safe to run multiple times.

Changes:
  - patients.first_chat_at       (TIMESTAMP, nullable)
  - CREATE TABLE content_materials
  - CREATE TABLE content_delivery_log
"""
import sys
sys.path.insert(0, '/mnt/ext/bare_NutriChatbot')

from sqlalchemy import text, inspect
import database as db


def main():
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()
    existing_patient_cols = {c["name"] for c in inspector.get_columns("patients")}

    # 1. Add first_chat_at to patients
    if "first_chat_at" not in existing_patient_cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE patients ADD COLUMN first_chat_at TIMESTAMP"))
        print("  ADDED   patients.first_chat_at")
    else:
        print("  SKIP    patients.first_chat_at (already exists)")

    # 2. Create content_materials and content_delivery_log via SQLAlchemy
    # (ContentMaterial and ContentDeliveryLog are registered in Base.metadata)
    for tname in ["content_materials", "content_delivery_log"]:
        if tname in existing_tables:
            print(f"  SKIP    {tname} (already exists)")
        else:
            print(f"  WILL CREATE {tname}")

    db.create_db_and_tables()
    print("  create_db_and_tables() complete")

    # Verify
    inspector = inspect(db.engine)
    final_tables = inspector.get_table_names()
    for tname in ["content_materials", "content_delivery_log"]:
        status = "OK" if tname in final_tables else "MISSING"
        print(f"  {status}     {tname}")

    patient_cols = {c["name"] for c in inspector.get_columns("patients")}
    print(f"  {'OK' if 'first_chat_at' in patient_cols else 'MISSING'}     patients.first_chat_at")
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
