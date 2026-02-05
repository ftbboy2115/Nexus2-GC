"""
Unit Tests for Telemetry Database (telemetry_db.py)

Tests telemetry models, session management, and write operations.
Phase 4 of telemetry testing per handoff_telemetry_testing.md.
"""

import pytest
from nexus2.db.telemetry_db import (
    get_telemetry_session,
    WarriorScanResult,
    NACScanResult,
    CatalystAudit,
    AIComparison,
)
from nexus2.utils.time_utils import now_utc


# =============================================================================
# Test 1-4: Model Existence Tests
# =============================================================================

class TestTelemetryModels:
    """Test telemetry DB models exist with correct config."""
    
    def test_warrior_scan_result_model_exists(self):
        """Model exists with correct tablename."""
        assert WarriorScanResult.__tablename__ == "warrior_scan_results"
    
    def test_nac_scan_result_model_exists(self):
        """Model exists with correct tablename."""
        assert NACScanResult.__tablename__ == "nac_scan_results"
    
    def test_catalyst_audit_model_exists(self):
        """Model exists with correct tablename."""
        assert CatalystAudit.__tablename__ == "catalyst_audits"
    
    def test_ai_comparison_model_exists(self):
        """Model exists with correct tablename."""
        assert AIComparison.__tablename__ == "ai_comparisons"


# =============================================================================
# Test 5: Session Management
# =============================================================================

class TestTelemetrySession:
    """Test session management."""
    
    def test_get_telemetry_session_works(self):
        """Context manager yields session."""
        with get_telemetry_session() as db:
            assert db is not None


# =============================================================================
# Test 6-8: Write Operations
# =============================================================================

class TestTelemetryWrites:
    """Test write operations."""
    
    def test_can_write_warrior_scan_result(self):
        """Insert row, verify count."""
        with get_telemetry_session() as db:
            db.add(WarriorScanResult(
                timestamp=now_utc(),
                symbol="TEST_WSR",
                result="PASS",
                score=10,
            ))
            db.commit()
            assert db.query(WarriorScanResult).filter_by(symbol="TEST_WSR").count() >= 1
    
    def test_can_write_catalyst_audit(self):
        """Insert row, verify count."""
        with get_telemetry_session() as db:
            db.add(CatalystAudit(
                timestamp=now_utc(),
                symbol="TEST_CA",
                result="PASS",
                headline="Test headline",
            ))
            db.commit()
            assert db.query(CatalystAudit).filter_by(symbol="TEST_CA").count() >= 1
    
    def test_can_write_ai_comparison(self):
        """Insert row, verify count."""
        with get_telemetry_session() as db:
            db.add(AIComparison(
                timestamp=now_utc(),
                symbol="TEST_AIC",
                regex_result="PASS",
                flash_result="PASS",
                final_result="PASS",
            ))
            db.commit()
            assert db.query(AIComparison).filter_by(symbol="TEST_AIC").count() >= 1


# =============================================================================
# Test 9: to_dict() Serialization
# =============================================================================

class TestToDict:
    """Test serialization."""
    
    def test_warrior_scan_result_to_dict(self):
        """to_dict() has all expected fields."""
        row = WarriorScanResult(
            timestamp=now_utc(),
            symbol="TEST",
            result="PASS",
            score=10,
            gap_pct=5.5,
            rvol=2.1,
        )
        d = row.to_dict()
        assert "symbol" in d
        assert "timestamp" in d
        assert "score" in d
        assert "result" in d
        assert "gap_pct" in d
        assert "rvol" in d
    
    def test_catalyst_audit_to_dict(self):
        """to_dict() has all expected fields."""
        row = CatalystAudit(
            timestamp=now_utc(),
            symbol="TEST",
            result="PASS",
            headline="Test headline",
            article_url="https://example.com/article",
            source="FMP",
            match_type="earnings",
        )
        d = row.to_dict()
        assert "symbol" in d
        assert "timestamp" in d
        assert "headline" in d
        assert "article_url" in d
        assert "source" in d
        assert "match_type" in d
    
    def test_ai_comparison_to_dict(self):
        """to_dict() has all expected fields."""
        row = AIComparison(
            timestamp=now_utc(),
            symbol="TEST",
            regex_result="PASS",
            flash_result="PASS",
            pro_result="PASS",
            final_result="PASS",
            winner="regex",
        )
        d = row.to_dict()
        assert "symbol" in d
        assert "timestamp" in d
        assert "regex_result" in d
        assert "flash_result" in d
        assert "pro_result" in d
        assert "final_result" in d
        assert "winner" in d
