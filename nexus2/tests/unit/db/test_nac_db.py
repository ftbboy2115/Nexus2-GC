"""
Unit tests for NAC Database (nac_db.py)

Tests the PSM (Position State Machine) integration with order ID tracking.
"""
import pytest
from uuid import uuid4
from decimal import Decimal

# Use in-memory SQLite for testing
import sys
import os


@pytest.fixture(autouse=True)
def use_test_db(tmp_path, monkeypatch):
    """
    Override the NAC database path to use a temp in-memory database for tests.
    """
    # Set up a test database in temp directory
    test_db_path = tmp_path / "test_nac.db"
    monkeypatch.setenv("NAC_DB_PATH", str(test_db_path))
    
    # Import after patching to get fresh module with test path
    from nexus2.db import nac_db
    
    # Override the path at module level
    nac_db.NAC_DB_PATH = test_db_path
    nac_db.NAC_DATABASE_URL = f"sqlite:///{test_db_path}"
    
    # Recreate engine with new path
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    nac_db.nac_engine = create_engine(
        nac_db.NAC_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    nac_db.NACSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=nac_db.nac_engine
    )
    
    # Initialize tables
    nac_db.NACBase.metadata.create_all(bind=nac_db.nac_engine)
    
    yield nac_db
    
    # Cleanup - dispose engine to release file lock (Windows fix)
    nac_db.nac_engine.dispose()
    # Don't manually delete - let pytest's tmp_path handle cleanup


class TestNACEntry:
    """Tests for entry tracking functions."""
    
    def test_log_nac_entry_creates_pending_fill_record(self, use_test_db):
        """Entry should create a PENDING_FILL record."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        trade_id = str(uuid4())
        
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="AAPL",
            entry_price=150.00,
            quantity=100,
            stop_price=145.00,
            setup_type="ep",
        )
        
        # Verify record was created
        trade = nac_db.get_nac_trade_by_symbol("AAPL")
        
        assert trade is not None
        assert trade["symbol"] == "AAPL"
        assert trade["status"] == PositionStatus.PENDING_FILL.value
        assert float(trade["entry_price"]) == 150.00
        assert trade["quantity"] == 100
        assert float(trade["stop_price"]) == 145.00
        assert trade["setup_type"] == "ep"
    
    def test_set_entry_order_id(self, use_test_db):
        """Should store broker order ID for entry."""
        nac_db = use_test_db
        
        trade_id = str(uuid4())
        order_id = str(uuid4())
        
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="MSFT",
            entry_price=400.00,
            quantity=50,
            stop_price=390.00,
        )
        
        # Set order ID
        result = nac_db.set_entry_order_id(trade_id, order_id)
        
        assert result is True
        
        # Verify via lookup
        trade = nac_db.get_nac_trade_by_order_id(order_id)
        assert trade is not None
        assert trade["entry_order_id"] == order_id
    
    def test_confirm_fill_transitions_to_open(self, use_test_db):
        """confirm_fill should transition PENDING_FILL → OPEN."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        trade_id = str(uuid4())
        
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="GOOGL",
            entry_price=140.00,
            quantity=75,
            stop_price=135.00,
        )
        
        # Confirm fill
        result = nac_db.confirm_fill(trade_id, fill_price=140.50, filled_shares=75)
        
        assert result is True
        
        trade = nac_db.get_nac_trade_by_symbol("GOOGL")
        assert trade["status"] == PositionStatus.OPEN.value
        assert float(trade["entry_price"]) == 140.50  # Updated to fill price


