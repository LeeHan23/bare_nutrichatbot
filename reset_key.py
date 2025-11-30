import os
import sys

# Force local SQLite (MUST be before importing database)
os.environ["DATABASE_URL"] = "sqlite:///./data/users.db"

from werkzeug.security import generate_password_hash
from sqlalchemy.orm import Session
import database as db

def reset_local_key():
    print("🔄 Resetting API Key for 'LocalClient'...")
    
    # Setup DB
    database = db.SessionLocal()
    
    # Find Client
    client = db.get_api_client_by_name(database, "LocalClient")
    if not client:
        print("❌ 'LocalClient' not found! Did you run ingestion?")
        return
        
    # Generate New Key
    import secrets
    new_key = f"nbk_local_{secrets.token_hex(16)}"
    hashed_key = generate_password_hash(new_key)
    
    # Update DB
    client.hashed_api_key = hashed_key
    database.commit()
    
    print(f"\n✅ Success! New API Key for LocalClient:")
    print(f"👉 {new_key}")
    print("\n(Copy this key now, you won't see it again!)")

if __name__ == "__main__":
    reset_local_key()
