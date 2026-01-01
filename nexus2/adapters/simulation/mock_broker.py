"""
Mock Broker

Simulates broker order execution for backtesting.
Same interface as AlpacaBroker for seamless integration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


class MockOrderStatus(Enum):
    """Mock order status."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class MockOrder:
    """Represents a mock order."""
    id: str
    symbol: str
    side: str  # buy, sell
    qty: int
    order_type: str  # market, limit, stop
    status: MockOrderStatus
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    avg_fill_price: Optional[float] = None
    filled_qty: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    
    # For bracket orders
    parent_id: Optional[str] = None
    stop_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None


@dataclass
class MockPosition:
    """Represents a mock position."""
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    stop_price: Optional[float] = None
    
    @property
    def market_value(self) -> float:
        return self.qty * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_entry_price) * self.qty
    
    @property
    def unrealized_pnl_percent(self) -> float:
        if self.avg_entry_price == 0:
            return 0.0
        return ((self.current_price - self.avg_entry_price) / self.avg_entry_price) * 100


@dataclass
class MockBracketOrderResult:
    """Result of bracket order submission."""
    is_accepted: bool
    entry_order_id: Optional[str] = None
    avg_fill_price: Optional[float] = None
    filled_qty: int = 0
    error: Optional[str] = None


class MockBroker:
    """
    Mock broker for simulation.
    
    Implements same interface as AlpacaBroker for seamless swapping.
    """
    
    def __init__(self, initial_cash: float = 100_000.0):
        """
        Initialize mock broker.
        
        Args:
            initial_cash: Starting cash balance
        """
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._orders: Dict[str, MockOrder] = {}
        self._positions: Dict[str, MockPosition] = {}
        self._current_prices: Dict[str, float] = {}
        self._realized_pnl: float = 0.0
        
    def reset(self):
        """Reset broker to initial state."""
        self._cash = self._initial_cash
        self._orders.clear()
        self._positions.clear()
        self._current_prices.clear()
        self._realized_pnl = 0.0
    
    def set_price(self, symbol: str, price: float):
        """
        Set current price for a symbol.
        
        Args:
            symbol: Stock symbol
            price: Current price
        """
        self._current_prices[symbol] = price
        
        # Update position current price
        if symbol in self._positions:
            self._positions[symbol].current_price = price
        
        # Check stop orders
        self._check_stop_orders(symbol)
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        return self._current_prices.get(symbol)
    
    def submit_bracket_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        stop_price: float,
        take_profit_price: Optional[float] = None,
    ) -> MockBracketOrderResult:
        """
        Submit bracket order (entry + stop + optional TP).
        
        Args:
            symbol: Stock symbol
            side: 'buy' or 'sell'
            qty: Number of shares
            stop_price: Stop loss price
            take_profit_price: Take profit price (optional)
        
        Returns:
            MockBracketOrderResult with fill info
        """
        current_price = self._current_prices.get(symbol)
        
        if current_price is None:
            return MockBracketOrderResult(
                is_accepted=False,
                error=f"No price available for {symbol}"
            )
        
        # Check buying power
        order_value = current_price * qty
        if side.lower() == "buy" and order_value > self._cash:
            return MockBracketOrderResult(
                is_accepted=False,
                error=f"Insufficient buying power: need ${order_value:.2f}, have ${self._cash:.2f}"
            )
        
        # Create entry order (assume market order, fill immediately)
        entry_order_id = str(uuid4())
        fill_price = current_price  # In sim, fill at current price
        
        entry_order = MockOrder(
            id=entry_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="market",
            status=MockOrderStatus.FILLED,
            avg_fill_price=fill_price,
            filled_qty=qty,
            filled_at=datetime.utcnow(),
        )
        
        # Create stop order (pending)
        stop_order_id = str(uuid4())
        stop_order = MockOrder(
            id=stop_order_id,
            symbol=symbol,
            side="sell" if side == "buy" else "buy",
            qty=qty,
            order_type="stop",
            status=MockOrderStatus.PENDING,
            stop_price=stop_price,
            parent_id=entry_order_id,
        )
        
        entry_order.stop_order_id = stop_order_id
        
        # Store orders
        self._orders[entry_order_id] = entry_order
        self._orders[stop_order_id] = stop_order
        
        # Update cash
        if side.lower() == "buy":
            self._cash -= fill_price * qty
        else:
            self._cash += fill_price * qty
        
        # Create/update position
        if symbol in self._positions:
            pos = self._positions[symbol]
            # Average up (simplified)
            total_qty = pos.qty + qty
            total_cost = (pos.avg_entry_price * pos.qty) + (fill_price * qty)
            pos.qty = total_qty
            pos.avg_entry_price = total_cost / total_qty
            pos.stop_price = stop_price
        else:
            self._positions[symbol] = MockPosition(
                symbol=symbol,
                qty=qty,
                avg_entry_price=fill_price,
                current_price=fill_price,
                stop_price=stop_price,
            )
        
        logger.info(f"[MockBroker] Filled {side.upper()} {qty}x {symbol} @ ${fill_price:.2f}")
        
        return MockBracketOrderResult(
            is_accepted=True,
            entry_order_id=entry_order_id,
            avg_fill_price=fill_price,
            filled_qty=qty,
        )
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancelled successfully
        """
        order = self._orders.get(order_id)
        if order is None:
            return False
        
        if order.status != MockOrderStatus.PENDING:
            return False
        
        order.status = MockOrderStatus.CANCELLED
        logger.info(f"[MockBroker] Cancelled order {order_id}")
        return True
    
    def sell_position(self, symbol: str, qty: Optional[int] = None) -> bool:
        """
        Sell position (partial or full).
        
        Args:
            symbol: Symbol to sell
            qty: Shares to sell (None = all)
        
        Returns:
            True if sold successfully
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return False
        
        sell_qty = qty if qty else pos.qty
        if sell_qty > pos.qty:
            sell_qty = pos.qty
        
        current_price = self._current_prices.get(symbol, pos.current_price)
        
        # Calculate P&L
        pnl = (current_price - pos.avg_entry_price) * sell_qty
        self._realized_pnl += pnl
        self._cash += current_price * sell_qty
        
        # Update or remove position
        pos.qty -= sell_qty
        if pos.qty <= 0:
            del self._positions[symbol]
            # Cancel associated stop orders
            for order in self._orders.values():
                if order.symbol == symbol and order.status == MockOrderStatus.PENDING:
                    order.status = MockOrderStatus.CANCELLED
        
        logger.info(f"[MockBroker] Sold {sell_qty}x {symbol} @ ${current_price:.2f}, P&L: ${pnl:.2f}")
        return True
    
    def update_stop(self, symbol: str, new_stop_price: float) -> bool:
        """
        Update stop price for position.
        
        Args:
            symbol: Symbol to update
            new_stop_price: New stop price
        
        Returns:
            True if updated successfully
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return False
        
        pos.stop_price = new_stop_price
        
        # Update pending stop orders
        for order in self._orders.values():
            if (order.symbol == symbol and 
                order.order_type == "stop" and 
                order.status == MockOrderStatus.PENDING):
                order.stop_price = new_stop_price
        
        logger.info(f"[MockBroker] Updated {symbol} stop to ${new_stop_price:.2f}")
        return True
    
    def get_positions(self) -> List[Dict]:
        """Get all positions as list of dicts."""
        return [
            {
                "symbol": pos.symbol,
                "qty": pos.qty,
                "avg_price": pos.avg_entry_price,
                "market_value": pos.market_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "pnl_percent": pos.unrealized_pnl_percent,
                "stop_price": pos.stop_price,
            }
            for pos in self._positions.values()
        ]
    
    def get_account(self) -> Dict:
        """Get account info."""
        total_position_value = sum(p.market_value for p in self._positions.values())
        total_unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        
        return {
            "cash": self._cash,
            "portfolio_value": self._cash + total_position_value,
            "buying_power": self._cash,  # Simplified, no margin
            "realized_pnl": self._realized_pnl,
            "unrealized_pnl": total_unrealized,
            "position_count": len(self._positions),
        }
    
    def _check_stop_orders(self, symbol: str):
        """Check and trigger stop orders for symbol."""
        price = self._current_prices.get(symbol)
        if price is None:
            return
        
        for order in list(self._orders.values()):
            if (order.symbol == symbol and 
                order.order_type == "stop" and 
                order.status == MockOrderStatus.PENDING and
                order.stop_price is not None):
                
                # For short stops (shouldn't happen in long-only), check >= stop
                # For long stops, trigger when price <= stop
                if price <= order.stop_price:
                    # Trigger stop
                    order.status = MockOrderStatus.FILLED
                    order.avg_fill_price = price  # Fill at current (could be slippage)
                    order.filled_qty = order.qty
                    order.filled_at = datetime.utcnow()
                    
                    # Close position
                    if symbol in self._positions:
                        pos = self._positions[symbol]
                        pnl = (price - pos.avg_entry_price) * pos.qty
                        self._realized_pnl += pnl
                        self._cash += price * pos.qty
                        del self._positions[symbol]
                        
                        logger.info(
                            f"[MockBroker] STOP TRIGGERED: {symbol} @ ${price:.2f}, "
                            f"P&L: ${pnl:.2f}"
                        )
    
    def to_dict(self) -> Dict:
        """Convert broker state to dict for debugging."""
        return {
            "account": self.get_account(),
            "positions": self.get_positions(),
            "order_count": len(self._orders),
            "pending_orders": len([o for o in self._orders.values() if o.status == MockOrderStatus.PENDING]),
        }
