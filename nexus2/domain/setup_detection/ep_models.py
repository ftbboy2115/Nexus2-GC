"""
EP (Episodic Pivot) Detection Models

Entities and value objects for EP setup detection.
Based on: ep_setup_research.md, implementation_plan.md
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4


# =============================================================================
# VALUE OBJECTS
# =============================================================================

class CatalystType(Enum):
    """Type of catalyst triggering the EP."""
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    NEWS = "news"  # Generic news catalyst
    PRODUCT_LAUNCH = "product_launch"
    FDA_APPROVAL = "fda_approval"
    PARTNERSHIP = "partnership"
    ANALYST_UPGRADE = "analyst_upgrade"
    CONTRACT = "contract"
    OTHER = "other"


class EPCandidateStatus(Enum):
    """Status of an EP candidate."""
    PENDING = "pending"      # Waiting for market open
    ACTIVE = "active"        # Opening range established
    TRIGGERED = "triggered"  # ORH broken
    EXPIRED = "expired"      # No trigger within session
    INVALID = "invalid"      # Disqualified


class EPValidationResult(Enum):
    """Result of EP validation."""
    VALID = "valid"
    INVALID_GAP = "invalid_gap"          # Gap too small
    INVALID_VOLUME = "invalid_volume"    # Volume too low
    INVALID_ATR = "invalid_atr"          # Stop too wide
    INVALID_PRICE = "invalid_price"      # Price disqualified
    INVALID_EXTENDED = "invalid_extended"  # Too extended


# =============================================================================
# ENTITIES
# =============================================================================

@dataclass
class OpeningRange:
    """
    Opening range for EP entry.
    
    Established after first N minutes of trading.
    """
    high: Decimal
    low: Decimal
    timeframe_minutes: int  # 1, 5, or 60
    established_at: datetime
    
    @property
    def range_size(self) -> Decimal:
        """Size of the opening range."""
        return self.high - self.low
    
    @property
    def range_pct(self) -> Decimal:
        """Range as percentage of low."""
        if self.low > 0:
            return (self.range_size / self.low) * 100
        return Decimal("0")


@dataclass
class EPCandidate:
    """
    Stock that has triggered an EP scanner alert.
    
    Not yet a confirmed setup - needs validation.
    """
    symbol: str
    catalyst_date: date
    catalyst_type: CatalystType
    catalyst_description: str
    
    # Gap metrics
    gap_percent: Decimal
    prev_close: Decimal
    open_price: Decimal
    
    # Volume metrics
    pre_market_volume: int
    relative_volume: Decimal  # RVOL vs average
    
    # Opening range (set after market open)
    opening_range: Optional[OpeningRange] = None
    
    # Price levels
    ep_candle_low: Optional[Decimal] = None  # Full day low = invalidation
    current_price: Optional[Decimal] = None
    
    # Volatility
    atr: Decimal = Decimal("0")
    adr_percent: Decimal = Decimal("0")
    
    # Status
    status: EPCandidateStatus = EPCandidateStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def tactical_stop(self) -> Optional[Decimal]:
        """Tactical stop = opening range low (LOD)."""
        if self.opening_range:
            return self.opening_range.low
        return None
    
    @property
    def invalidation_level(self) -> Optional[Decimal]:
        """Setup invalidation = EP candle low."""
        return self.ep_candle_low


@dataclass
class EPSetup:
    """
    Confirmed, actionable EP setup.
    
    Created from validated EPCandidate.
    """
    id: UUID
    symbol: str
    candidate: EPCandidate
    
    # Entry
    entry_price: Decimal  # ORH break price
    
    # Stops (KK hierarchy)
    tactical_stop: Decimal      # Opening range low (LOD)
    invalidation_level: Decimal  # EP candle low
    
    # Risk metrics
    stop_distance: Decimal
    stop_atr_ratio: Decimal
    
    # Validity
    is_valid: bool
    invalidation_reason: Optional[str] = None
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # EOD by default
    
    @classmethod
    def from_candidate(
        cls,
        candidate: EPCandidate,
        entry_price: Optional[Decimal] = None,
    ) -> "EPSetup":
        """
        Create EPSetup from validated candidate.
        
        Args:
            candidate: Validated EP candidate
            entry_price: Entry price (defaults to ORH)
        """
        if not candidate.opening_range:
            raise ValueError("Candidate must have opening range established")
        
        orh = candidate.opening_range.high
        lod = candidate.opening_range.low
        ep_low = candidate.ep_candle_low or lod
        
        entry = entry_price or orh
        stop_distance = entry - lod
        stop_atr_ratio = stop_distance / candidate.atr if candidate.atr > 0 else Decimal("999")
        
        return cls(
            id=uuid4(),
            symbol=candidate.symbol,
            candidate=candidate,
            entry_price=entry,
            tactical_stop=lod,
            invalidation_level=ep_low,
            stop_distance=stop_distance,
            stop_atr_ratio=stop_atr_ratio,
            is_valid=stop_atr_ratio <= Decimal("1.0"),
            invalidation_reason=None if stop_atr_ratio <= Decimal("1.0") else "Stop exceeds 1x ATR",
        )


@dataclass
class EPTrade:
    """
    Active trade based on an EP setup.
    
    Tracks the full trade lifecycle.
    """
    id: UUID
    setup: EPSetup
    
    # Entry
    entry_date: date
    entry_price: Decimal
    shares: int
    
    # Risk
    initial_risk_dollars: Decimal
    current_stop: Decimal
    trailing_ma_type: Optional[str] = None  # e.g., "sma_20"
    
    # Exits
    partial_exits: List["PartialExit"] = field(default_factory=list)
    
    # Status
    status: str = "open"  # open, partial, closed
    exit_price: Optional[Decimal] = None
    exit_date: Optional[date] = None
    exit_reason: Optional[str] = None
    
    # P&L
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    
    @property
    def remaining_shares(self) -> int:
        """Shares still open after partial exits."""
        exited = sum(p.shares for p in self.partial_exits)
        return self.shares - exited
    
    @property
    def total_pnl(self) -> Decimal:
        """Total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl


@dataclass
class PartialExit:
    """Record of a partial position exit."""
    shares: int
    exit_price: Decimal
    exit_date: date
    reason: str  # e.g., "3-5 day rule", "trailing stop"
    pnl: Decimal


@dataclass
class EntrySignal:
    """Signal to enter an EP trade."""
    setup: EPSetup
    entry_price: Decimal
    stop_price: Decimal
    shares: int
    risk_dollars: Decimal
    signal_time: datetime = field(default_factory=datetime.now)
