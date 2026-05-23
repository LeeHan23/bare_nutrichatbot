import os
import secrets
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, JSON, Float
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
    
    # Relationship to documents and patients
    documents = relationship("DocumentMetadata", back_populates="client", cascade="all, delete-orphan")
    patients  = relationship("Patient", back_populates="client", cascade="all, delete-orphan")

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

# --- Patient Model ---
class Patient(Base):
    __tablename__ = "patients"
    id       = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False, index=True)

    # Demographics
    name      = Column(String, nullable=False)
    ic_number = Column(String, index=True)   # Malaysian IC: YYMMDD-SS-XXXX
    age       = Column(Integer)
    gender    = Column(String)        # "Male" / "Female"
    ethnicity = Column(String)        # "Malay" / "Chinese" / "Indian"
    weight_kg = Column(Float)
    height_cm = Column(Float)

    # Clinical (stored as JSON lists)
    conditions           = Column(JSON, default=list)
    medications          = Column(JSON, default=list)
    dietary_restrictions = Column(JSON, default=list)
    allergies            = Column(JSON, default=list)

    # Free-text clinical notes
    notes = Column(String, default="")

    # ──────────────────────────────────────────────────────────────────
    # Nutribot supplementary fields (eNCPT 2020 aligned)
    # Filled by the extractor from chat conversation, not from hospital.
    # All nullable — existing rows remain valid.
    # ──────────────────────────────────────────────────────────────────

    # Tier 1 — Critical
    fluid_intake_ml        = Column(Integer, nullable=True)        # FH-1.2.1.1.1
    alcohol_per_week       = Column(Integer, nullable=True)        # FH-1.4.1.1
    supplements            = Column(JSON, default=list)            # FH-3.2.1
    religion               = Column(String, nullable=True)         # CH-3.1.7
    tobacco_status         = Column(String, nullable=True)         # CH-1.1.10

    # Tier 2 — Important
    meals_per_day          = Column(Integer, nullable=True)        # FH-1.2.2.3.1.1
    snacks_per_day         = Column(Integer, nullable=True)        # FH-1.2.2.3.1.2
    processed_food_freq    = Column(String, nullable=True)         # FH-1.2.2.2.5
    fast_food_freq         = Column(String, nullable=True)         # FH-1.2.2.2.6
    self_prepared_freq     = Column(String, nullable=True)         # FH-1.2.2.2.7
    caffeine_mg_per_day    = Column(Integer, nullable=True)        # FH-1.4.3.1
    sugar_drinks_ml        = Column(Integer, nullable=True)        # FH-1.2.1.1.1.3
    activity_freq          = Column(String, nullable=True)         # FH-7.3.1
    activity_minutes       = Column(Integer, nullable=True)        # FH-7.3.2
    activity_intensity     = Column(String, nullable=True)         # FH-7.3.3
    food_avoidance         = Column(JSON, default=list)            # FH-5.2.1
    nutrition_knowledge    = Column(Integer, nullable=True)        # FH-4.1.3 (1-5)
    readiness_to_change    = Column(String, nullable=True)         # FH-4.2.8
    sodium_awareness       = Column(String, nullable=True)         # FH-1.5.6.1

    # ── v2 (cardiac priority additions) ─────────────────────────────────
    fat_intake_level       = Column(String, nullable=True)         # FH-1.5.1.1 (low/moderate/high)
    fat_sources            = Column(JSON, default=list)            # FH-1.5.1.2
    medication_compliance  = Column(String, nullable=True)         # FH-3.1.1.1 (good/variable/poor)
    activity_types         = Column(JSON, default=list)            # FH-7.3.1.1
    extractor_food_allergies = Column(JSON, default=list)          # FH-1.6 (self-reported, extractor-filled)

    # Dietitian-assigned personalization level (L0/L1/L2/L3)
    personalization_level  = Column(String, nullable=True)

    # Provenance — which fields were filled by extractor + when
    extractor_metadata     = Column(JSON, default=dict)            # {field: {confidence, last_updated, source_session_id}}

    # Demo auth
    username        = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    # Relationship back to the B2B client
    client = relationship("ApiClient", back_populates="patients")


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


