"""
Shared dependencies for FastAPI endpoints to avoid circular imports.
"""
from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import database as db

# --- API Key Security ---
api_key_header = APIKeyHeader(name="X-API-Key")

TEAM_COOKIE_NAME = "team_key"

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


def get_team_client_from_cookie(request: Request, database: Session = Depends(get_db)):
    """
    Team sign-in session. The team_key cookie holds the person's own
    X-API-Key and is set with Domain=.computationalrd.com on login, so
    it's sent to nutribot., docs-api., and eval.computationalrd.com alike
    — one sign-in covers EKA review, judge calibration, and the chatbot.
    Raises 401 if missing/invalid.
    """
    key = request.cookies.get(TEAM_COOKIE_NAME)
    client = db.get_client_by_key(database, key) if key else None
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return client


def is_team_session(request: Request, database: Session) -> bool:
    """Non-raising check for OR-fallback auth branches (existing shared-key
    checks stay valid; a signed-in team cookie is just an alternate pass)."""
    key = request.cookies.get(TEAM_COOKIE_NAME)
    return bool(key) and db.get_client_by_key(database, key) is not None
