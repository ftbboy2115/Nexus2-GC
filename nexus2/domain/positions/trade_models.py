"""
Trade Management Models

Entities for managing active trades through their lifecycle.
Based on: trade_management_research.md
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from nexus2.utils.time_utils import now_utc_factory


class TradeStatus(Enum):
    """Status of a trade."""
    OPEN = "open"
    PARTIAL_EXIT = "partial_exit"
    STOPPED_OUT = "stopped_out"
    TRAILING_EXIT = "trailing_exit"
    MANUAL_EXIT = "manual_exit"
    CLOSED = "closed"


class ExitReason(Enum):
    """Reason for exiting a trade."""
    INITIAL_STOP = "initial_stop"
    BREAKEVEN_STOP = "breakeven_stop"
    TRAILING_STOP = "trailing_stop"
    PARTIAL_PROFIT = "partial_profit"
    TIME_BASED = "time_based"  # 3-5 day rule
    MA_CLOSE = "ma_close"  # Close below MA
    MANUAL = "manual"
    EARNINGS = "earnings"  # Pre-earnings exit


@dataclass
class PartialExitRecord:
    """Record of a partial position exit."""
    id: UUID
    shares: int
    exit_price: Decimal
    exit_date: date
    exit_time: datetime
    reason: ExitReason
    pnl: Decimal
    pnl_percent: Decimal
    r_multiple: Decimal  # Profit as multiple of initial risk


@dataclass
class TradePerformance:
    """Performance metrics for a trade."""
    entry_price: Decimal
    current_price: Decimal
    initial_stop: Decimal
    
    # P&L
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    
    # Risk metrics
    initial_risk: Decimal
    current_risk: Decimal
    r_multiple: Decimal  # Current profit as R multiple
    
    # Time
    days_held: int
    
    @property
    def is_profitable(self) -> bool:
        return self.total_pnl > 0


@dataclass
class ManagedTrade:
    """
    A trade being actively managed.
    
    Tracks full lifecycle from entry to exit.
    """
    id: UUID
    symbol: str
    setup_type: str  # "ep", "flag", "htf", "breakout"
    
    # Entry
    entry_date: date
    entry_time: datetime
    entry_price: Decimal
    shares: int
    
    # Risk - KK Stop Hierarchy
    initial_stop: Decimal  # Legacy: same as tactical_stop for backwards compat
    initial_risk_dollars: Decimal
    current_stop: Decimal
    stop_type: str  # "initial", "breakeven", "trailing"
    trailing_ma_type: Optional[str] = None
    
    # Dual-stop system (NOT KK-style - optional feature, default=off)
    # KK uses single stop: LOD. This is for experimental comparison.
    use_dual_stops: bool = False  # Track if dual-stop was enabled for this trade
    tactical_stop: Optional[Decimal] = None  # Opening range/flag low - for position sizing
    invalidation_level: Optional[Decimal] = None  # EP candle low - alert only if breached
    atr_at_entry: Optional[Decimal] = None  # ATR when trade opened
    stop_atr_ratio: Optional[Decimal] = None  # tactical_stop distance / ATR (must be <= 1.0)
    
    # Status
    status: TradeStatus = TradeStatus.OPEN
    remaining_shares: int = 0
    
    # Broker/Account context - for filtering positions by broker
    broker_type: str = "paper"  # paper, alpaca_paper
    account: str = "A"  # A or B for Alpaca accounts
    
    # Exits
    partial_exits: List[PartialExitRecord] = field(default_factory=list)
    final_exit_price: Optional[Decimal] = None
    final_exit_date: Optional[date] = None
    final_exit_reason: Optional[ExitReason] = None
    
    # P&L
    realized_pnl: Decimal = Decimal("0")
    
    # Timestamps
    created_at: datetime = field(default_factory=now_utc_factory)
    updated_at: datetime = field(default_factory=now_utc_factory)
    
    def __post_init__(self):
        if self.remaining_shares == 0:
            self.remaining_shares = self.shares
    
    @property
    def days_held(self) -> int:
        """Days since entry."""
        today = date.today()
        return (today - self.entry_date).days
    
    @property
    def is_breakeven_eligible(self) -> bool:
        """Has had a partial exit (eligible for BE stop)."""
        return len(self.partial_exits) > 0
    
    def calculate_performance(self, current_price: Decimal) -> TradePerformance:
        """Calculate current trade performance."""
        # Unrealized P&L on remaining shares
        unrealized = (current_price - self.entry_price) * self.remaining_shares
        unrealized_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        
        # Current risk
        current_risk = (self.entry_price - self.current_stop) * self.remaining_shares
        
        # R multiple
        if self.initial_risk_dollars > 0:
            r_mult = (self.realized_pnl + unrealized) / self.initial_risk_dollars
        else:
            r_mult = Decimal("0")
        
        return TradePerformance(
            entry_price=self.entry_price,
            current_price=current_price,
            initial_stop=self.initial_stop,
            unrealized_pnl=unrealized,
            unrealized_pnl_pct=unrealized_pct,
            realized_pnl=self.realized_pnl,
            total_pnl=self.realized_pnl + unrealized,
            initial_risk=self.initial_risk_dollars,
            current_risk=current_risk,
            r_multiple=r_mult,
            days_held=self.days_held,
        )


@dataclass
class PartialExitSignal:
    """Signal to take a partial exit."""
    trade_id: UUID
    shares_to_exit: int
    reason: ExitReason
    suggested_price: Optional[Decimal] = None
    message: str = ""
    
    @classmethod
    def from_time_rule(
        cls,
        trade: ManagedTrade,
        fraction: Decimal,
        current_price: Decimal,
    ) -> "PartialExitSignal":
        """Create signal from 3-5 day rule."""
        shares = int(trade.remaining_shares * fraction)
        return cls(
            trade_id=trade.id,
            shares_to_exit=shares,
            reason=ExitReason.TIME_BASED,
            suggested_price=current_price,
            message=f"3-5 day rule: Sell {shares} shares ({fraction*100:.0f}%)",
        )


@dataclass
class ExitSignal:
    """Signal to exit a trade (full or partial)."""
    trade_id: UUID
    exit_type: str  # "full", "partial"
    shares: int
    reason: ExitReason
    trigger_price: Optional[Decimal] = None
    message: str = ""
