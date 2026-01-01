"""
Order Service

Order operations with KK-style validation.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
from uuid import UUID, uuid4

from nexus2.domain.orders.models import (
    Order,
    OrderRequest,
    OrderStatus,
    OrderSide,
    Fill,
)
from nexus2.domain.orders.state_machine import transition, validate_transition
from nexus2.domain.orders.exceptions import (
    AddOnWeaknessError,
    StopLooseningError,
    ATRConstraintError,
    OrderNotFoundError,
)


class OrderService:
    """
    Order operations with KK-style validation.
    
    All order lifecycle operations go through this service.
    KK-style rules are enforced at operation time.
    """
    
    # Maximum allowed stop distance as ATR multiple
    MAX_ATR_RATIO = Decimal("1.0")
    
    def __init__(self):
        # In-memory storage (repository pattern for future DB)
        self._orders: Dict[UUID, Order] = {}
    
    # =========================================================================
    # Order Lifecycle
    # =========================================================================
    
    def create_order(self, request: OrderRequest) -> Order:
        """
        Create a new order in DRAFT status.
        
        Validates KK-style ATR constraint if ATR provided.
        
        Args:
            request: Order creation request
            
        Returns:
            New Order in DRAFT status
            
        Raises:
            ATRConstraintError: If stop distance exceeds 1x ATR
        """
        order = Order(
            id=uuid4(),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            tactical_stop=request.tactical_stop,
            risk_dollars=request.risk_dollars,
            setup_id=request.setup_id,
            atr=request.atr,
            is_add=request.is_add,
            parent_order_id=request.parent_order_id,
            notes=request.notes,
            status=OrderStatus.DRAFT,
            created_at=datetime.now(),
        )
        
        # Validate ATR constraint for BUY orders with stop (skip for adds)
        if (
            order.side == OrderSide.BUY
            and order.tactical_stop
            and order.atr
            and order.limit_price
            and not order.is_add  # Skip for adds (parent already validated)
        ):
            self._validate_atr_constraint(order)
        
        self._orders[order.id] = order
        return order
    
    def submit_order(self, order_id: UUID) -> Order:
        """
        Submit an order for execution.
        
        Transitions from DRAFT to PENDING.
        
        Args:
            order_id: Order to submit
            
        Returns:
            Updated order in PENDING status
            
        Raises:
            OrderNotFoundError: If order not found
            InvalidTransitionError: If not in DRAFT status
        """
        order = self._get_order(order_id)
        transition(order, OrderStatus.PENDING)
        order.submitted_at = datetime.now()
        return order
    
    def cancel_order(self, order_id: UUID) -> Order:
        """
        Cancel an order.
        
        Valid from DRAFT, PENDING, or PARTIALLY_FILLED.
        
        Args:
            order_id: Order to cancel
            
        Returns:
            Updated order in CANCELLED status
            
        Raises:
            OrderNotFoundError: If order not found
            InvalidTransitionError: If in terminal status
        """
        order = self._get_order(order_id)
        transition(order, OrderStatus.CANCELLED)
        order.cancelled_at = datetime.now()
        return order
    
    def record_fill(
        self,
        order_id: UUID,
        quantity: int,
        price: Decimal,
        timestamp: Optional[datetime] = None,
        fee: Decimal = Decimal("0"),
    ) -> Order:
        """
        Record a fill on an order.
        
        Updates filled quantity and average price.
        Transitions to PARTIALLY_FILLED or FILLED.
        
        Args:
            order_id: Order that was filled
            quantity: Number of shares filled
            price: Fill price
            timestamp: Fill time (defaults to now)
            fee: Transaction fee
            
        Returns:
            Updated order
            
        Raises:
            OrderNotFoundError: If order not found
        """
        order = self._get_order(order_id)
        
        fill = Fill(
            quantity=quantity,
            price=price,
            timestamp=timestamp or datetime.now(),
            fee=fee,
        )
        
        order.record_fill(fill)
        return order
    
    def reject_order(self, order_id: UUID, reason: Optional[str] = None) -> Order:
        """
        Mark order as rejected by broker.
        
        Args:
            order_id: Order that was rejected
            reason: Rejection reason
            
        Returns:
            Updated order in REJECTED status
        """
        order = self._get_order(order_id)
        transition(order, OrderStatus.REJECTED)
        if reason:
            order.notes = f"Rejected: {reason}"
        return order
    
    def expire_order(self, order_id: UUID) -> Order:
        """
        Mark order as expired (time-in-force reached).
        
        Args:
            order_id: Order that expired
            
        Returns:
            Updated order in EXPIRED status
        """
        order = self._get_order(order_id)
        transition(order, OrderStatus.EXPIRED)
        return order
    
    # =========================================================================
    # KK-Style Operations
    # =========================================================================
    
    def create_add_order(
        self,
        parent_order_id: UUID,
        quantity: int,
        current_price: Decimal,
        position_avg_price: Decimal,
        limit_price: Optional[Decimal] = None,
    ) -> Order:
        """
        Create an add-to-position order.
        
        KK Rule: Can only add on strength (current > avg entry).
        
        Args:
            parent_order_id: Original order for this position
            quantity: Shares to add
            current_price: Current market price
            position_avg_price: Average price of existing position
            limit_price: Limit price for the add order
            
        Returns:
            New add order in DRAFT status
            
        Raises:
            OrderNotFoundError: If parent order not found
            AddOnWeaknessError: If current price < avg price
        """
        parent = self._get_order(parent_order_id)
        
        # KK Rule: No adds on weakness
        if current_price < position_avg_price:
            raise AddOnWeaknessError(current_price, position_avg_price)
        
        request = OrderRequest(
            symbol=parent.symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=parent.order_type,
            limit_price=limit_price or current_price,
            tactical_stop=parent.tactical_stop,
            atr=parent.atr,
            is_add=True,
            parent_order_id=parent_order_id,
            notes=f"Add to {parent.symbol} position",
        )
        
        return self.create_order(request)
    
    def update_stop(
        self,
        order_id: UUID,
        new_stop: Decimal,
    ) -> Order:
        """
        Update the tactical stop on an order.
        
        KK Rule: Stops can only be tightened (raised for longs).
        
        Args:
            order_id: Order to update
            new_stop: New stop price
            
        Returns:
            Updated order
            
        Raises:
            OrderNotFoundError: If order not found
            StopLooseningError: If new stop is lower than current
        """
        order = self._get_order(order_id)
        
        if order.tactical_stop is None:
            order.tactical_stop = new_stop
            return order
        
        # KK Rule: Can only tighten (raise) stop for long positions
        if order.side == OrderSide.BUY and new_stop < order.tactical_stop:
            raise StopLooseningError(order.tactical_stop, new_stop)
        
        # For shorts, can only lower stop (but we focus on longs)
        if order.side == OrderSide.SELL and new_stop > order.tactical_stop:
            raise StopLooseningError(order.tactical_stop, new_stop)
        
        order.tactical_stop = new_stop
        return order
    
    # =========================================================================
    # Queries
    # =========================================================================
    
    def get_order(self, order_id: UUID) -> Optional[Order]:
        """Get order by ID, returns None if not found."""
        return self._orders.get(order_id)
    
    def get_orders_by_symbol(self, symbol: str) -> list[Order]:
        """Get all orders for a symbol."""
        return [o for o in self._orders.values() if o.symbol == symbol]
    
    def get_open_orders(self) -> list[Order]:
        """Get all non-terminal orders."""
        return [o for o in self._orders.values() if not o.is_complete]
    
    # =========================================================================
    # Internal
    # =========================================================================
    
    def _get_order(self, order_id: UUID) -> Order:
        """Get order or raise OrderNotFoundError."""
        order = self._orders.get(order_id)
        if not order:
            raise OrderNotFoundError(order_id)
        return order
    
    def _validate_atr_constraint(self, order: Order) -> None:
        """
        Validate stop distance against ATR constraint.
        
        KK Rule: Stop distance must be <= 1.0 ATR.
        
        Raises:
            ATRConstraintError: If stop exceeds constraint
        """
        if not order.limit_price or not order.tactical_stop or not order.atr:
            return
        
        stop_distance = abs(order.limit_price - order.tactical_stop)
        ratio = stop_distance / order.atr
        
        if ratio > self.MAX_ATR_RATIO:
            raise ATRConstraintError(stop_distance, order.atr, ratio)
