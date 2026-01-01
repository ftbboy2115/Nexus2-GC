"""
Pytest Configuration and Fixtures

Sets up isolated test environment with in-memory database.
"""

import os
import pytest

# Set TESTING mode before any imports
os.environ["TESTING"] = "true"

# Force paper broker for tests (not Alpaca)
os.environ["FORCE_PAPER_BROKER"] = "true"

from sqlalchemy import event
from sqlalchemy.orm import Session

from nexus2.db import Base, engine, SessionLocal, init_db


@pytest.fixture(scope="function", autouse=True)
def reset_database():
    """Reset database before each test function."""
    # Drop all tables and recreate
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup after test
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Provide a clean database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
