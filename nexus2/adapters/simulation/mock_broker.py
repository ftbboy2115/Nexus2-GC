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
from nexus2.utils.time_utils import now_utc, now_utc_factory

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
    created_at: datetime = field(default_factory=now_utc_factory)
    filled_at: Optional[datetime] = None
    
    # For bracket orders
    parent_id: Optional[str] = None
    stop_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    
    # Exit mode for GUI display (base_hit or home_run)
    exit_mode: Optional[str] = None
    # Sim clock time when order was placed (for historical replay)
    sim_time: Optional[str] = None


@dataclass
class MockPosition:
    """Represents a mock position."""
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    stop_price: Optional[float] = None
    opened_at: Optional[datetime] = None  # Track actual entry time for days_held
    
    @property
    def market_value(self) -> float:
        if self.current_price is None:
            return self.qty * self.avg_entry_price
        return self.qty * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        if self.current_price is None:
            return 0.0
        return (self.current_price - self.avg_entry_price) * self.qty
    
    @property
    def unrealized_pnl_percent(self) -> float:
        if self.avg_entry_price == 0 or self.current_price is None:
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
        # Track peak capital usage metrics
        self._max_capital_deployed: float = 0.0  # Peak capital in positions
        self._max_shares_held: int = 0  # Peak total shares across all positions
        
    def reset(self):
        """Reset broker to initial state."""
        self._cash = self._initial_cash
        self._orders.clear()
        self._positions.clear()
        self._current_prices.clear()
        self._realized_pnl = 0.0
        self._max_capital_deployed = 0.0
        self._max_shares_held = 0
    
    def _update_max_metrics(self):
        """Update peak capital and shares metrics based on current positions."""
        total_shares = sum(pos.qty for pos in self._positions.values())
        total_capital = sum(
            pos.qty * pos.avg_entry_price for pos in self._positions.values()
        )
        
        if total_shares > self._max_shares_held:
            self._max_shares_held = total_shares
        if total_capital > self._max_capital_deployed:
            self._max_capital_deployed = total_capital
    
    def set_price(self, symbol: str, price: float):
        """
        Set current price for a symbol.
        
        Also checks if any pending limit or stop orders should fill.
        
        Args:
            symbol: Stock symbol
            price: Current price
        """
        self._current_prices[symbol] = price
        
        # Update position current price
        if symbol in self._positions:
            self._positions[symbol].current_price = price
        
        # Check pending limit orders (for entry)
        self._check_pending_limit_orders(symbol)
        
        # Check stop orders (for exit)
        self._check_stop_orders(symbol)
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        return self._current_prices.get(symbol)
    
    def submit_bracket_order(
        self,
        client_order_id,  # UUID
        symbol: str,
        quantity: int,
        stop_loss_price,  # Decimal
        limit_price=None,  # Optional[Decimal]
        take_profit_price=None,  # Optional[Decimal]
        exit_mode: Optional[str] = None,  # "base_hit" or "home_run" for GUI
        sim_time: Optional[str] = None,  # Sim clock time (e.g. "10:45") for GUI
    ):
        """
        Submit bracket order (entry + stop + optional TP).
        
        If limit_price is provided, creates a PENDING limit order that fills
        when price crosses the limit. Otherwise fills immediately at market.
        
        Args:
            client_order_id: Unique client order ID (UUID)
            symbol: Stock symbol
            quantity: Number of shares
            stop_loss_price: Stop loss price
            limit_price: If provided, order stays PENDING until price <= limit
            take_profit_price: Take profit price (optional)
            exit_mode: "base_hit" or "home_run" (for GUI display)
            sim_time: Sim clock time when order placed (for GUI display)
        
        Returns:
            BrokerOrder matching AlpacaBroker's return type
        """
        from nexus2.adapters.broker.protocol import BrokerOrder, BrokerOrderStatus
        from decimal import Decimal
        
        current_price = self._current_prices.get(symbol)
        
        if current_price is None:
            return BrokerOrder(
                client_order_id=client_order_id,
                broker_order_id=str(uuid4()),
                symbol=symbol,
                side="buy",
                quantity=quantity,
                order_type="limit" if limit_price else "market",
                status=BrokerOrderStatus.REJECTED,
            )
        
        # Keep stop_loss_price as-is (None means no stop - monitor controls exits)
        stop_price = float(stop_loss_price) if stop_loss_price is not None else None
        entry_order_id = str(uuid4())

        
        # Determine if this is a limit order (PENDING) or market order (immediate fill)
        if limit_price is not None:
            limit_price_float = float(limit_price)
            
            # Check if we can fill immediately (price already at or below limit)
            if current_price <= limit_price_float:
                # Can fill immediately
                return self._fill_entry_order(
                    client_order_id, entry_order_id, symbol, quantity, 
                    current_price, stop_price, exit_mode, sim_time
                )
            else:
                # Create PENDING limit order - will fill when price crosses
                entry_order = MockOrder(
                    id=entry_order_id,
                    symbol=symbol,
                    side="buy",
                    qty=quantity,
                    order_type="limit",
                    status=MockOrderStatus.PENDING,
                    limit_price=limit_price_float,
                    stop_price=stop_price,  # Store for when it fills
                    exit_mode=exit_mode,
                    sim_time=sim_time,
                )
                self._orders[entry_order_id] = entry_order
                
                logger.info(
                    f"[MockBroker] PENDING limit BUY {quantity}x {symbol} @ ${limit_price_float:.2f} "
                    f"(current: ${current_price:.2f})"
                )
                
                return BrokerOrder(
                    client_order_id=client_order_id,
                    broker_order_id=entry_order_id,
                    symbol=symbol,
                    side="buy",
                    quantity=quantity,
                    order_type="limit",
                    limit_price=Decimal(str(limit_price_float)),
                    status=BrokerOrderStatus.PENDING,
                    submitted_at=now_utc(),
                )
        else:
            # Market order - check buying power and fill immediately
            order_value = current_price * quantity
            if order_value > self._cash:
                return BrokerOrder(
                    client_order_id=client_order_id,
                    broker_order_id=str(uuid4()),
                    symbol=symbol,
                    side="buy",
                    quantity=quantity,
                    order_type="market",
                    status=BrokerOrderStatus.REJECTED,
                )
            
            return self._fill_entry_order(
                client_order_id, entry_order_id, symbol, quantity, 
                current_price, stop_price, exit_mode, sim_time
            )
    
    def _fill_entry_order(
        self, 
        client_order_id, 
        entry_order_id: str, 
        symbol: str, 
        quantity: int, 
        fill_price: float, 
        stop_price: float,
        exit_mode: Optional[str] = None,
        sim_time: Optional[str] = None,
    ):
        """Internal helper to fill an entry order and create position."""
        from nexus2.adapters.broker.protocol import BrokerOrder, BrokerOrderStatus
        from decimal import Decimal
        
        # Check buying power
        order_value = fill_price * quantity
        if order_value > self._cash:
            return BrokerOrder(
                client_order_id=client_order_id,
                broker_order_id=entry_order_id,
                symbol=symbol,
                side="buy",
                quantity=quantity,
                order_type="limit",
                status=BrokerOrderStatus.REJECTED,
            )
        
        # Create filled entry order
        entry_order = MockOrder(
            id=entry_order_id,
            symbol=symbol,
            side="buy",
            qty=quantity,
            order_type="limit",
            status=MockOrderStatus.FILLED,
            limit_price=fill_price,  # Store for GUI display
            avg_fill_price=fill_price,
            filled_qty=quantity,
            filled_at=now_utc(),
            exit_mode=exit_mode,
            sim_time=sim_time,
        )
        
        # Only create stop order if stop_price is provided
        # (None = monitor controls exits, no broker-level stops)
        stop_order_id = None
        if stop_price is not None:
            stop_order_id = str(uuid4())
            stop_order = MockOrder(
                id=stop_order_id,
                symbol=symbol,
                side="sell",
                qty=quantity,
                order_type="stop",
                status=MockOrderStatus.PENDING,
                stop_price=stop_price,
                parent_id=entry_order_id,
            )
            entry_order.stop_order_id = stop_order_id
            self._orders[stop_order_id] = stop_order
        
        # Store entry order
        self._orders[entry_order_id] = entry_order

        
        # Update cash
        self._cash -= fill_price * quantity
        
        # Create/update position
        if symbol in self._positions:
            pos = self._positions[symbol]
            total_qty = pos.qty + quantity
            total_cost = (pos.avg_entry_price * pos.qty) + (fill_price * quantity)
            pos.qty = total_qty
            pos.avg_entry_price = total_cost / total_qty
            pos.stop_price = stop_price
        else:
            self._positions[symbol] = MockPosition(
                symbol=symbol,
                qty=quantity,
                avg_entry_price=fill_price,
                current_price=fill_price,
                stop_price=stop_price,
                opened_at=now_utc(),
            )
        
        # Update peak metrics
        self._update_max_metrics()
        
        logger.info(f"[MockBroker] FILLED BUY {quantity}x {symbol} @ ${fill_price:.2f}")
        
        return BrokerOrder(
            client_order_id=client_order_id,
            broker_order_id=entry_order_id,
            symbol=symbol,
            side="buy",
            quantity=quantity,
            order_type="limit",
            status=BrokerOrderStatus.FILLED,
            filled_quantity=quantity,
            avg_fill_price=Decimal(str(fill_price)),
            submitted_at=now_utc(),
            filled_at=now_utc(),
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
        
        # Create SELL order record for GUI visibility
        # Get sim_time from simulation clock for GUI display
        try:
            from nexus2.adapters.simulation import get_simulation_clock
            sim_clock = get_simulation_clock()
            sim_time = sim_clock.get_time_string() if sim_clock and sim_clock.current_time else None
        except ImportError:
            sim_time = None
        
        sell_order_id = str(uuid4())
        sell_order = MockOrder(
            id=sell_order_id,
            symbol=symbol,
            side="sell",
            qty=sell_qty,
            order_type="limit",  # Ross uses limit orders, not market
            status=MockOrderStatus.FILLED,
            limit_price=current_price,  # Limit price for display
            avg_fill_price=current_price,
            filled_qty=sell_qty,
            filled_at=now_utc(),
            sim_time=sim_time,
        )
        self._orders[sell_order_id] = sell_order
        
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
            "max_capital_deployed": self._max_capital_deployed,
            "max_shares_held": self._max_shares_held,
        }
    
    def _check_pending_limit_orders(self, symbol: str):
        """
        Check and fill pending limit buy orders when price is favorable.
        
        Limit buy fills when current price <= limit price.
        """
        price = self._current_prices.get(symbol)
        if price is None:
            return
        
        for order in list(self._orders.values()):
            if (order.symbol == symbol and 
                order.order_type == "limit" and 
                order.status == MockOrderStatus.PENDING and
                order.limit_price is not None):
                
                # Limit BUY: fill when price <= limit
                if order.side == "buy" and price <= order.limit_price:
                    # Fill at the better price (current price, not limit)
                    fill_price = price
                    
                    # Check buying power
                    order_value = fill_price * order.qty
                    if order_value > self._cash:
                        order.status = MockOrderStatus.REJECTED
                        logger.warning(f"[MockBroker] REJECTED {symbol}: Insufficient buying power")
                        continue
                    
                    # Fill the order
                    order.status = MockOrderStatus.FILLED
                    order.avg_fill_price = fill_price
                    order.filled_qty = order.qty
                    order.filled_at = now_utc()
                    
                    # Update cash
                    self._cash -= fill_price * order.qty
                    
                    # Create/update position
                    stop_price = order.stop_price or (fill_price * 0.95)
                    if symbol in self._positions:
                        pos = self._positions[symbol]
                        total_qty = pos.qty + order.qty
                        total_cost = (pos.avg_entry_price * pos.qty) + (fill_price * order.qty)
                        pos.qty = total_qty
                        pos.avg_entry_price = total_cost / total_qty
                    else:
                        self._positions[symbol] = MockPosition(
                            symbol=symbol,
                            qty=order.qty,
                            avg_entry_price=fill_price,
                            current_price=fill_price,
                            stop_price=stop_price,
                            opened_at=now_utc(),
                        )
                    
                    # Update peak metrics
                    self._update_max_metrics()
                    
                    logger.info(
                        f"[MockBroker] LIMIT FILL: BUY {order.qty}x {symbol} "
                        f"@ ${fill_price:.2f} (limit was ${order.limit_price:.2f})"
                    )
                
                # Limit SELL: fill when price >= limit (take profit)
                elif order.side == "sell" and price >= order.limit_price:
                    fill_price = price
                    order.status = MockOrderStatus.FILLED
                    order.avg_fill_price = fill_price
                    order.filled_qty = order.qty
                    order.filled_at = now_utc()
                    
                    # Close position
                    if symbol in self._positions:
                        pos = self._positions[symbol]
                        pnl = (fill_price - pos.avg_entry_price) * order.qty
                        self._realized_pnl += pnl
                        self._cash += fill_price * order.qty
                        pos.qty -= order.qty
                        if pos.qty <= 0:
                            del self._positions[symbol]
                        
                        logger.info(
                            f"[MockBroker] LIMIT FILL: SELL {order.qty}x {symbol} "
                            f"@ ${fill_price:.2f}, P&L: ${pnl:.2f}"
                        )
    
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
                
                # For long stops, trigger when price <= stop
                if price <= order.stop_price:
                    # Trigger stop
                    order.status = MockOrderStatus.FILLED
                    order.avg_fill_price = price  # Fill at current (slippage)
                    order.filled_qty = order.qty
                    order.filled_at = now_utc()
                    
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
    
    def get_orders(self) -> List[Dict]:
        """Get all orders for GUI visibility."""
        return [
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "order_type": order.order_type,
                "status": order.status.value,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "avg_fill_price": order.avg_fill_price,
                "filled_qty": order.filled_qty,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "exit_mode": order.exit_mode,
                "sim_time": order.sim_time,
            }
            for order in self._orders.values()
        ]
    
    def to_dict(self) -> Dict:
        """Convert broker state to dict for debugging."""
        return {
            "account": self.get_account(),
            "positions": self.get_positions(),
            "order_count": len(self._orders),
            "pending_orders": len([o for o in self._orders.values() if o.status == MockOrderStatus.PENDING]),
        }
