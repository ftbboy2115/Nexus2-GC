"""
Stop Management Service

Full stop automation (KK style).
Based on: risk_engine_architecture.md
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from nexus2.domain.risk.models import (
    TradeRisk,
    StopType,
    TrailingMAType,
)
from nexus2.settings.risk_settings import RiskSettings


class SetupType(Enum):
    """Setup type for stop placement."""
    EP = "ep"
    BREAKOUT = "breakout"
    FLAG = "flag"
    HTF = "htf"


class Trade(Protocol):
    """Protocol for trade data."""
    id: UUID
    symbol: str
    entry_price: Decimal
    shares: int
    current_stop: Decimal
    stop_type: StopType


class BrokerInterface(Protocol):
    """Protocol for broker operations."""
    
    def place_stop_order(
        self,
        symbol: str,
        shares: int,
        stop_price: Decimal,
    ) -> str:
        """Place a stop order. Returns order ID."""
        ...
    
    def modify_stop_order(
        self,
        order_id: str,
        new_stop_price: Decimal,
    ) -> bool:
        """Modify existing stop order."""
        ...


@dataclass
class StockCharacteristics:
    """Stock characteristics for MA selection."""
    symbol: str
    adr_percent: Decimal  # Volatility measure
    market_cap: Decimal
    avg_volume: int


class StopManagementService:
    """
    Full stop automation (KK style).
    
    Responsibilities:
    - Set initial stop based on setup type
    - Move stop to breakeven after partial exit
    - Update trailing stop based on MA
    - Check exit triggers
    - Auto-place hard stops
    """
    
    def __init__(self, risk_settings: RiskSettings):
        self.risk_settings = risk_settings
    
    def set_initial_stop(
        self,
        setup_type: SetupType,
        lod: Decimal,  # Low of day
        flag_low: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Set initial stop based on setup type.
        
        - EP/Breakout: LOD
        - Flag/HTF: Flag low
        
        Args:
            setup_type: Type of setup
            lod: Low of the day
            flag_low: Optional flag/consolidation low
            
        Returns:
            Stop price
        """
        if setup_type in (SetupType.EP, SetupType.BREAKOUT):
            return lod
        elif setup_type in (SetupType.FLAG, SetupType.HTF):
            if flag_low is not None:
                return flag_low
            return lod  # Fallback to LOD
        return lod
    
    def move_to_breakeven(
        self,
        entry_price: Decimal,
        current_stop: Decimal,
    ) -> Decimal:
        """
        Move stop to entry price (breakeven).
        
        Only moves if current stop is below entry.
        
        Args:
            entry_price: Original entry price
            current_stop: Current stop price
            
        Returns:
            New stop price (entry_price for BE)
        """
        if current_stop < entry_price:
            return entry_price
        return current_stop  # Don't move stop down
    
    def update_trailing_stop(
        self,
        current_stop: Decimal,
        ma_value: Decimal,
        entry_price: Decimal,
    ) -> Decimal:
        """
        Update trailing stop based on MA.
        
        Only trails UP, never down. Only trails if above breakeven.
        
        Args:
            current_stop: Current stop price
            ma_value: Current MA value for trailing
            entry_price: Original entry (breakeven reference)
            
        Returns:
            New stop price
        """
        # Never trail below entry (breakeven)
        new_stop = max(ma_value, entry_price)
        
        # Only trail up, never down
        return max(current_stop, new_stop)
    
    def select_trailing_ma(
        self,
        stock_chars: StockCharacteristics,
    ) -> TrailingMAType:
        """
        Intelligent MA selection based on stock characteristics.
        
        - Fast/volatile stocks: 10-day MA
        - Slower/larger cap: 20-day MA
        
        Args:
            stock_chars: Stock characteristics
            
        Returns:
            Recommended trailing MA type
        """
        if not self.risk_settings.auto_intelligent_ma:
            return self.risk_settings.default_trailing_ma
        
        # High ADR = volatile = use tighter trail
        if stock_chars.adr_percent > Decimal("6.0"):
            return TrailingMAType.SMA_10
        
        # Large cap = use wider trail
        if stock_chars.market_cap > Decimal("10_000_000_000"):  # $10B+
            return TrailingMAType.SMA_20
        
        # Default: use user's preference
        return self.risk_settings.default_trailing_ma
    
    def check_exit_trigger(
        self,
        close_price: Decimal,
        ma_value: Decimal,
    ) -> bool:
        """
        Check if first close below MA (KK style).
        
        Exit triggered when daily close is below trailing MA.
        
        Args:
            close_price: Daily closing price
            ma_value: Trailing MA value
            
        Returns:
            True if exit should be triggered
        """
        return close_price < ma_value
    
    def auto_place_hard_stop(
        self,
        trade: Trade,
        broker: BrokerInterface,
    ) -> Optional[str]:
        """
        Automatically place hard stop order.
        
        Args:
            trade: Trade to place stop for
            broker: Broker interface
            
        Returns:
            Order ID if placed, None on failure
        """
        if not self.risk_settings.auto_place_hard_stop:
            return None
        
        try:
            order_id = broker.place_stop_order(
                symbol=trade.symbol,
                shares=trade.shares,
                stop_price=trade.current_stop,
            )
            return order_id
        except Exception as e:
            print(f"Error placing stop order: {e}")
            return None
    
    def calculate_stop_atr_ratio(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        atr: Decimal,
    ) -> Decimal:
        """
        Calculate stop distance as ATR ratio.
        
        Args:
            entry_price: Entry price
            stop_price: Stop price
            atr: Average True Range
            
        Returns:
            Stop distance as multiple of ATR
        """
        if atr <= 0:
            return Decimal("999")  # Invalid ATR
        
        stop_distance = entry_price - stop_price
        return stop_distance / atr
    
    def is_stop_valid(self, stop_atr_ratio: Decimal) -> bool:
        """Check if stop is within ATR constraint."""
        return stop_atr_ratio <= self.risk_settings.max_atr_ratio
