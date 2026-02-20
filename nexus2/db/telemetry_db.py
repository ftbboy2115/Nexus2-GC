"""
Telemetry Database

SQLite database for scanner telemetry, catalyst audits, and AI model comparisons.
Centralizes all system observability data in one queryable store.
"""

from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, Integer, Float, BigInteger, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base

from nexus2.utils.time_utils import now_utc, format_iso_utc

# Database path - same data directory as other DBs
DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)
TELEMETRY_DB_PATH = DB_DIR / "telemetry.db"
TELEMETRY_DATABASE_URL = f"sqlite:///{TELEMETRY_DB_PATH}"

# Create engine
telemetry_engine = create_engine(
    TELEMETRY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Session factory
TelemetrySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=telemetry_engine)

# Base class for Telemetry models
TelemetryBase = declarative_base()


# =============================================================================
# MODELS
# =============================================================================

class WarriorScanResult(TelemetryBase):
    """Warrior scanner evaluation results."""
    __tablename__ = "warrior_scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)  # UTC
    symbol = Column(String(10), nullable=False, index=True)
    result = Column(String(10), nullable=False)  # PASS or FAIL
    gap_pct = Column(Float, nullable=True)
    rvol = Column(Float, nullable=True)
    score = Column(Integer, nullable=True)  # Candidate score (0-16), computed even for FAIL
    float_shares = Column(BigInteger, nullable=True)
    reason = Column(String(100), nullable=True)  # Rejection reason (null for PASS)
    catalyst_type = Column(String(50), nullable=True)
    catalyst_source = Column(String(20), nullable=True)  # calendar, regex, ai, former_runner
    
    # Extended telemetry columns (Feb 2026)
    price = Column(Float, nullable=True)  # Last price at scan time
    country = Column(String(10), nullable=True)  # Country code (US, CN, HK)

    ema_200 = Column(Float, nullable=True)  # 200-day EMA value
    room_to_ema_pct = Column(Float, nullable=True)  # % position vs 200 EMA (+ve = above, -ve = below)
    is_etb = Column(String(5), nullable=True)  # Easy to borrow status (True/False/None)
    name = Column(String(100), nullable=True)  # Company name

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": format_iso_utc(self.timestamp),
            "symbol": self.symbol,
            "result": self.result,
            "gap_pct": self.gap_pct,
            "rvol": self.rvol,
            "score": self.score,
            "float_shares": self.float_shares,
            "reason": self.reason,
            "catalyst_type": self.catalyst_type,
            "catalyst_source": self.catalyst_source,
            # Extended telemetry columns
            "price": self.price,
            "country": self.country,

            "ema_200": self.ema_200,
            "room_to_ema_pct": self.room_to_ema_pct,
            "is_etb": self.is_etb,
            "name": self.name,
        }


class NACScanResult(TelemetryBase):
    """NAC (KK-style) scanner evaluation results."""
    __tablename__ = "nac_scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)  # UTC
    symbol = Column(String(10), nullable=False, index=True)
    result = Column(String(10), nullable=False)  # PASS or FAIL
    gap_pct = Column(Float, nullable=True)
    rvol = Column(Float, nullable=True)
    score = Column(Integer, nullable=True)
    float_shares = Column(BigInteger, nullable=True)
    reason = Column(String(100), nullable=True)
    catalyst_type = Column(String(50), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": format_iso_utc(self.timestamp),
            "symbol": self.symbol,
            "result": self.result,
            "gap_pct": self.gap_pct,
            "rvol": self.rvol,
            "score": self.score,
            "float_shares": self.float_shares,
            "reason": self.reason,
            "catalyst_type": self.catalyst_type,
        }


class CatalystAudit(TelemetryBase):
    """Catalyst evaluation audit records."""
    __tablename__ = "catalyst_audits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)  # UTC
    symbol = Column(String(10), nullable=False, index=True)
    result = Column(String(10), nullable=False)  # PASS or FAIL
    headline = Column(Text, nullable=True)  # The evaluated headline
    article_url = Column(Text, nullable=True)  # Link to source article
    source = Column(String(50), nullable=True)  # FMP, Benzinga, etc.
    match_type = Column(String(50), nullable=True)  # earnings, contract, fda, etc.
    confidence = Column(String(20), nullable=True)  # Evaluation method: consensus|tiebreaker|flash_only|regex_only|calendar

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": format_iso_utc(self.timestamp),
            "symbol": self.symbol,
            "result": self.result,
            "headline": self.headline,
            "article_url": self.article_url,
            "source": self.source,
            "match_type": self.match_type,
            "confidence": self.confidence,
        }


class AIComparison(TelemetryBase):
    """AI model comparison records for catalyst classification."""
    __tablename__ = "ai_comparisons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)  # UTC
    symbol = Column(String(10), nullable=False, index=True)
    headline = Column(Text, nullable=True)
    article_url = Column(Text, nullable=True)  # Link to source article
    source = Column(String(50), nullable=True)  # FMP, Benzinga, etc.
    regex_result = Column(String(50), nullable=True)
    flash_result = Column(String(50), nullable=True)
    pro_result = Column(String(50), nullable=True)
    final_result = Column(String(50), nullable=True)
    winner = Column(String(20), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": format_iso_utc(self.timestamp),
            "symbol": self.symbol,
            "headline": self.headline,
            "article_url": self.article_url,
            "source": self.source,
            "regex_result": self.regex_result,
            "flash_result": self.flash_result,
            "pro_result": self.pro_result,
            "final_result": self.final_result,
            "winner": self.winner,
        }


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def get_telemetry_engine():
    """Get the SQLAlchemy engine for telemetry DB."""
    return telemetry_engine


@contextmanager
def get_telemetry_session():
    """Context manager for Telemetry database sessions."""
    db = TelemetrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_telemetry_columns():
    """Add missing columns to existing telemetry tables (SQLite migration).
    
    SQLAlchemy's create_all() creates missing TABLES but does NOT add missing
    COLUMNS to existing tables. This function handles schema evolution for
    columns added after initial table creation.
    """
    import sqlite3
    conn = sqlite3.connect(str(TELEMETRY_DB_PATH))
    cursor = conn.cursor()
    
    # Define expected columns and their SQLite types
    expected_columns = {
        "warrior_scan_results": {
            "price": "REAL",
            "country": "VARCHAR(10)",
            "ema_200": "REAL",
            "room_to_ema_pct": "REAL",
            "is_etb": "VARCHAR(5)",
            "name": "VARCHAR(100)",
            "catalyst_source": "VARCHAR(20)",
        }
    }
    
    for table, columns in expected_columns.items():
        # Get existing columns
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        
        if not existing:
            # Table doesn't exist yet — create_all() will handle it
            continue
        
        # Add missing columns
        for col_name, col_type in columns.items():
            if col_name not in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    print(f"[Telemetry DB] Added column {table}.{col_name}")
                except Exception as e:
                    print(f"[Telemetry DB] Column migration failed for {table}.{col_name}: {e}")
    
    conn.commit()
    conn.close()


def init_telemetry_db():
    """Initialize Telemetry database tables."""
    TelemetryBase.metadata.create_all(bind=telemetry_engine)
    _migrate_telemetry_columns()
    print(f"[Telemetry DB] Initialized at {TELEMETRY_DB_PATH}")


# Auto-initialize on import
init_telemetry_db()
