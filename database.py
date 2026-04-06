import os
import secrets
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/users.db")
os.makedirs("data", exist_ok=True)

# --- SQLAlchemy Setup ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- User Database Model (FOR DEMO UI) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# --- NEW: API Client Model (FOR B2B "SLOT-IN") ---
class ApiClient(Base):
    __tablename__ = "api_clients"
    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, unique=True, index=True) # e.g., "HealthTechCo"
    hashed_api_key = Column(String, unique=True, index=True)
    
    # Relationship to documents
    documents = relationship("DocumentMetadata", back_populates="client", cascade="all, delete-orphan")

# --- NEW: Document Metadata Model ---
class DocumentMetadata(Base):
    __tablename__ = "document_metadata"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_hash = Column(String, index=True)  # For deduplication
    upload_date = Column(DateTime, nullable=False)
    file_size = Column(Integer)  # In bytes
    chunk_count = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending, completed, failed
    
    # Relationship to client
    client = relationship("ApiClient", back_populates="documents")

# --- Database Creation ---
def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

# --- User Management Functions (for Demo UI) ---
def get_user(db_session, username: str):
    return db_session.query(User).filter(User.username == username).first()

def add_user(db_session, username: str, password: str):
    if get_user(db_session, username):
        raise ValueError("Username already exists")
    hashed_password = generate_password_hash(password)
    new_user = User(username=username, hashed_password=hashed_password)
    db_session.add(new_user)
    db_session.commit()
    db_session.refresh(new_user)
    return new_user

def check_login(db_session, username: str, password: str) -> bool:
    user = get_user(db_session, username)
    if not user:
        return False
    return check_password_hash(user.hashed_password, password)

# --- NEW: API Client Management Functions (for B2B API) ---
def add_api_client(db_session, client_name: str, api_key: str):
    """
    Adds a new B2B client and their hashed API key to the database.
    """
    hashed_key = generate_password_hash(api_key)
    new_client = ApiClient(client_name=client_name, hashed_api_key=hashed_key)
    db_session.add(new_client)
    db_session.commit()
    db_session.refresh(new_client)
    return new_client

def get_api_client_by_name(db_session, client_name: str):
    """
    Checks if a client name already exists.
    """
    return db_session.query(ApiClient).filter(ApiClient.client_name == client_name).first()

def get_client_by_key(db_session, api_key: str) -> ApiClient | None:
    """
    Finds the client by checking the provided API key against all hashed keys.
    This is intentionally slow to protect against timing attacks.
    """
    clients = db_session.query(ApiClient).all()
    for client in clients:
        if check_password_hash(client.hashed_api_key, api_key):
            return client
    return None

def get_all_api_clients(db_session):
    """
    Returns a list of all API clients.
    """
    return db_session.query(ApiClient).all()

# --- NEW: Document Management Functions ---
def add_document_metadata(db_session, client_id: int, filename: str, file_hash: str, 
                         file_size: int, chunk_count: int = 0, status: str = "completed"):
    """
    Add document metadata to track uploaded files.
    """
    from datetime import datetime
    doc = DocumentMetadata(
        client_id=client_id,
        filename=filename,
        file_hash=file_hash,
        upload_date=datetime.utcnow(),
        file_size=file_size,
        chunk_count=chunk_count,
        status=status
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc

def get_client_documents(db_session, client_id: int):
    """
    Get all documents for a specific client.
    """
    return db_session.query(DocumentMetadata).filter(
        DocumentMetadata.client_id == client_id
    ).order_by(DocumentMetadata.upload_date.desc()).all()

def get_document_by_id(db_session, document_id: int, client_id: int = None):
    """
    Get a specific document by ID, optionally filtered by client_id for security.
    """
    query = db_session.query(DocumentMetadata).filter(DocumentMetadata.id == document_id)
    if client_id is not None:
        query = query.filter(DocumentMetadata.client_id == client_id)
    return query.first()

def get_document_by_hash(db_session, client_id: int, file_hash: str):
    """
    Check if a document with this hash already exists for this client (deduplication).
    """
    return db_session.query(DocumentMetadata).filter(
        DocumentMetadata.client_id == client_id,
        DocumentMetadata.file_hash == file_hash
    ).first()

def delete_document_metadata(db_session, document_id: int, client_id: int = None):
    """
    Delete document metadata. Returns True if deleted, False if not found.
    """
    doc = get_document_by_id(db_session, document_id, client_id)
    if doc:
        db_session.delete(doc)
        db_session.commit()
        return True
    return False

# Tables are created at app startup (see app.py startup_event).
# Call create_db_and_tables() explicitly in scripts that need it.