import os
import secrets
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, JSON, Float, Boolean, Text
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

    # WhatsApp delivery
    phone_number       = Column(String, nullable=True)   # e.g. +60123456789
    whatsapp_opted_out = Column(Boolean, default=False)   # True after patient replies STOP

    # Content delivery tracking — set on first chat message
    first_chat_at   = Column(DateTime, nullable=True)

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

# --- Content Material Model ---
class ContentMaterial(Base):
    """
    A single educational content item for a condition group + day offset.
    raw_tips holds LLM-generated JSON tips.
    file_path points to the polished file uploaded by the dev team.
    is_active = True once a polished file is ready for delivery.
    """
    __tablename__ = "content_materials"

    id              = Column(Integer, primary_key=True, index=True)
    condition_group = Column(String, nullable=False, index=True)   # e.g. "T2DM", "CKD"
    condition_tags  = Column(JSON, default=list)                   # e.g. ["Type 2 Diabetes"]
    day_offset      = Column(Integer, nullable=True, index=True)   # 3,5,7,14,21,30 (NULL for weekly EKA)
    content_type    = Column(String(1), nullable=True, index=True) # "E" | "K" | "A" | NULL (legacy nutrition)
    week_number     = Column(Integer, nullable=True, index=True)   # ISO week number (weekly EKA only)
    topic           = Column(String, nullable=False)               # "breakfast_choices"
    title           = Column(String, nullable=False)               # human-readable
    raw_tips        = Column(JSON, default=list)                   # [{tip_number,tip,source_hint}] or EKA structured dict
    file_path       = Column(String, nullable=True)                # polished file (dev team uploads)
    file_type       = Column(String, nullable=True)                # pdf / word / image
    is_active       = Column(Boolean, default=False)               # True once dev team approves
    created_at      = Column(DateTime, nullable=False)
    expires_at      = Column(DateTime, nullable=True, index=True)  # EKA: created_at + 14 days; NULL = never expires (legacy)

    delivery_logs = relationship("ContentDeliveryLog", back_populates="material")


# --- Content Delivery Log Model ---
class ContentDeliveryLog(Base):
    """
    Tracks scheduled and sent content deliveries per patient.
    One row per (patient, day_offset, material) combination.
    status: queued → sent | failed | no_material
    """
    __tablename__ = "content_delivery_log"

    id             = Column(Integer, primary_key=True, index=True)
    patient_id     = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id    = Column(Integer, ForeignKey("content_materials.id"), nullable=True)
    condition_group = Column(String, nullable=False)               # denormalised for easy querying
    day_offset     = Column(Integer, nullable=True)                 # NULL for weekly EKA deliveries
    scheduled_date = Column(DateTime, nullable=False, index=True)
    status         = Column(String, default="queued")              # queued | sent | failed | no_material
    sent_at        = Column(DateTime, nullable=True)
    channel        = Column(String, nullable=True)                 # whatsapp | email | in_app

    material = relationship("ContentMaterial", back_populates="delivery_logs")


# --- Chat Message Model ---
class ChatMessage(Base):
    """
    Persisted conversation history, keyed by session_id.
    Survives bot restarts (unlike the old InMemoryChatMessageHistory) and
    gives WhatsApp / multi-channel delivery a shared history per patient session.
    """
    __tablename__ = "chat_messages"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True, index=True)
    role       = Column(String, nullable=False)   # "user" | "assistant"
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, index=True)


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


def normalise_phone_number(phone_number: str) -> str:
    """Normalise to +<country><number> — strip 'whatsapp:' prefix, spaces, dashes."""
    cleaned = phone_number.replace("whatsapp:", "").strip().replace(" ", "").replace("-", "")
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def get_patient_by_phone(db_session, phone_number: str):
    """Look up a patient by their WhatsApp phone number (any format; normalised before lookup)."""
    normalised = normalise_phone_number(phone_number)
    return db_session.query(Patient).filter(Patient.phone_number == normalised).first()


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