class TestNACExit:
    """Tests for exit tracking functions."""
    
    def test_set_pending_exit_from_open(self, use_test_db):
        """Should transition OPEN → PENDING_EXIT."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        trade_id = str(uuid4())
        
        # Create and confirm an entry
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="NVDA",
            entry_price=800.00,
            quantity=10,
            stop_price=780.00,
        )
        nac_db.confirm_fill(trade_id)
        
        # Set pending exit
        result = nac_db.set_pending_exit(trade_id)
        
        assert result is True
        
        trade = nac_db.get_nac_trade_by_symbol("NVDA")
        assert trade["status"] == PositionStatus.PENDING_EXIT.value
    
    def test_set_pending_exit_fails_from_pending_fill(self, use_test_db):
        """Cannot exit a position that hasn't filled yet."""
        nac_db = use_test_db
        
        trade_id = str(uuid4())
        
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="AMZN",
            entry_price=180.00,
            quantity=50,
            stop_price=175.00,
        )
        
        # Try to exit without confirming fill
        result = nac_db.set_pending_exit(trade_id)
        
        assert result is False
    
    def test_confirm_exit_full_close(self, use_test_db):
        """Full exit should transition to CLOSED with P&L."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        trade_id = str(uuid4())
        
        # Create, confirm, and set pending exit
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="META",
            entry_price=500.00,
            quantity=20,
            stop_price=480.00,
        )
        nac_db.confirm_fill(trade_id)
        nac_db.set_pending_exit(trade_id)
        
        # Confirm exit
        result = nac_db.confirm_exit(
            trade_id=trade_id,
            exit_price=550.00,
            exit_reason="profit_target",
        )
        
        assert result is True
        
        # Use get_nac_trade_by_id since closed trades aren't returned by get_by_symbol
        trade = nac_db.get_nac_trade_by_id(trade_id)
        assert trade["status"] == PositionStatus.CLOSED.value
        assert float(trade["exit_price"]) == 550.00
        assert trade["exit_reason"] == "profit_target"
        # P&L = (550 - 500) * 20 = $1000
        assert float(trade["realized_pnl"]) == 1000.00
    
    def test_confirm_exit_partial(self, use_test_db):
        """Partial exit should transition to PARTIAL with remaining shares."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        trade_id = str(uuid4())
        
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="TSLA",
            entry_price=200.00,
            quantity=100,
            stop_price=190.00,
        )
        nac_db.confirm_fill(trade_id)
        nac_db.set_pending_exit(trade_id)
        
        # Partial exit - 50 shares
        result = nac_db.confirm_exit(
            trade_id=trade_id,
            exit_price=220.00,
            exit_reason="partial_exit",
            quantity_exited=50,
        )
        
        assert result is True
        
        trade = nac_db.get_nac_trade_by_symbol("TSLA")
        assert trade["status"] == PositionStatus.PARTIAL.value
        assert trade["remaining_quantity"] == 50
        assert trade["partial_taken"] is True
    
    def test_revert_pending_exit(self, use_test_db):
        """Revert should transition PENDING_EXIT → OPEN."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        trade_id = str(uuid4())
        
        nac_db.log_nac_entry(
            trade_id=trade_id,
            symbol="AMD",
            entry_price=150.00,
            quantity=50,
            stop_price=145.00,
        )
        nac_db.confirm_fill(trade_id)
        nac_db.set_pending_exit(trade_id)
        
        # Revert (exit order failed)
        result = nac_db.revert_pending_exit(trade_id)
        
        assert result is True
        
        trade = nac_db.get_nac_trade_by_symbol("AMD")
        assert trade["status"] == PositionStatus.OPEN.value
        assert trade["exit_order_id"] is None


class TestNACReconciliation:
    """Tests for startup reconciliation functions."""
    
    def test_get_pending_fills(self, use_test_db):
        """Should return all PENDING_FILL positions."""
        nac_db = use_test_db
        
        # Create multiple trades in different states
        id1 = str(uuid4())
        id2 = str(uuid4())
        id3 = str(uuid4())
        
        nac_db.log_nac_entry(trade_id=id1, symbol="AAPL", entry_price=150, quantity=10, stop_price=145)
        nac_db.log_nac_entry(trade_id=id2, symbol="MSFT", entry_price=400, quantity=10, stop_price=390)
        nac_db.log_nac_entry(trade_id=id3, symbol="GOOGL", entry_price=140, quantity=10, stop_price=135)
        
        # Confirm one
        nac_db.confirm_fill(id2)
        
        # Get pending fills
        pending = nac_db.get_pending_fills()
        
        assert len(pending) == 2
        symbols = [p["symbol"] for p in pending]
        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert "MSFT" not in symbols  # This one was confirmed
    
    def test_get_open_nac_trades(self, use_test_db):
        """Should return all active trades (any active state)."""
        nac_db = use_test_db
        
        id1 = str(uuid4())
        id2 = str(uuid4())
        id3 = str(uuid4())
        
        # Create trades in various states
        nac_db.log_nac_entry(trade_id=id1, symbol="AAPL", entry_price=150, quantity=10, stop_price=145)
        
        nac_db.log_nac_entry(trade_id=id2, symbol="MSFT", entry_price=400, quantity=10, stop_price=390)
        nac_db.confirm_fill(id2)
        
        nac_db.log_nac_entry(trade_id=id3, symbol="GOOGL", entry_price=140, quantity=10, stop_price=135)
        nac_db.confirm_fill(id3)
        nac_db.set_pending_exit(id3)
        nac_db.confirm_exit(id3, exit_price=150, exit_reason="profit")
        
        # Get all active
        active = nac_db.get_open_nac_trades()
        
        assert len(active) == 2  # AAPL (pending_fill) and MSFT (open)
        symbols = [p["symbol"] for p in active]
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "GOOGL" not in symbols  # This one is closed
    
    def test_close_orphaned_nac_trades(self, use_test_db):
        """Should close trades not present on broker."""
        nac_db = use_test_db
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        id1 = str(uuid4())
        id2 = str(uuid4())
        
        # Create two open trades
        nac_db.log_nac_entry(trade_id=id1, symbol="AAPL", entry_price=150, quantity=10, stop_price=145)
        nac_db.confirm_fill(id1)
        
        nac_db.log_nac_entry(trade_id=id2, symbol="MSFT", entry_price=400, quantity=10, stop_price=390)
        nac_db.confirm_fill(id2)
        
        # Broker only has AAPL
        broker_symbols = {"AAPL"}
        
        closed = nac_db.close_orphaned_nac_trades(broker_symbols)
        
        assert "MSFT" in closed
        assert len(closed) == 1
        
        # Verify MSFT is closed
        msft = nac_db.get_nac_trade_by_symbol("MSFT")
        assert msft is None  # Should not be in active trades


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
