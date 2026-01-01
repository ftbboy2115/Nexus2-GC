"""
Tests for Orders Domain

Tests order lifecycle, state machine, and KK-style rule enforcement.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from nexus2.domain.orders import (
    Order,
    OrderRequest,
    OrderStatus,
    OrderType,
    OrderSide,
    Fill,
    OrderService,
    can_transition,
    validate_transition,
    InvalidTransitionError,
    AddOnWeaknessError,
    StopLooseningError,
    ATRConstraintError,
    OrderNotFoundError,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def order_service():
    """Fresh order service for each test."""
    return OrderService()


@pytest.fixture
def basic_request():
    """Basic buy order request."""
    return OrderRequest(
        symbol="NVDA",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("450.00"),
        tactical_stop=Decimal("448.00"),  # $2 stop
        atr=Decimal("3.00"),  # Stop is 0.67 ATR (valid)
        risk_dollars=Decimal("200"),
    )


@pytest.fixture
def wide_stop_request():
    """Request with stop exceeding 1x ATR."""
    return OrderRequest(
        symbol="WIDE",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("100.00"),
        tactical_stop=Decimal("95.00"),  # $5 stop
        atr=Decimal("3.00"),  # Stop is 1.67 ATR (INVALID)
        risk_dollars=Decimal("500"),
    )


# ============================================================================
# State Machine Tests
# ============================================================================

class TestStateMachine:
    """Tests for order state transitions."""
    
    def test_valid_draft_to_pending(self):
        """DRAFT -> PENDING is valid."""
        assert can_transition(OrderStatus.DRAFT, OrderStatus.PENDING)
    
    def test_valid_draft_to_cancelled(self):
        """DRAFT -> CANCELLED is valid."""
        assert can_transition(OrderStatus.DRAFT, OrderStatus.CANCELLED)
    
    def test_valid_pending_to_filled(self):
        """PENDING -> FILLED is valid."""
        assert can_transition(OrderStatus.PENDING, OrderStatus.FILLED)
    
    def test_valid_pending_to_partially_filled(self):
        """PENDING -> PARTIALLY_FILLED is valid."""
        assert can_transition(OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED)
    
    def test_valid_partial_to_filled(self):
        """PARTIALLY_FILLED -> FILLED is valid."""
        assert can_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)
    
    def test_invalid_draft_to_filled(self):
        """DRAFT -> FILLED is invalid (must go through PENDING)."""
        assert not can_transition(OrderStatus.DRAFT, OrderStatus.FILLED)
    
    def test_invalid_filled_to_anywhere(self):
        """FILLED is terminal, cannot transition."""
        assert not can_transition(OrderStatus.FILLED, OrderStatus.CANCELLED)
        assert not can_transition(OrderStatus.FILLED, OrderStatus.PENDING)
    
    def test_validate_raises_on_invalid(self):
        """validate_transition raises on invalid transition."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(OrderStatus.FILLED, OrderStatus.PENDING)
        
        assert "filled" in str(exc_info.value).lower()


# ============================================================================
# Order Lifecycle Tests
# ============================================================================

