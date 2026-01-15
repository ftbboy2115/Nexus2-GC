"""
Paper Broker

Local simulation broker for testing without API calls.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from nexus2.adapters.broker.protocol import (
    BrokerOrder,
    BrokerOrderStatus,
    BrokerFill,
    BrokerPosition,
)
from nexus2.utils.time_utils import now_et


class PaperBrokerError(Exception):
    """Paper broker error."""
    pass


class OrderNotFoundError(PaperBrokerError):
    """Order not found in paper broker."""
    pass


@dataclass
class PaperBrokerConfig:
    """Configuration for paper broker."""
    initial_cash: Decimal = Decimal("100000")
    fill_mode: str = "instant"      # "instant", "partial"
    slippage_bps: int = 0           # Basis points of slippage
    partial_fill_pct: int = 50      # Percentage per partial fill


class PaperBroker:
    """
    Local simulation broker.
    
    Provides instant or simulated fills without network calls.
    Perfect for testing and backtesting.
    """
    
    def __init__(self, config: Optional[PaperBrokerConfig] = None):
        self.config = config or PaperBrokerConfig()
        
        # State
        self._orders: Dict[str, BrokerOrder] = {}
        self._positions: Dict[str, BrokerPosition] = {}
        self._cash: Decimal = self.config.initial_cash
        self._fills: List[BrokerFill] = []
        
        # Order ID counter
        self._order_counter = 0
    
    def _generate_broker_id(self) -> str:
        """Generate unique broker order ID."""
        self._order_counter += 1
        return f"PAPER-{self._order_counter:06d}"
    
    def _apply_slippage(self, price: Decimal, side: str) -> Decimal:
        """Apply slippage to fill price."""
        if self.config.slippage_bps == 0:
            return price
        
        slippage = price * Decimal(self.config.slippage_bps) / Decimal("10000")
        if side == "buy":
            return price + slippage  # Pay more
        return price - slippage  # Receive less
    
    def submit_order(
        self,
        client_order_id: UUID,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
    ) -> BrokerOrder:
        """
        Submit order to paper broker.
        
        In instant mode, fills immediately.
        """
        broker_id = self._generate_broker_id()
        now = now_et()
        
        # Determine fill price
        if order_type == "market":
            # Market orders need a price - use limit or a default
            fill_price = limit_price or Decimal("100.00")
        else:
            fill_price = limit_price or Decimal("100.00")
        
        fill_price = self._apply_slippage(fill_price, side)
        
        order = BrokerOrder(
            client_order_id=client_order_id,
            broker_order_id=broker_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            status=BrokerOrderStatus.ACCEPTED,
            submitted_at=now,
        )
        
        self._orders[broker_id] = order
        
        # Handle fill based on mode
        if self.config.fill_mode == "instant":
            self._fill_order(order, quantity, fill_price, now)
        elif self.config.fill_mode == "partial":
            # Fill partial amount
            partial_qty = max(1, int(quantity * self.config.partial_fill_pct / 100))
            self._fill_order(order, partial_qty, fill_price, now)
        
        return order
    
    def submit_bracket_order(
        self,
        client_order_id: UUID,
        symbol: str,
        quantity: int,
        stop_loss_price: Decimal,
        limit_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
    ) -> BrokerOrder:
        """
        Submit a bracket order (entry + stop-loss).
        
        For paper broker, this just delegates to submit_order and
        stores the stop_loss_price for future reference.
        """
        # Submit the entry order
        order = self.submit_order(
            client_order_id=client_order_id,
            symbol=symbol,
            side="buy",
            quantity=quantity,
            order_type="limit" if limit_price else "market",
            limit_price=limit_price,
            stop_price=stop_loss_price,  # Store stop for reference
        )
        
        # In a real implementation, we'd also create the stop-loss order
        # For paper broker, the stop_price is stored on the order
        
        return order
    
    def _fill_order(
        self,
        order: BrokerOrder,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
    ) -> None:
        """Record a fill on an order."""
        # Create fill record
        fill = BrokerFill(
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
        )
        self._fills.append(fill)
        
        # Update order
        order.filled_quantity += quantity
        
        # Update average price
        if order.avg_fill_price is None:
            order.avg_fill_price = price
        else:
            # Weighted average
            prev_value = order.avg_fill_price * (order.filled_quantity - quantity)
            new_value = price * quantity
            order.avg_fill_price = (prev_value + new_value) / order.filled_quantity
        
        # Update status
        if order.filled_quantity >= order.quantity:
            order.status = BrokerOrderStatus.FILLED
            order.filled_at = timestamp
        else:
            order.status = BrokerOrderStatus.PARTIALLY_FILLED
        
        # Update position
        self._update_position(order.symbol, order.side, quantity, price)
        
        # Update cash
        value = price * quantity
        if order.side == "buy":
            self._cash -= value
        else:
            self._cash += value
    
    def _update_position(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: Decimal,
    ) -> None:
        """Update position after fill."""
        if symbol not in self._positions:
            self._positions[symbol] = BrokerPosition(
                symbol=symbol,
                quantity=0,
                avg_price=Decimal("0"),
                market_value=Decimal("0"),
                unrealized_pnl=Decimal("0"),
            )
        
        pos = self._positions[symbol]
        
        if side == "buy":
            # Add to position
            new_qty = pos.quantity + quantity
            if new_qty > 0:
                # Weighted average price
                old_value = pos.avg_price * pos.quantity
                new_value = price * quantity
                pos.avg_price = (old_value + new_value) / new_qty
            pos.quantity = new_qty
        else:
            # Reduce position
            pos.quantity -= quantity
        
        pos.market_value = price * pos.quantity
        
        # Remove if flat
        if pos.quantity == 0:
            del self._positions[symbol]
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrder:
        """Cancel an order."""
        order = self._orders.get(broker_order_id)
        if not order:
            raise OrderNotFoundError(f"Order not found: {broker_order_id}")
        
        if order.is_complete:
            raise PaperBrokerError(f"Cannot cancel completed order: {broker_order_id}")
        
        order.status = BrokerOrderStatus.CANCELLED
        return order
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrder:
        """Get order status."""
        order = self._orders.get(broker_order_id)
        if not order:
            raise OrderNotFoundError(f"Order not found: {broker_order_id}")
        return order
    
    def get_positions(self) -> Dict[str, BrokerPosition]:
        """Get all positions."""
        return dict(self._positions)
    
    def get_account_value(self) -> Decimal:
        """Get total account value (cash + positions)."""
        position_value = sum(p.market_value for p in self._positions.values())
        return self._cash + position_value
    
    def get_pending_fills(self, since: Optional[datetime] = None) -> List[BrokerFill]:
        """Get fills since a timestamp."""
        if since is None:
            return list(self._fills)
        return [f for f in self._fills if f.timestamp > since]
    
    def simulate_partial_fill(self, broker_order_id: str) -> BrokerOrder:
        """
        Manually trigger a partial fill on a pending order.
        
        Useful for testing partial fill scenarios.
        """
        order = self._orders.get(broker_order_id)
        if not order:
            raise OrderNotFoundError(f"Order not found: {broker_order_id}")
        
        if order.is_complete:
            raise PaperBrokerError(f"Order already complete: {broker_order_id}")
        
        remaining = order.remaining_quantity
        if remaining == 0:
            return order
        
        fill_qty = max(1, remaining // 2)
        fill_price = order.limit_price or Decimal("100.00")
        fill_price = self._apply_slippage(fill_price, order.side)
        
        self._fill_order(order, fill_qty, fill_price, now_et())
        return order
