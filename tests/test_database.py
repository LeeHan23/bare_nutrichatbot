import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, add_user, check_login, get_user, User

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def test_add_and_get_user(db_session):
    add_user(db_session, "testuser", "password")
    user = get_user(db_session, "testuser")
    assert user is not None
    assert user.username == "testuser"

def test_check_login(db_session):
    add_user(db_session, "testuser", "password")
    assert check_login(db_session, "testuser", "password") is True
    assert check_login(db_session, "testuser", "wrongpassword") is False