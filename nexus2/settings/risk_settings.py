"""
Risk Settings

User-configurable settings for the risk engine.
All settings are editable in the dashboard via Settings UI.
Based on: risk_engine_architecture.md
"""

from dataclasses import dataclass
from decimal import Decimal

from nexus2.domain.risk.models import TrailingMAType


@dataclass
class RiskSettings:
    """
    Position sizing and risk management settings.
    
    All values are KK-aligned with verified defaults.
    """
    
    # Position Sizing
    risk_per_trade_dollars: Decimal = Decimal("250.0")
    max_position_pct: Decimal = Decimal("30.0")  # KK: 20-30%
    
    # Stops
    max_atr_ratio: Decimal = Decimal("1.0")      # KK: ≤1x ATR
    ideal_atr_ratio: Decimal = Decimal("0.5")    # KK: 0.5-0.67x
    stop_order_type: str = "market"              # Fixed, safety
    
    # Open Heat
    max_heat_pct: Decimal = Decimal("10.0")      # KK: <10%
    heat_warning_pct: Decimal = Decimal("8.0")
    
    # Trailing
    default_trailing_ma: TrailingMAType = TrailingMAType.LOWER_SMA20_EMA20
    auto_intelligent_ma: bool = True             # Auto-select based on stock
    exit_on_first_close: bool = True             # KK style
    
    # Automation
    auto_place_hard_stop: bool = True
    auto_move_to_breakeven: bool = True
    auto_trail_stop: bool = True


@dataclass
class PerformanceSettings:
    """
    Settings for RRR-based sizing adjustment.
    """
    
    rrr_lookback: int = 20                       # Last 20 trades
    full_sizing_rrr: Decimal = Decimal("2.0")    # RRR > 2 = full
    reduced_sizing_rrr: Decimal = Decimal("1.0") # RRR < 1 = reduced
    reduced_multiplier: Decimal = Decimal("0.5") # 50% size when cold


@dataclass
class PartialExitSettings:
    """
    Settings for partial profit-taking.
    
    KK style: Sell 1/3 to 1/2 after 3-5 days when up 10-15%.
    """
    
    partial_exit_fraction: Decimal = Decimal("0.33")  # 1/3
    partial_exit_days: int = 5                        # KK: 3-5 days
    partial_exit_gain_pct: Decimal = Decimal("10.0")  # KK: 10-15%
    require_both_conditions: bool = True              # Days AND gain
    auto_execute: bool = True                         # Auto-execute partial
    move_to_breakeven_after: bool = True              # Auto move stop to BE
