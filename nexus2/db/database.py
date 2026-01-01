"""
Database Configuration and Session Management

SQLite-based persistence for Nexus 2.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Check if running in test mode
TESTING = os.environ.get("TESTING", "").lower() == "true"

if TESTING:
    # Use in-memory database for tests
    DATABASE_URL = "sqlite:///:memory:"
else:
    # Production: file-based database
    DB_DIR = Path(__file__).parent.parent.parent / "data"
    DB_DIR.mkdir(exist_ok=True)
    DB_PATH = DB_DIR / "nexus.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite specific
    echo=False,  # Set True for SQL debug logging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from nexus2.db import models  # Import to register models
    Base.metadata.create_all(bind=engine)
    if TESTING:
        print("[DB] Test database initialized (in-memory)")
    else:
        print(f"[DB] Database initialized at {DB_PATH}")
    
    # Run migrations for existing databases
    _run_migrations()


def _run_migrations():
    """Run simple schema migrations for existing databases."""
    from sqlalchemy import text
    
    with engine.connect() as conn:
        # Migration 1: Add auto_execute column to scheduler_settings if missing
        try:
            # Check if column exists by querying it
            conn.execute(text("SELECT auto_execute FROM scheduler_settings LIMIT 1"))
        except Exception:
            # Column doesn't exist, add it
            try:
                conn.execute(text(
                    "ALTER TABLE scheduler_settings ADD COLUMN auto_execute VARCHAR(5) DEFAULT 'false'"
                ))
                conn.commit()
                print("[DB] Migration: Added auto_execute column to scheduler_settings")
            except Exception as e:
                # Table might not exist yet, that's OK
                print(f"[DB] Migration skipped: {e}")
        
        # Migration 2: Add nac_broker_type column to scheduler_settings if missing
        try:
            conn.execute(text("SELECT nac_broker_type FROM scheduler_settings LIMIT 1"))
        except Exception:
            try:
                conn.execute(text(
                    "ALTER TABLE scheduler_settings ADD COLUMN nac_broker_type VARCHAR(20) DEFAULT 'alpaca_paper'"
                ))
                conn.commit()
                print("[DB] Migration: Added nac_broker_type column to scheduler_settings")
            except Exception:
                pass
        
        # Migration 3: Add nac_account column to scheduler_settings if missing
        try:
            conn.execute(text("SELECT nac_account FROM scheduler_settings LIMIT 1"))
        except Exception:
            try:
                conn.execute(text(
                    "ALTER TABLE scheduler_settings ADD COLUMN nac_account VARCHAR(10) DEFAULT 'A'"
                ))
                conn.commit()
                print("[DB] Migration: Added nac_account column to scheduler_settings")
            except Exception:
                pass
        
        # Migration 4: Add sim_mode column to scheduler_settings if missing
        try:
            conn.execute(text("SELECT sim_mode FROM scheduler_settings LIMIT 1"))
        except Exception:
            try:
                conn.execute(text(
                    "ALTER TABLE scheduler_settings ADD COLUMN sim_mode VARCHAR(5) DEFAULT 'false'"
                ))
                conn.commit()
                print("[DB] Migration: Added sim_mode column to scheduler_settings")
            except Exception:
                pass
