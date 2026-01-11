"""
Tests for Positions Domain

Tests PositionService and TradeManagementService.
"""

import pytest
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from nexus2.domain.positions import (
    PositionService,
    PositionError,
    PositionNotFoundError,
    TradeManagementService,
    ManagedTrade,
    TradeStatus,
    ExitReason,
)
from nexus2.domain.orders import (
    Order,
    OrderStatus,
    OrderType,
    OrderSide,
    Fill,
)
from nexus2.settings.risk_settings import PartialExitSettings


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def position_service():
    """Fresh position service."""
    return PositionService()


@pytest.fixture
def partial_settings():
    """Default partial exit settings."""
    return PartialExitSettings()


@pytest.fixture
def trade_service(partial_settings):
    """Trade management service."""
    return TradeManagementService(partial_settings)


@pytest.fixture
def filled_order():
    """A filled buy order."""
    order = Order(
        id=uuid4(),
        symbol="NVDA",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=Decimal("450.00"),
        tactical_stop=Decimal("445.00"),
        status=OrderStatus.FILLED,
        filled_quantity=100,
        avg_fill_price=Decimal("450.00"),
        filled_at=datetime.now(),
    )
    return order


@pytest.fixture
def open_trade():
    """An open managed trade."""
    return ManagedTrade(
        id=uuid4(),
        symbol="AAPL",
        setup_type="ep",
        entry_date=date.today(),
        entry_time=datetime.now(),
        entry_price=Decimal("175.00"),
        shares=100,
        initial_stop=Decimal("172.00"),
        initial_risk_dollars=Decimal("300"),  # $3 * 100 shares
        current_stop=Decimal("172.00"),
        stop_type="initial",
        status=TradeStatus.OPEN,
        remaining_shares=100,
    )


# ============================================================================
# PositionService Tests
# ============================================================================

class TestPositionService:
    """Tests for PositionService."""
    
    def test_create_from_filled_order(self, position_service, filled_order):
        """Can create position from filled order."""
        trade = position_service.create_from_order(filled_order, setup_type="ep")
        
        assert trade.symbol == "NVDA"
        assert trade.entry_price == Decimal("450.00")
        assert trade.shares == 100
        assert trade.initial_stop == Decimal("445.00")
        assert trade.status == TradeStatus.OPEN
    
    def test_reject_unfilled_order(self, position_service):
        """Cannot create position from unfilled order."""
        order = Order(
            id=uuid4(),
            symbol="NVDA",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            status=OrderStatus.PENDING,
        )
        
        with pytest.raises(PositionError):
            position_service.create_from_order(order)
    
    def test_reject_duplicate_symbol(self, position_service, filled_order):
        """Cannot create second position for same symbol."""
        position_service.create_from_order(filled_order)
        
        with pytest.raises(PositionError) as exc_info:
            position_service.create_from_order(filled_order)
        
        assert "already exists" in str(exc_info.value)
    
    def test_add_to_position(self, position_service, filled_order):
        """Can add shares to existing position."""
        trade = position_service.create_from_order(filled_order)
        
        # Create add order
        add_order = Order(
            id=uuid4(),
            symbol="NVDA",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=50,
            status=OrderStatus.FILLED,
            filled_quantity=50,
            avg_fill_price=Decimal("455.00"),
            filled_at=datetime.now(),
        )
        
        updated = position_service.add_to_position(trade.id, add_order)
        
        assert updated.shares == 150
        # Weighted avg: (100*450 + 50*455) / 150 = 67750/150 = 451.67
        expected_avg = (Decimal("100") * Decimal("450") + Decimal("50") * Decimal("455")) / Decimal("150")
        assert abs(updated.entry_price - expected_avg) < Decimal("0.01")
    
    def test_get_position_by_symbol(self, position_service, filled_order):
        """Can retrieve position by symbol."""
        position_service.create_from_order(filled_order)
        
        trade = position_service.get_position_by_symbol("NVDA")
        
        assert trade is not None
        assert trade.symbol == "NVDA"
    
    def test_get_open_positions(self, position_service, filled_order):
        """get_open_positions returns only open trades."""
        trade = position_service.create_from_order(filled_order)
        
        open_trades = position_service.get_open_positions()
        
        assert len(open_trades) == 1
        assert open_trades[0].id == trade.id
    
    def test_update_stop_tighten(self, position_service, filled_order):
        """Can tighten stop."""
        trade = position_service.create_from_order(filled_order)
        assert trade.current_stop == Decimal("445.00")
        
        updated = position_service.update_stop(trade.id, Decimal("447.00"))
        
        assert updated.current_stop == Decimal("447.00")
        assert updated.stop_type == "trailing"
    
    def test_update_stop_reject_loosen(self, position_service, filled_order):
        """Cannot loosen stop."""
        trade = position_service.create_from_order(filled_order)
        
        with pytest.raises(PositionError) as exc_info:
            position_service.update_stop(trade.id, Decimal("440.00"))
        
        assert "loosen" in str(exc_info.value).lower()


