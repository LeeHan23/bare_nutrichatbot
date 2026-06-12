"""
migrate_chat_history.py — Create the chat_messages table.

chat_messages persists conversation history per session_id, replacing the old
InMemoryChatMessageHistory (which was lost on every bot restart). It's a brand
new table, so create_db_and_tables() (Base.metadata.create_all) creates it
without needing any ALTER statements. Safe to run multiple times.

Usage:
    /home/han/miniconda3/bin/python scripts/migrate_chat_history.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from database import engine, create_db_and_tables


def migrate():
    create_db_and_tables()
    if "chat_messages" in inspect(engine).get_table_names():
        print("  chat_messages table is present")
    else:
        print("  chat_messages table NOT found — check for errors above")
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
