"""
Order Executor

Bridges OrderService (domain) and Broker (adapter).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Protocol
from uuid import UUID

from nexus2.domain.orders import (
    Order,
    OrderService,
    OrderStatus,
)
from nexus2.adapters.broker.protocol import (
    BrokerOrder,
    BrokerOrderStatus,
    BrokerProtocol,
)
from nexus2.utils.time_utils import now_et


class ExecutorError(Exception):
    """Executor error."""
    pass


class OrderNotSubmittedError(ExecutorError):
    """Order not in correct state to execute."""
    pass


@dataclass
class ExecutionResult:
    """Result of an execution attempt."""
    order: Order
    broker_order: BrokerOrder
    success: bool
    error: Optional[str] = None


class OrderExecutor:
    """
    Bridges domain OrderService and broker.
    
    Handles:
    - Submitting orders from domain to broker
    - Syncing fills from broker back to domain
    - Cancellation flow
    """
    
    def __init__(
        self,
        order_service: OrderService,
        broker: BrokerProtocol,
    ):
        self.order_service = order_service
        self.broker = broker
        
        # Track order_id -> broker_order_id mapping
        self._broker_orders: Dict[UUID, str] = {}
        
        # Last sync timestamp for incremental fill sync
        self._last_sync: Optional[datetime] = None
    
    def execute_order(self, order_id: UUID) -> ExecutionResult:
        """
        Submit a domain order to the broker.
        
        The order must be in PENDING status (already submitted in domain).
        
        Args:
            order_id: Domain order ID
            
        Returns:
            ExecutionResult with broker order
            
        Raises:
            OrderNotSubmittedError: If order not in PENDING status
        """
        order = self.order_service.get_order(order_id)
        if not order:
            raise ExecutorError(f"Order not found: {order_id}")
        
        if order.status != OrderStatus.PENDING:
            raise OrderNotSubmittedError(
                f"Order must be PENDING to execute, got {order.status}"
            )
        
        try:
            broker_order = self.broker.submit_order(
                client_order_id=order.id,
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                order_type=order.order_type.value,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
            )
            
            self._broker_orders[order.id] = broker_order.broker_order_id
            
            # If already filled, record in domain
            if broker_order.filled_quantity > 0:
                self._sync_order_fills(order, broker_order)
            
            return ExecutionResult(
                order=order,
                broker_order=broker_order,
                success=True,
            )
            
        except Exception as e:
            # Mark order as rejected in domain
            self.order_service.reject_order(order_id, str(e))
            return ExecutionResult(
                order=order,
                broker_order=None,  # type: ignore
                success=False,
                error=str(e),
            )
    
    def sync_fills(self) -> List[Order]:
        """
        Sync all pending orders with broker.
        
        Polls broker for order status and records fills in domain.
        
        Returns:
            List of orders that were updated
        """
        updated = []
        
        for order_id, broker_order_id in list(self._broker_orders.items()):
            order = self.order_service.get_order(order_id)
            if not order or order.is_complete:
                continue
            
            try:
                broker_order = self.broker.get_order_status(broker_order_id)
                
                if self._sync_order_fills(order, broker_order):
                    updated.append(order)
                    
            except Exception:
                # Skip orders we can't sync
                continue
        
        self._last_sync = now_et()
        return updated
    
    def _sync_order_fills(self, order: Order, broker_order: BrokerOrder) -> bool:
        """
        Sync fills from broker order to domain order.
        
        Returns True if order was updated.
        """
        # Check for new fills
        domain_filled = order.filled_quantity
        broker_filled = broker_order.filled_quantity
        
        if broker_filled <= domain_filled:
            return False
        
        # Record the delta as a fill
        new_fill_qty = broker_filled - domain_filled
        fill_price = broker_order.avg_fill_price or Decimal("0")
        
        self.order_service.record_fill(
            order_id=order.id,
            quantity=new_fill_qty,
            price=fill_price,
        )
        
        return True
    
    def cancel_order(self, order_id: UUID) -> Order:
        """
        Cancel an order via broker and update domain.
        
        Args:
            order_id: Domain order ID
            
        Returns:
            Updated domain order
        """
        broker_order_id = self._broker_orders.get(order_id)
        
        if broker_order_id:
            try:
                self.broker.cancel_order(broker_order_id)
            except Exception:
                # Best effort - still cancel in domain
                pass
        
        return self.order_service.cancel_order(order_id)
    
    def get_broker_order_id(self, order_id: UUID) -> Optional[str]:
        """Get broker order ID for a domain order."""
        return self._broker_orders.get(order_id)
    
    def get_pending_executions(self) -> List[UUID]:
        """Get order IDs that are pending at broker."""
        pending = []
        for order_id in self._broker_orders:
            order = self.order_service.get_order(order_id)
            if order and not order.is_complete:
                pending.append(order_id)
        return pending