# ============================================================================
# TradeManagementService Tests
# ============================================================================

class TestTradeManagement:
    """Tests for TradeManagementService."""
    
    def test_check_stop_hit(self, trade_service, open_trade):
        """Detects when stop is hit."""
        # Price below stop
        signal = trade_service.check_stop_hit(open_trade, Decimal("171.00"))
        
        assert signal is not None
        assert signal.reason == ExitReason.INITIAL_STOP
        assert signal.shares == 100
    
    def test_no_stop_hit_above(self, trade_service, open_trade):
        """No signal when price above stop."""
        signal = trade_service.check_stop_hit(open_trade, Decimal("180.00"))
        
        assert signal is None
    
    def test_execute_partial_exit(self, trade_service, open_trade):
        """Can execute partial exit."""
        updated = trade_service.execute_partial_exit(
            open_trade,
            shares=50,
            exit_price=Decimal("185.00"),
            reason=ExitReason.PARTIAL_PROFIT,
        )
        
        assert updated.remaining_shares == 50
        assert updated.status == TradeStatus.PARTIAL_EXIT
        assert len(updated.partial_exits) == 1
        # P&L: (185 - 175) * 50 = $500
        assert updated.realized_pnl == Decimal("500")
    
    def test_close_trade(self, trade_service, open_trade):
        """Can close full trade."""
        closed = trade_service.close_trade(
            open_trade,
            exit_price=Decimal("190.00"),
            reason=ExitReason.TRAILING_STOP,
        )
        
        assert closed.status == TradeStatus.CLOSED
        assert closed.remaining_shares == 0
        assert closed.final_exit_price == Decimal("190.00")
        # P&L: (190 - 175) * 100 = $1500
        assert closed.realized_pnl == Decimal("1500")
    
    def test_calculate_performance(self, open_trade):
        """Performance calculation is correct."""
        perf = open_trade.calculate_performance(Decimal("180.00"))
        
        # Unrealized: (180 - 175) * 100 = $500
        assert perf.unrealized_pnl == Decimal("500")
        assert perf.days_held == 0  # Same day
        # R multiple: 500 / 300 = 1.67
        assert abs(perf.r_multiple - Decimal("1.67")) < Decimal("0.01")


# ============================================================================
# Integration Tests
# ============================================================================

class TestPositionIntegration:
    """Integration tests for position workflow."""
    
    def test_full_trade_lifecycle(self, position_service, trade_service, filled_order):
        """Complete lifecycle: order → position → partial → close."""
        # 1. Create position from order
        trade = position_service.create_from_order(filled_order, setup_type="ep")
        assert trade.status == TradeStatus.OPEN
        
        # 2. Take partial profit
        trade = trade_service.execute_partial_exit(
            trade,
            shares=50,
            exit_price=Decimal("460.00"),
            reason=ExitReason.PARTIAL_PROFIT,
        )
        assert trade.remaining_shares == 50
        assert trade.status == TradeStatus.PARTIAL_EXIT
        
        # 3. Close remaining
        trade = trade_service.close_trade(
            trade,
            exit_price=Decimal("470.00"),
            reason=ExitReason.TRAILING_STOP,
        )
        assert trade.status == TradeStatus.CLOSED
        assert trade.remaining_shares == 0
        
        # Total P&L: (460-450)*50 + (470-450)*50 = 500 + 1000 = 1500
        assert trade.realized_pnl == Decimal("1500")