class TestOrderLifecycle:
    """Tests for order creation and lifecycle."""
    
    def test_create_order_draft_status(self, order_service, basic_request):
        """New orders start in DRAFT status."""
        order = order_service.create_order(basic_request)
        
        assert order.status == OrderStatus.DRAFT
        assert order.symbol == "NVDA"
        assert order.quantity == 100
        assert order.filled_quantity == 0
    
    def test_submit_order_transitions_to_pending(self, order_service, basic_request):
        """Submitting order transitions to PENDING."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        
        assert order.status == OrderStatus.PENDING
        assert order.submitted_at is not None
    
    def test_cancel_draft_order(self, order_service, basic_request):
        """Can cancel order in DRAFT status."""
        order = order_service.create_order(basic_request)
        order = order_service.cancel_order(order.id)
        
        assert order.status == OrderStatus.CANCELLED
        assert order.cancelled_at is not None
    
    def test_cancel_pending_order(self, order_service, basic_request):
        """Can cancel order in PENDING status."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        order = order_service.cancel_order(order.id)
        
        assert order.status == OrderStatus.CANCELLED
    
    def test_record_full_fill(self, order_service, basic_request):
        """Recording full fill transitions to FILLED."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        order = order_service.record_fill(
            order.id,
            quantity=100,
            price=Decimal("450.00"),
        )
        
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert order.avg_fill_price == Decimal("450.00")
        assert order.filled_at is not None
    
    def test_record_partial_fill(self, order_service, basic_request):
        """Recording partial fill transitions to PARTIALLY_FILLED."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        order = order_service.record_fill(
            order.id,
            quantity=50,
            price=Decimal("450.00"),
        )
        
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 50
        assert order.remaining_quantity == 50
    
    def test_multiple_fills_complete_order(self, order_service, basic_request):
        """Multiple partial fills complete the order."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        
        order = order_service.record_fill(order.id, 30, Decimal("449.00"))
        order = order_service.record_fill(order.id, 40, Decimal("450.00"))
        order = order_service.record_fill(order.id, 30, Decimal("451.00"))
        
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert len(order.fills) == 3
        # Weighted average: (30*449 + 40*450 + 30*451) / 100 = 45000/100 = 450
        assert order.avg_fill_price == Decimal("450.00")


# ============================================================================
# KK-Style Rule Tests
# ============================================================================

class TestKKRules:
    """Tests for KK-style trading rule enforcement."""
    
    def test_atr_constraint_valid(self, order_service, basic_request):
        """Order with stop <= 1x ATR is valid."""
        # basic_request has $2 stop with $3 ATR = 0.67 ratio
        order = order_service.create_order(basic_request)
        assert order is not None
        assert order.stop_atr_ratio < Decimal("1.0")
    
    def test_atr_constraint_violation(self, order_service, wide_stop_request):
        """Order with stop > 1x ATR raises ATRConstraintError."""
        with pytest.raises(ATRConstraintError) as exc_info:
            order_service.create_order(wide_stop_request)
        
        assert exc_info.value.ratio > Decimal("1.0")
    
    def test_add_on_strength_valid(self, order_service, basic_request):
        """Can add when current price > avg price."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        order = order_service.record_fill(order.id, 100, Decimal("450.00"))
        
        # Current price $455 > avg $450 = adding on strength
        add_order = order_service.create_add_order(
            parent_order_id=order.id,
            quantity=50,
            current_price=Decimal("455.00"),
            position_avg_price=Decimal("450.00"),
        )
        
        assert add_order is not None
        assert add_order.is_add is True
        assert add_order.parent_order_id == order.id
    
    def test_add_on_weakness_violation(self, order_service, basic_request):
        """Cannot add when current price < avg price."""
        order = order_service.create_order(basic_request)
        order = order_service.submit_order(order.id)
        order = order_service.record_fill(order.id, 100, Decimal("450.00"))
        
        # Current price $445 < avg $450 = adding on weakness (VIOLATION)
        with pytest.raises(AddOnWeaknessError) as exc_info:
            order_service.create_add_order(
                parent_order_id=order.id,
                quantity=50,
                current_price=Decimal("445.00"),
                position_avg_price=Decimal("450.00"),
            )
        
        assert exc_info.value.current_price == Decimal("445.00")
    
    def test_tighten_stop_valid(self, order_service, basic_request):
        """Can raise stop (tighten) for long position."""
        order = order_service.create_order(basic_request)
        assert order.tactical_stop == Decimal("448.00")
        
        # Raise stop from $448 to $449
        order = order_service.update_stop(order.id, Decimal("449.00"))
        assert order.tactical_stop == Decimal("449.00")
    
    def test_loosen_stop_violation(self, order_service, basic_request):
        """Cannot lower stop (loosen) for long position."""
        order = order_service.create_order(basic_request)
        assert order.tactical_stop == Decimal("448.00")
        
        # Try to lower stop from $448 to $446 (VIOLATION)
        with pytest.raises(StopLooseningError) as exc_info:
            order_service.update_stop(order.id, Decimal("446.00"))
        
        assert exc_info.value.current_stop == Decimal("448.00")
        assert exc_info.value.new_stop == Decimal("446.00")


# ============================================================================
# Query Tests
# ============================================================================

class TestOrderQueries:
    """Tests for order queries."""
    
    def test_get_order_by_id(self, order_service, basic_request):
        """Can retrieve order by ID."""
        order = order_service.create_order(basic_request)
        retrieved = order_service.get_order(order.id)
        
        assert retrieved is not None
        assert retrieved.id == order.id
    
    def test_get_nonexistent_order_returns_none(self, order_service):
        """Getting nonexistent order returns None."""
        result = order_service.get_order(uuid4())
        assert result is None
    
    def test_get_open_orders(self, order_service, basic_request):
        """get_open_orders returns non-terminal orders."""
        order1 = order_service.create_order(basic_request)
        order2 = order_service.create_order(basic_request)
        order_service.submit_order(order1.id)
        order_service.cancel_order(order2.id)
        
        open_orders = order_service.get_open_orders()
        
        # order1 is PENDING (open), order2 is CANCELLED (closed)
        assert len(open_orders) == 1
        assert open_orders[0].id == order1.id
    
    def test_order_not_found_error(self, order_service):
        """Operations on nonexistent order raise OrderNotFoundError."""
        fake_id = uuid4()
        
        with pytest.raises(OrderNotFoundError):
            order_service.submit_order(fake_id)
