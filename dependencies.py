"""
Shared dependencies for FastAPI endpoints to avoid circular imports.
"""
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import database as db

# --- API Key Security ---
api_key_header = APIKeyHeader(name="X-API-Key")

def get_db():
    """Database session dependency"""
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

def get_api_client(
    api_key: str = Security(api_key_header), 
    database: Session = Depends(get_db)
):
    """
    A dependency that validates the X-API-Key header.
    Returns the authenticated ApiClient or raises 401 error.
    """
    client = db.get_client_by_key(database, api_key)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return client
