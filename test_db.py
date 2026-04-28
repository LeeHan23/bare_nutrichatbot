import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, add_api_client, get_api_client_by_name, get_client_by_key, get_all_api_clients, add_document_metadata, get_client_documents, get_document_by_id, delete_document_metadata

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_add_api_client(db):
    client = add_api_client(db, "TestClient1", "test-api-key-1")
    assert client.id is not None
    assert client.client_name == "TestClient1"


def test_get_api_client_by_name(db):
    add_api_client(db, "TestClient2", "test-api-key-2")
    client = get_api_client_by_name(db, "TestClient2")
    assert client is not None
    assert client.client_name == "TestClient2"


def test_get_client_by_key(db):
    add_api_client(db, "TestClient3", "secret-key-123")
    client = get_client_by_key(db, "secret-key-123")
    assert client is not None
    assert client.client_name == "TestClient3"


def test_document_metadata_lifecycle(db):
    client = add_api_client(db, "TestClient4", "key-doc")

    doc = add_document_metadata(
        db,
        client_id=client.id,
        filename="test.pdf",
        file_hash="hash123",
        file_size=1024,
        chunk_count=5,
    )
    assert doc.id is not None

    docs = get_client_documents(db, client.id)
    assert len(docs) == 1
    assert docs[0].filename == "test.pdf"

    fetched = get_document_by_id(db, doc.id, client.id)
    assert fetched is not None
    assert fetched.filename == "test.pdf"

    deleted = delete_document_metadata(db, doc.id, client.id)
    assert deleted is True

    docs_after = get_client_documents(db, client.id)
    assert len(docs_after) == 0
