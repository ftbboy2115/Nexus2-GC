"""
Tests for Order ID Linkage functionality.

Tests the connection between position_id and broker order_id:
- set_entry_order_id stores linkage
- get_warrior_trade_by_order_id retrieves by order ID
- Sync recovery preserves original position_id and trigger_type
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

# Import the functions we're testing
from nexus2.db.warrior_db import (
    get_warrior_trade_by_order_id,
    set_entry_order_id,
    log_warrior_entry,
    get_warrior_trade_by_symbol,
    get_open_warrior_trades,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    with patch('nexus2.db.warrior_db.get_warrior_session') as mock:
        session = MagicMock()
        mock.return_value.__enter__ = MagicMock(return_value=session)
        mock.return_value.__exit__ = MagicMock(return_value=False)
        yield session


@pytest.fixture
def sample_trade():
    """Sample trade data."""
    return {
        "id": "order-123-abc",
        "symbol": "LCFY",
        "entry_price": "6.50",
        "quantity": 100,
        "stop_price": "6.35",
        "target_price": "6.80",
        "trigger_type": "pmh_break",
        "status": "open",
        "entry_order_id": "order-123-abc",
    }


# =============================================================================
# get_warrior_trade_by_order_id Tests
# =============================================================================

class TestGetWarriorTradeByOrderId:
    """Tests for get_warrior_trade_by_order_id function."""

    def test_returns_trade_when_found(self, mock_db_session, sample_trade):
        """Returns trade dict when order_id matches."""
        mock_trade = MagicMock()
        mock_trade.to_dict.return_value = sample_trade
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_trade

        result = get_warrior_trade_by_order_id("order-123-abc")

        assert result == sample_trade
        mock_db_session.query.return_value.filter_by.assert_called_with(
            entry_order_id="order-123-abc"
        )

    def test_returns_none_when_not_found(self, mock_db_session):
        """Returns None when no trade matches order_id."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        result = get_warrior_trade_by_order_id("nonexistent-order")

        assert result is None


# =============================================================================
# set_entry_order_id Tests
# =============================================================================

class TestSetEntryOrderId:
    """Tests for set_entry_order_id function."""

    def test_sets_order_id_on_existing_trade(self, mock_db_session):
        """Sets entry_order_id on existing trade."""
        mock_trade = MagicMock()
        mock_trade.entry_order_id = None
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_trade

        result = set_entry_order_id("trade-123", "alpaca-order-456")

        assert result is True
        assert mock_trade.entry_order_id == "alpaca-order-456"
        mock_db_session.commit.assert_called_once()

    def test_returns_false_when_trade_not_found(self, mock_db_session):
        """Returns False when trade doesn't exist."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        result = set_entry_order_id("nonexistent-trade", "order-123")

        assert result is False
        mock_db_session.commit.assert_not_called()


# =============================================================================
# Sync Recovery Tests
# =============================================================================

class TestSyncRecovery:
    """Tests for sync recovery using existing trade data."""

    def test_recover_existing_trade_preserves_trigger_type(self, mock_db_session, sample_trade):
        """Sync recovery should preserve original trigger_type."""
        mock_trade = MagicMock()
        mock_trade.to_dict.return_value = sample_trade
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_trade

        # Simulate what sync does - lookup existing trade
        existing = get_warrior_trade_by_symbol("LCFY")

        if existing:
            recovered_position_id = existing["id"]
            recovered_trigger_type = existing.get("trigger_type", "recovered")
        else:
            recovered_position_id = str(uuid4())
            recovered_trigger_type = "external"

        # Should preserve original values
        assert recovered_position_id == "order-123-abc"
        assert recovered_trigger_type == "pmh_break"

    def test_new_external_position_gets_external_trigger_type(self, mock_db_session):
        """New positions not in DB should get 'external' trigger_type."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        # Simulate sync for truly external position
        existing = get_warrior_trade_by_symbol("NEWSTOCK")

        if existing:
            position_id = existing["id"]
            trigger_type = existing.get("trigger_type", "recovered")
        else:
            position_id = str(uuid4())
            trigger_type = "external"

        # Should get new UUID and external trigger
        assert trigger_type == "external"
        assert len(position_id) == 36  # UUID length


# =============================================================================
# Integration with Warrior Engine
# =============================================================================

class TestOrderIdLinkageIntegration:
    """Integration tests for order ID linkage flow."""

    def test_entry_flow_stores_order_id(self, mock_db_session):
        """After order fill, entry_order_id should be stored."""
        # This tests the flow in warrior_engine.py
        mock_trade = MagicMock()
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_trade

        # Simulate what warrior_engine does after fill
        order_id = "alpaca-order-789"
        set_entry_order_id(order_id, order_id)

        assert mock_trade.entry_order_id == order_id

    def test_restart_recovery_uses_same_position_id(self, mock_db_session, sample_trade):
        """After restart, sync should recover same position_id."""
        mock_trade = MagicMock()
        mock_trade.to_dict.return_value = sample_trade
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_trade

        # After restart, lookup by order_id
        recovered = get_warrior_trade_by_order_id("order-123-abc")

        assert recovered is not None
        assert recovered["id"] == sample_trade["id"]
        assert recovered["trigger_type"] == "pmh_break"
