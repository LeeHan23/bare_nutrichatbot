"""Smoke test for /patient/register — the explicit signup step for a
first-time visitor with no existing record (see app.py's patient_register()).
Confirms the new patient_id it returns is immediately usable by
/content/patient-feed/{patient_id}, i.e. a brand-new sign-in can actually
reach their EKA content."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app
from database import Base
from dependencies import get_db, get_api_client

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


class _FakeClient:
    id = 1
    client_name = "test-client"


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    # Scoped to this test's lifetime (not module import time) so it doesn't
    # clobber other test files' overrides on the same shared `app` object
    # when the full suite runs together.
    prev_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_api_client] = lambda: _FakeClient()
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides = prev_overrides


def test_register_then_locate_via_patient_feed():
    r = client.post("/patient/register", json={"name": "Test Patient", "ic_number": "990101-01-1234"})
    assert r.status_code == 200
    data = r.json()
    assert data["is_new"] is True
    patient_id = data["patient_id"]
    assert patient_id

    feed = client.get(f"/content/patient-feed/{patient_id}")
    assert feed.status_code == 200
    assert feed.json()["patient_id"] == patient_id


def test_register_duplicate_ic_rejected():
    client.post("/patient/register", json={"name": "Test Patient", "ic_number": "990101-01-1234"})
    r = client.post("/patient/register", json={"name": "Someone Else", "ic_number": "990101-01-1234"})
    assert r.status_code == 409
