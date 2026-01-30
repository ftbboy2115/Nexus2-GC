"""
Risk Domain Models

Entities and value objects for the risk bounded context.
Based on: risk_engine_architecture.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID
from nexus2.utils.time_utils import now_utc_factory


# =============================================================================
# VALUE OBJECTS
# =============================================================================

class StopType(Enum):
    """Stop type classification."""
    INITIAL = "initial"       # LOD or flag low
    BREAKEVEN = "breakeven"   # After partial exit
    TRAILING = "trailing"     # MA-based trail


class HeatStatus(Enum):
    """Open heat status levels."""
    GREEN = "green"   # <5%
    YELLOW = "yellow" # 5-8%
    RED = "red"       # >8%


class SizingMode(Enum):
    """Position sizing mode based on RRR."""
    FULL = "full"         # RRR > 2
    STANDARD = "standard" # RRR 1-2
    REDUCED = "reduced"   # RRR < 1


class TrailingMAType(Enum):
    """Trailing MA type options."""
    SMA_10 = "sma_10"
    SMA_20 = "sma_20"
    EMA_10 = "ema_10"
    EMA_20 = "ema_20"
    EMA_21 = "ema_21"
    LOWER_SMA20_EMA20 = "lower_sma20_ema20"  # Clay's preference


# =============================================================================
# ENTITIES
# =============================================================================

@dataclass
class RiskContext:
    """
    Current account and risk state.
    
    Provides context for position sizing decisions.
    """
    account_value: Decimal
    risk_per_trade_dollars: Decimal
    max_position_pct: Decimal  # Max 30%
    max_open_heat_pct: Decimal  # Max 10%
    current_open_heat: Decimal
    rrr_last_20: Decimal  # Risk-reward ratio
    sizing_multiplier: Decimal  # 1.0 = full, 0.5 = half
    
    @property
    def sizing_mode(self) -> SizingMode:
        """Get sizing mode from RRR."""
        if self.rrr_last_20 > Decimal("2.0"):
            return SizingMode.FULL
        elif self.rrr_last_20 >= Decimal("1.0"):
            return SizingMode.STANDARD
        return SizingMode.REDUCED


@dataclass
class PositionSize:
    """
    Result of position sizing calculation.
    
    Contains all details for a potential trade.
    """
    symbol: str
    entry_price: Decimal
    stop_price: Decimal
    stop_distance: Decimal
    stop_distance_pct: Decimal
    risk_dollars: Decimal
    shares: int
    position_value: Decimal
    position_pct: Decimal  # % of account
    is_valid: bool
    validation_errors: List[str] = field(default_factory=list)
    
    @property
    def risk_reward_at_target(self) -> Decimal:
        """Placeholder for R:R calculation when target is known."""
        return Decimal("0")


@dataclass
class PositionRisk:
    """
    Risk parameters for an open position.
    """
    symbol: str
    shares: int
    entry_price: Decimal
    current_stop: Decimal
    risk_dollars: Decimal
    risk_pct: Decimal  # % of account


@dataclass
class OpenHeat:
    """
    Portfolio-level risk tracking.
    
    Aggregates risk across all open positions.
    """
    total_heat_dollars: Decimal
    total_heat_pct: Decimal  # % of account
    positions: List[PositionRisk]
    status: HeatStatus
    updated_at: datetime = field(default_factory=now_utc_factory)
    
    @classmethod
    def calculate_status(cls, heat_pct: Decimal) -> HeatStatus:
        """Get status from heat percentage."""
        if heat_pct < Decimal("5.0"):
            return HeatStatus.GREEN
        elif heat_pct < Decimal("8.0"):
            return HeatStatus.YELLOW
        return HeatStatus.RED


@dataclass
class TradeRisk:
    """
    Risk parameters for an active trade.
    
    Tracks stop progression through trade lifecycle.
    """
    trade_id: UUID
    symbol: str
    entry_price: Decimal
    initial_stop: Decimal  # LOD or flag low (tactical)
    invalidation_level: Decimal  # Setup invalidation (reference only)
    current_stop: Decimal
    stop_type: StopType
    trailing_ma: Optional[TrailingMAType]
    atr: Decimal
    stop_atr_ratio: Decimal
    
    @property
    def is_stop_valid(self) -> bool:
        """Check if stop is within ATR constraint."""
        return self.stop_atr_ratio <= Decimal("1.0")


@dataclass
class HeatIndicator:
    """
    Dashboard-ready heat indicator.
    """
    total_pct: Decimal
    status: HeatStatus
    color: str  # "green", "yellow", "red"
    positions_at_risk: int
    max_allowed: Decimal
    room_remaining: Decimal
    
    @classmethod
    def from_open_heat(cls, heat: OpenHeat, max_heat_pct: Decimal) -> "HeatIndicator":
        """Create indicator from OpenHeat."""
        color_map = {
            HeatStatus.GREEN: "green",
            HeatStatus.YELLOW: "yellow",
            HeatStatus.RED: "red",
        }
        return cls(
            total_pct=heat.total_heat_pct,
            status=heat.status,
            color=color_map[heat.status],
            positions_at_risk=len(heat.positions),
            max_allowed=max_heat_pct,
            room_remaining=max_heat_pct - heat.total_heat_pct,
        )
