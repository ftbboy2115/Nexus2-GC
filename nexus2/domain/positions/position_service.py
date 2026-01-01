"""
Position Service

Bridges Orders domain to Trade Management.
Creates and manages ManagedTrades from filled orders.
"""

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from nexus2.domain.orders import Order, OrderStatus, OrderSide
from nexus2.domain.positions.trade_models import (
    ManagedTrade,
    TradeStatus,
)


class PositionError(Exception):
    """Position-related error."""
    pass


class PositionNotFoundError(PositionError):
    """Position not found."""
    pass


class PositionService:
    """
    Manages positions created from filled orders.
    
    Bridges the Orders domain to Trade Management.
    """
    
    def __init__(self):
        # In-memory storage
        self._positions: Dict[UUID, ManagedTrade] = {}
        self._positions_by_symbol: Dict[str, UUID] = {}
    
    def load_from_database(self, db_positions: list) -> int:
        """
        Load open positions from database into memory on startup.
        
        Args:
            db_positions: List of PositionModel objects from database
            
        Returns:
            Number of positions loaded
        """
        count = 0
        for p in db_positions:
            try:
                # Convert DB model to ManagedTrade
                trade = ManagedTrade(
                    id=UUID(p.id),
                    symbol=p.symbol,
                    setup_type=p.setup_type or "manual",
                    entry_date=p.opened_at.date() if p.opened_at else date.today(),
                    entry_time=p.opened_at or datetime.now(),
                    entry_price=Decimal(p.entry_price),
                    shares=p.shares,
                    initial_stop=Decimal(p.initial_stop) if p.initial_stop else Decimal("0"),
                    initial_risk_dollars=Decimal("0"),  # Not stored in DB, calculate if needed
                    current_stop=Decimal(p.current_stop) if p.current_stop else Decimal("0"),
                    stop_type="initial",
                    status=TradeStatus.OPEN if p.status == "open" else TradeStatus.CLOSED,
                    remaining_shares=p.remaining_shares,
                    broker_type=getattr(p, 'broker_type', 'paper') or 'paper',
                    account=getattr(p, 'account', 'A') or 'A',
                    realized_pnl=Decimal(p.realized_pnl or "0"),
                )
                
                # Add to in-memory storage
                self._positions[trade.id] = trade
                
                # Index by composite key (symbol:broker:account)
                key = f"{trade.symbol}:{trade.broker_type}:{trade.account}"
                self._positions_by_symbol[key] = trade.id
                
                count += 1
            except Exception as e:
                print(f"[PositionService] Error loading position {p.id}: {e}")
        
        return count
    
    def create_from_order(
        self,
        order: Order,
        setup_type: str = "manual",
        broker_type: str = "paper",
        account: str = "A",
    ) -> ManagedTrade:
        """
        Create a ManagedTrade from a filled Order.
        
        Args:
            order: Filled order
            setup_type: Type of setup (ep, flag, htf, breakout, manual)
            broker_type: Broker type (paper, alpaca_paper)
            account: Account identifier (A or B)
            
        Returns:
            New ManagedTrade
            
        Raises:
            PositionError: If order not filled or already has position
        """
        if order.status != OrderStatus.FILLED:
            raise PositionError(f"Order must be FILLED, got {order.status}")
        
        if order.side != OrderSide.BUY:
            raise PositionError("Can only create position from BUY order")
        
        # Check for existing position (for same broker/account)
        existing = self.get_position_by_symbol(
            order.symbol, 
            broker_type=broker_type, 
            account=account
        )
        if existing:
            raise PositionError(f"Position already exists for {order.symbol} on {broker_type}/{account}")
        
        # Calculate initial risk using tactical stop (KK-style)
        tactical = order.tactical_stop or Decimal("0")
        stop = tactical if tactical > 0 else order.stop_price or Decimal("0")
        
        if stop > 0 and order.avg_fill_price:
            initial_risk = (order.avg_fill_price - stop) * order.filled_quantity
        else:
            initial_risk = order.risk_dollars or Decimal("0")
        
        # Calculate ATR ratio if ATR provided
        atr_at_entry = getattr(order, 'atr_at_entry', None)
        stop_atr_ratio = None
        if atr_at_entry and atr_at_entry > 0 and stop > 0 and order.avg_fill_price:
            stop_distance = order.avg_fill_price - stop
            stop_atr_ratio = stop_distance / atr_at_entry
        
        # Get invalidation level (EP candle low) - wider than tactical stop
        invalidation = getattr(order, 'invalidation_level', None)
        
        trade = ManagedTrade(
            id=uuid4(),
            symbol=order.symbol,
            setup_type=setup_type,
            entry_date=date.today(),
            entry_time=order.filled_at or datetime.now(),
            entry_price=order.avg_fill_price or Decimal("0"),
            shares=order.filled_quantity,
            initial_stop=stop,
            initial_risk_dollars=initial_risk,
            current_stop=stop,
            stop_type="initial",
            # KK-style dual stops
            tactical_stop=tactical if tactical > 0 else None,
            invalidation_level=invalidation,
            atr_at_entry=atr_at_entry,
            stop_atr_ratio=stop_atr_ratio,
            status=TradeStatus.OPEN,
            remaining_shares=order.filled_quantity,
            broker_type=broker_type,
            account=account,
        )
        
        self._positions[trade.id] = trade
        # Use composite key for symbol lookup
        key = f"{order.symbol}:{broker_type}:{account}"
        self._positions_by_symbol[key] = trade.id
        
        return trade
    
    def add_to_position(
        self,
        trade_id: UUID,
        order: Order,
    ) -> ManagedTrade:
        """
        Add shares from an add order to existing position.
        
        Updates average entry price.
        
        Args:
            trade_id: Existing trade ID
            order: Filled add order
            
        Returns:
            Updated ManagedTrade
        """
        trade = self._positions.get(trade_id)
        if not trade:
            raise PositionNotFoundError(f"Trade not found: {trade_id}")
        
        if order.status != OrderStatus.FILLED:
            raise PositionError(f"Order must be FILLED, got {order.status}")
        
        if order.symbol != trade.symbol:
            raise PositionError(f"Symbol mismatch: {order.symbol} != {trade.symbol}")
        
        # Calculate new average price
        old_value = trade.entry_price * trade.shares
        new_value = (order.avg_fill_price or Decimal("0")) * order.filled_quantity
        new_shares = trade.shares + order.filled_quantity
        
        trade.entry_price = (old_value + new_value) / new_shares
        trade.shares = new_shares
        trade.remaining_shares += order.filled_quantity
        trade.updated_at = datetime.now()
        
        return trade
    
    def get_position(self, trade_id: UUID) -> Optional[ManagedTrade]:
        """Get position by trade ID."""
        return self._positions.get(trade_id)
    
    def get_position_by_symbol(
        self, 
        symbol: str, 
        broker_type: str | None = None,
        account: str | None = None,
    ) -> Optional[ManagedTrade]:
        """Get open position for a symbol, optionally filtered by broker/account."""
        if broker_type and account:
            # Look up by composite key
            key = f"{symbol}:{broker_type}:{account}"
            trade_id = self._positions_by_symbol.get(key)
            if trade_id:
                return self._positions.get(trade_id)
            return None
        
        # Legacy lookup - any matching symbol
        for trade in self._positions.values():
            if trade.symbol == symbol and trade.status not in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT):
                return trade
        return None
    
    def get_open_positions(
        self,
        broker_type: str | None = None,
        account: str | None = None,
    ) -> List[ManagedTrade]:
        """Get all open positions, optionally filtered by broker/account."""
        positions = [
            t for t in self._positions.values()
            if t.status not in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT)
        ]
        
        # Filter by broker/account if specified
        if broker_type:
            positions = [p for p in positions if p.broker_type == broker_type]
        if account:
            positions = [p for p in positions if p.account == account]
        
        return positions
    
    def get_all_positions(self) -> List[ManagedTrade]:
        """Get all positions (open and closed)."""
        return list(self._positions.values())
    
    def close_position(self, trade_id: UUID) -> ManagedTrade:
        """
        Mark a position as closed.
        
        Called after TradeManagementService.close_trade().
        """
        trade = self._positions.get(trade_id)
        if not trade:
            raise PositionNotFoundError(f"Trade not found: {trade_id}")
        
        # Remove from composite symbol lookup (allow new positions)
        key = f"{trade.symbol}:{trade.broker_type}:{trade.account}"
        if key in self._positions_by_symbol:
            del self._positions_by_symbol[key]
        
        return trade
    
    def update_stop(self, trade_id: UUID, new_stop: Decimal, stop_type: str = "trailing") -> ManagedTrade:
        """
        Update the stop on a position.
        
        Args:
            trade_id: Trade ID
            new_stop: New stop price
            stop_type: Type of stop (initial, breakeven, trailing)
            
        Returns:
            Updated trade
        """
        trade = self._positions.get(trade_id)
        if not trade:
            raise PositionNotFoundError(f"Trade not found: {trade_id}")
        
        # KK Rule: Can only tighten stop
        if new_stop < trade.current_stop:
            raise PositionError(
                f"Cannot loosen stop: {trade.current_stop} -> {new_stop}"
            )
        
        trade.current_stop = new_stop
        trade.stop_type = stop_type
        trade.updated_at = datetime.now()
        
        return trade
    
    def get_all_trades(self) -> List[ManagedTrade]:
        """Get all trades for analytics."""
        return list(self._positions.values())


# Singleton instance
_position_service: Optional[PositionService] = None

def get_position_service() -> PositionService:
    """Get or create singleton position service."""
    global _position_service
    if _position_service is None:
        _position_service = PositionService()
    return _position_service