# --- Patient Management Functions ---

def add_patient(db_session, client_id: int, name: str, age: int, gender: str,
                ethnicity: str, weight_kg: float, height_cm: float,
                conditions: list, medications: list, dietary_restrictions: list,
                allergies: list, notes: str, username: str, password: str,
                ic_number: str = None, personalization_level: str = None):
    """Create a new patient record with a hashed password."""
    hashed_pw = generate_password_hash(password)
    patient = Patient(
        client_id=client_id, name=name, ic_number=ic_number, age=age, gender=gender,
        ethnicity=ethnicity, weight_kg=weight_kg, height_cm=height_cm,
        conditions=conditions, medications=medications,
        dietary_restrictions=dietary_restrictions, allergies=allergies,
        notes=notes, username=username, hashed_password=hashed_pw,
        personalization_level=personalization_level,
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient


def get_patient(db_session, patient_id: int):
    """Fetch a single patient by primary key."""
    return db_session.query(Patient).filter(Patient.id == patient_id).first()


def get_patient_by_username(db_session, username: str):
    """Fetch a patient by username."""
    return db_session.query(Patient).filter(Patient.username == username).first()


def get_patients_by_name(db_session, name: str, client_id: int):
    """Case-insensitive name search within a client's patients.
    Tries exact match first; falls back to contains if no exact match found."""
    exact = db_session.query(Patient).filter(
        Patient.client_id == client_id,
        Patient.name.ilike(name.strip())
    ).all()
    if exact:
        return exact
    return db_session.query(Patient).filter(
        Patient.client_id == client_id,
        Patient.name.ilike(f"%{name.strip()}%")
    ).all()


def get_patient_by_ic(db_session, ic_number: str, client_id: int):
    """Look up a patient by exact IC number (normalised — strips dashes and spaces)."""
    normalised = ic_number.replace("-", "").replace(" ", "")
    patients = db_session.query(Patient).filter(
        Patient.client_id == client_id,
        Patient.ic_number.isnot(None)
    ).all()
    for p in patients:
        if p.ic_number and p.ic_number.replace("-", "").replace(" ", "") == normalised:
            return p
    return None


def get_patients_by_client(db_session, client_id: int):
    """List all patients belonging to a specific B2B client."""
    return db_session.query(Patient).filter(Patient.client_id == client_id).all()


def check_patient_login(db_session, username: str, password: str):
    """Returns the Patient if credentials are valid, else None."""
    patient = get_patient_by_username(db_session, username)
    if patient and check_password_hash(patient.hashed_password, password):
        return patient
    return None


def patient_to_profile_dict(patient) -> dict:
    """
    Convert a Patient ORM object to the profile dict consumed by rag.get_rag_response().
    Key 'condition' (not 'conditions') matches the existing rag.py dict schema.
    """
    return {
        "condition":              patient.conditions           or [],
        "medications":            patient.medications          or [],
        "dietary_restrictions":   patient.dietary_restrictions or [],
        "name":                   patient.name,
        "age":                    patient.age,
        "gender":                 patient.gender,
        "ethnicity":              patient.ethnicity,
        "weight_kg":              patient.weight_kg,
        "height_cm":              patient.height_cm,
        "allergies":              patient.allergies            or [],
        "notes":                  patient.notes                or "",
        "personalization_level":  patient.personalization_level,
        # v2 cardiac supplementary fields (extractor-filled)
        "fat_intake_level":        patient.fat_intake_level,
        "fat_sources":             patient.fat_sources             or [],
        "medication_compliance":   patient.medication_compliance,
        "activity_types":          patient.activity_types          or [],
        "extractor_food_allergies": patient.extractor_food_allergies or [],
    }