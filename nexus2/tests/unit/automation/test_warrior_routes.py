"""
Unit tests for Warrior API routes.
"""

import pytest


class TestCancelOrdersEndpoint:
    """Test the DELETE /warrior/orders/{symbol} endpoint logic."""
    
    def test_cancel_endpoint_exists(self):
        """Test cancel orders function exists in warrior_broker_routes."""
        from nexus2.api.routes import warrior_broker_routes
        assert hasattr(warrior_broker_routes, 'cancel_orders_for_symbol')
        assert callable(warrior_broker_routes.cancel_orders_for_symbol)
    
    def test_alpaca_broker_has_cancel_method(self):
        """Test AlpacaBroker has cancel_order method."""
        from nexus2.adapters.broker.alpaca_broker import AlpacaBroker
        assert hasattr(AlpacaBroker, 'cancel_order')
        assert hasattr(AlpacaBroker, 'get_open_orders')
    
    def test_cancel_reverts_pending_exit_status(self):
        """Test PSM status logic: cancel should revert PENDING_EXIT to OPEN."""
        from nexus2.domain.positions.position_state_machine import (
            PositionStatus, can_transition
        )
        
        # This is the expected transition when an exit order is cancelled
        assert can_transition(PositionStatus.PENDING_EXIT, PositionStatus.OPEN)
