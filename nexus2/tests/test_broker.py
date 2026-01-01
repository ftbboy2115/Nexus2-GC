"""
Tests for Broker Adapters

Tests PaperBroker, AlpacaBroker (mocked), and OrderExecutor.
"""

import sys
import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, patch

# Mock httpx before importing AlpacaBroker
_mock_httpx = MagicMock()
_mock_httpx.Client = MagicMock
sys.modules['httpx'] = _mock_httpx

from nexus2.adapters.broker import (
    PaperBroker,
    PaperBrokerConfig,
    BrokerOrderStatus,
    OrderExecutor,
)
from nexus2.domain.orders import (
    OrderService,
    OrderRequest,
    OrderType,
    OrderSide,
    OrderStatus,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def paper_broker():
    """Paper broker with instant fills."""
    return PaperBroker(PaperBrokerConfig(
        initial_cash=Decimal("100000"),
        fill_mode="instant",
    ))


@pytest.fixture
def partial_broker():
    """Paper broker with partial fills."""
    return PaperBroker(PaperBrokerConfig(
        initial_cash=Decimal("100000"),
        fill_mode="partial",
        partial_fill_pct=50,
    ))


@pytest.fixture
def order_service():
    """Fresh order service."""
    return OrderService()


@pytest.fixture
def executor(order_service, paper_broker):
    """Order executor with paper broker."""
    return OrderExecutor(order_service, paper_broker)


@pytest.fixture
def basic_request():
    """Basic buy order request."""
    return OrderRequest(
        symbol="NVDA",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("450.00"),
    )


# ============================================================================
# PaperBroker Tests
# ============================================================================

class TestPaperBroker:
    """Tests for PaperBroker."""
    
    def test_submit_instant_fill(self, paper_broker):
        """Instant fill mode fills immediately."""
        order = paper_broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("450.00"),
        )
        
        assert order.status == BrokerOrderStatus.FILLED
        assert order.filled_quantity == 100
        assert order.avg_fill_price == Decimal("450.00")
    
    def test_submit_partial_fill(self, partial_broker):
        """Partial fill mode fills partially."""
        order = partial_broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("450.00"),
        )
        
        assert order.status == BrokerOrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 50  # 50% partial fill
        assert order.remaining_quantity == 50
    
    def test_cancel_order(self, partial_broker):
        """Can cancel partially filled order."""
        order = partial_broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("450.00"),
        )
        
        cancelled = partial_broker.cancel_order(order.broker_order_id)
        
        assert cancelled.status == BrokerOrderStatus.CANCELLED
        assert cancelled.filled_quantity == 50  # Keep partial fill
    
    def test_position_tracking(self, paper_broker):
        """Positions are tracked correctly."""
        paper_broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("450.00"),
        )
        
        positions = paper_broker.get_positions()
        
        assert "NVDA" in positions
        assert positions["NVDA"].quantity == 100
        assert positions["NVDA"].avg_price == Decimal("450.00")
    
    def test_cash_tracking(self, paper_broker):
        """Cash is updated after fills."""
        initial_cash = paper_broker.get_account_value()
        
        paper_broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("450.00"),
        )
        
        # Cash reduced, but position value added back
        # Net account value should stay same (no slippage)
        assert paper_broker.get_account_value() == initial_cash
    
    def test_slippage(self):
        """Slippage affects fill price."""
        broker = PaperBroker(PaperBrokerConfig(
            slippage_bps=10,  # 0.1% slippage
        ))
        
        order = broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("100.00"),
        )
        
        # Buy pays more with slippage
        assert order.avg_fill_price > Decimal("100.00")
    
    def test_simulate_partial_fill(self, partial_broker):
        """Can manually trigger additional partial fills."""
        order = partial_broker.submit_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("450.00"),
        )
        
        assert order.filled_quantity == 50
        
        # Trigger another partial
        order = partial_broker.simulate_partial_fill(order.broker_order_id)
        
        assert order.filled_quantity == 75  # 50 + 25 (half of remaining)


# ============================================================================
# OrderExecutor Tests
# ============================================================================

class TestOrderExecutor:
    """Tests for OrderExecutor."""
    
    def test_execute_pending_order(self, executor, order_service, basic_request):
        """Can execute a pending order."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        
        result = executor.execute_order(order.id)
        
        assert result.success
        assert result.broker_order.status == BrokerOrderStatus.FILLED
    
    def test_fills_sync_to_domain(self, executor, order_service, basic_request):
        """Fills from broker are recorded in domain."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        
        executor.execute_order(order.id)
        
        # Check domain order is updated
        updated = order_service.get_order(order.id)
        assert updated.status == OrderStatus.FILLED
        assert updated.filled_quantity == 100
        assert updated.avg_fill_price == Decimal("450.00")
    
    def test_cancel_via_executor(self, executor, order_service):
        """Can cancel order via executor."""
        # Use partial broker to avoid instant fill
        partial_config = PaperBrokerConfig(fill_mode="partial")
        partial_broker = PaperBroker(partial_config)
        exec_partial = OrderExecutor(order_service, partial_broker)
        
        request = OrderRequest(
            symbol="NVDA",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("450.00"),
        )
        order = order_service.create_order(request)
        order = order_service.submit_order(order.id)
        
        exec_partial.execute_order(order.id)
        
        # Now cancel
        cancelled = exec_partial.cancel_order(order.id)
        
        assert cancelled.status == OrderStatus.CANCELLED
    
    def test_sync_fills_updates_pending(self, order_service):
        """sync_fills updates pending orders."""
        partial_broker = PaperBroker(PaperBrokerConfig(fill_mode="partial"))
        executor = OrderExecutor(order_service, partial_broker)
        
        request = OrderRequest(
            symbol="NVDA",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("450.00"),
        )
        order = order_service.create_order(request)
        order = order_service.submit_order(order.id)
        
        # Execute (partial fill)
        result = executor.execute_order(order.id)
        assert result.broker_order.filled_quantity == 50
        
        # Manually fill more in broker
        partial_broker.simulate_partial_fill(result.broker_order.broker_order_id)
        
        # Sync should pick up new fills
        updated = executor.sync_fills()
        
        assert len(updated) == 1
        assert updated[0].filled_quantity == 75
    
    def test_get_pending_executions(self, order_service):
        """get_pending_executions returns unfilled orders."""
        partial_broker = PaperBroker(PaperBrokerConfig(fill_mode="partial"))
        executor = OrderExecutor(order_service, partial_broker)
        
        request = OrderRequest(
            symbol="NVDA",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("450.00"),
        )
        order = order_service.create_order(request)
        order = order_service.submit_order(order.id)
        executor.execute_order(order.id)
        
        pending = executor.get_pending_executions()
        
        assert order.id in pending


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """End-to-end integration tests."""
    
    def test_full_order_lifecycle(self, order_service, paper_broker):
        """Complete order lifecycle: create → submit → execute → fill."""
        executor = OrderExecutor(order_service, paper_broker)
        
        # 1. Create order in domain
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=50,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("175.00"),
        )
        order = order_service.create_order(request)
        assert order.status == OrderStatus.DRAFT
        
        # 2. Submit to domain
        order = order_service.submit_order(order.id)
        assert order.status == OrderStatus.PENDING
        
        # 3. Execute via broker
        result = executor.execute_order(order.id)
        assert result.success
        
        # 4. Verify fill propagated to domain
        final = order_service.get_order(order.id)
        assert final.status == OrderStatus.FILLED
        assert final.filled_quantity == 50
        assert final.avg_fill_price == Decimal("175.00")
        
        # 5. Verify broker position
        positions = paper_broker.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 50
