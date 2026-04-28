"""
Set DATABASE_URL to SQLite in-memory BEFORE any module imports so that
database.py creates a local engine instead of trying to reach the remote
PostgreSQL server.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test.db")