def set_first_chat_at(db_session, patient_id: int):
    """Set first_chat_at to now if not already set. Safe to call on every message."""
    from datetime import datetime
    patient = get_patient(db_session, patient_id)
    if patient and patient.first_chat_at is None:
        patient.first_chat_at = datetime.utcnow()
        db_session.commit()


def get_all_patients_with_first_chat(db_session):
    """Return all patients that have chatted at least once."""
    return db_session.query(Patient).filter(Patient.first_chat_at.isnot(None)).all()


def upsert_content_material(db_session, condition_group: str, condition_tags: list,
                             day_offset: int, topic: str, title: str, raw_tips: list) -> "ContentMaterial":
    """Insert a new ContentMaterial row. Always creates a new row (generation is idempotent via the scheduler check)."""
    from datetime import datetime
    mat = ContentMaterial(
        condition_group=condition_group,
        condition_tags=condition_tags,
        day_offset=day_offset,
        topic=topic,
        title=title,
        raw_tips=raw_tips,
        is_active=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(mat)
    db_session.commit()
    db_session.refresh(mat)
    return mat


def get_active_materials_for_conditions(db_session, condition_groups: list, day_offset: int):
    """Find is_active=True materials matching any of the condition groups at this day offset."""
    return db_session.query(ContentMaterial).filter(
        ContentMaterial.day_offset == day_offset,
        ContentMaterial.condition_group.in_(condition_groups),
        ContentMaterial.is_active == True,
    ).all()


def get_all_materials(db_session, day_offset: int = None, condition_group: str = None):
    """List materials, optionally filtered."""
    q = db_session.query(ContentMaterial)
    if day_offset is not None:
        q = q.filter(ContentMaterial.day_offset == day_offset)
    if condition_group:
        q = q.filter(ContentMaterial.condition_group == condition_group)
    return q.order_by(ContentMaterial.condition_group, ContentMaterial.day_offset).all()


def log_content_delivery(db_session, patient_id: int, day_offset: int,
                         condition_group: str, scheduled_date, material_id: int = None,
                         status: str = "queued") -> "ContentDeliveryLog":
    from datetime import datetime
    entry = ContentDeliveryLog(
        patient_id=patient_id,
        material_id=material_id,
        condition_group=condition_group,
        day_offset=day_offset,
        scheduled_date=scheduled_date,
        status=status,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def get_delivery_log(db_session, patient_id: int = None, status: str = None, scheduled_date=None):
    """Query delivery log with optional filters."""
    q = db_session.query(ContentDeliveryLog)
    if patient_id:
        q = q.filter(ContentDeliveryLog.patient_id == patient_id)
    if status:
        q = q.filter(ContentDeliveryLog.status == status)
    if scheduled_date:
        from datetime import datetime, timedelta
        day_start = datetime.combine(scheduled_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        q = q.filter(ContentDeliveryLog.scheduled_date >= day_start,
                     ContentDeliveryLog.scheduled_date < day_end)
    return q.order_by(ContentDeliveryLog.scheduled_date).all()


EKA_EXPIRY_DAYS = 14  # EKA materials expire 14 days after creation (deleted on 3rd-week Monday run)


def upsert_eka_material(db_session, condition_group: str, condition_tags: list,
                        content_type: str, week_number: int, topic: str, title: str,
                        raw_content: dict, force: bool = False) -> "ContentMaterial":
    """Insert a weekly E/K/A material. Skips if (group, type, week, topic) already exists unless force=True."""
    from datetime import datetime, timedelta
    existing = db_session.query(ContentMaterial).filter(
        ContentMaterial.condition_group == condition_group,
        ContentMaterial.content_type == content_type,
        ContentMaterial.week_number == week_number,
        ContentMaterial.topic == topic,
    ).first()
    if existing and not force:
        return existing
    if existing and force:
        existing.raw_tips = raw_content
        existing.title = title
        existing.condition_tags = condition_tags
        db_session.commit()
        db_session.refresh(existing)
        return existing
    now = datetime.utcnow()
    mat = ContentMaterial(
        condition_group=condition_group,
        condition_tags=condition_tags,
        content_type=content_type,
        week_number=week_number,
        day_offset=None,
        topic=topic,
        title=title,
        raw_tips=raw_content,
        is_active=False,
        created_at=now,
        expires_at=now + timedelta(days=EKA_EXPIRY_DAYS),
    )
    db_session.add(mat)
    db_session.commit()
    db_session.refresh(mat)
    return mat


def cleanup_expired_eka_materials(db_session) -> int:
    """
    Delete EKA materials whose expires_at has passed.
    Called at the start of each weekly scheduler run.
    Returns the number of rows deleted.
    """
    from datetime import datetime
    expired = db_session.query(ContentMaterial).filter(
        ContentMaterial.content_type.isnot(None),
        ContentMaterial.expires_at.isnot(None),
        ContentMaterial.expires_at < datetime.utcnow(),
    ).all()
    count = len(expired)
    for mat in expired:
        db_session.delete(mat)
    if count:
        db_session.commit()
    return count


def get_materials_by_filters(db_session, content_type: str = None, week_number: int = None,
                              condition_group: str = None, is_active: bool = None,
                              include_expired: bool = False,
                              limit: int = 100, offset: int = 0) -> list:
    """
    List ContentMaterials with optional filters.
    By default excludes expired EKA materials (include_expired=False).
    """
    from datetime import datetime
    q = db_session.query(ContentMaterial)
    if not include_expired:
        q = q.filter(
            (ContentMaterial.expires_at.is_(None)) |
            (ContentMaterial.expires_at >= datetime.utcnow())
        )
    if content_type is not None:
        q = q.filter(ContentMaterial.content_type == content_type)
    if week_number is not None:
        q = q.filter(ContentMaterial.week_number == week_number)
    if condition_group is not None:
        q = q.filter(ContentMaterial.condition_group == condition_group)
    if is_active is not None:
        q = q.filter(ContentMaterial.is_active == is_active)
    return q.order_by(ContentMaterial.condition_group, ContentMaterial.content_type, ContentMaterial.week_number).offset(offset).limit(limit).all()


def get_weekly_feed_for_conditions(db_session, condition_groups: list, week_number: int,
                                    content_type: str = None, is_active: bool = True) -> list:
    """Return this week's E/K/A materials for given condition groups. Expired materials are excluded."""
    from datetime import datetime
    q = db_session.query(ContentMaterial).filter(
        ContentMaterial.week_number == week_number,
        ContentMaterial.condition_group.in_(condition_groups),
        ContentMaterial.content_type.isnot(None),
        (ContentMaterial.expires_at.is_(None)) |
        (ContentMaterial.expires_at >= datetime.utcnow()),
    )
    if content_type:
        q = q.filter(ContentMaterial.content_type == content_type)
    if is_active is not None:
        q = q.filter(ContentMaterial.is_active == is_active)
    return q.order_by(ContentMaterial.content_type, ContentMaterial.condition_group).all()


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


# --- Chat History Functions ---

def add_chat_message(db_session, session_id: str, patient_id: int | None, role: str, content: str):
    """Append one message (role: 'user' or 'assistant') to a session's history."""
    from datetime import datetime
    msg = ChatMessage(
        session_id=session_id,
        patient_id=patient_id,
        role=role,
        content=content,
        created_at=datetime.utcnow(),
    )
    db_session.add(msg)
    db_session.commit()
    return msg


def get_chat_history(db_session, session_id: str, limit: int = 12):
    """Return the most recent `limit` messages for a session, oldest first."""
    rows = (
        db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def clear_chat_history(db_session, session_id: str) -> int:
    """Delete all messages for a session. Returns the number of rows deleted."""
    count = db_session.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db_session.commit()
    return count