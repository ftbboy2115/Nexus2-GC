"""
Warrior Trading Types

Shared enums and dataclasses for Warrior Trading position monitoring.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
from nexus2.utils.time_utils import now_utc_factory


# =============================================================================
# ENUMS
# =============================================================================

class WarriorExitReason(Enum):
    """Reasons for exiting a Warrior position."""
    MENTAL_STOP = "mental_stop"  # 10-20 cents
    TECHNICAL_STOP = "technical_stop"  # Support level
    CANDLE_UNDER_CANDLE = "candle_under_candle"  # New low
    TOPPING_TAIL = "topping_tail"  # Rejection at highs
    PROFIT_TARGET = "profit_target"  # 2:1 R
    PARTIAL_EXIT = "partial_exit"  # 50% at target
    BREAKOUT_FAILURE = "breakout_failure"  # Failed to hold breakout
    TIME_STOP = "time_stop"  # No momentum after entry
    AFTER_HOURS_EXIT = "after_hours_exit"  # Forced exit before overnight hold
    SPREAD_EXIT = "spread_exit"  # Liquidity drying up - spread too wide
    MANUAL = "manual"


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class WarriorExitSignal:
    """Signal to exit a Warrior position."""
    position_id: str
    symbol: str
    reason: WarriorExitReason
    exit_price: Decimal
    shares_to_exit: int
    pnl_estimate: Decimal
    stop_price: Decimal = Decimal("0")
    generated_at: datetime = field(default_factory=now_utc_factory)
    
    # Analytics
    r_multiple: float = 0.0
    trigger_description: str = ""
    
    # Escalating exit - offset percent below bid (e.g., 0.02 = 2% below bid)
    exit_offset_percent: float = 0.01  # Default 1%


@dataclass
class WarriorMonitorSettings:
    """Settings for Warrior position monitoring."""
    # Mental Stop (fallback only - Ross uses low of entry candle)
    mental_stop_cents: Decimal = Decimal("50")  # FALLBACK ONLY - set high (50¢) to rarely trigger
    use_candle_low_stop: bool = True  # Ross's actual method: low of entry candle
    use_technical_stop: bool = True  # Also use support levels
    technical_stop_buffer_cents: Decimal = Decimal("5")  # 2-5 cents below support
    
    # Profit Targets (Ross-style: can use fixed cents OR R-multiple)
    profit_target_cents: Decimal = Decimal("0")  # If > 0, use fixed cents (e.g., 20 = +20¢)
    profit_target_r: float = 2.0  # 2:1 R target (used if profit_target_cents = 0)
    partial_exit_fraction: float = 0.5  # Sell 50% at target
    # NOTE: move_stop_to_breakeven REMOVED - this is KK methodology, not Ross Cameron
    # Ross does not explicitly advocate moving stop to breakeven after partials

    
    # Character Exit Patterns
    enable_candle_under_candle: bool = True
    candle_exit_grace_seconds: int = 60  # Wait 60s after entry before this exit can trigger
    candle_exit_volume_multiplier: float = 1.5  # Require >1.5x avg volume OR 5m red confirmation
    candle_exit_only_when_red: bool = True  # Skip CUC when position is profitable (let trail manage)

    enable_topping_tail: bool = True
    topping_tail_threshold: float = 0.6  # Wick > 60% of candle range
    
    # Time Stop (no momentum)
    enable_time_stop: bool = False  # Disabled: kills winners (NPT -$1740). Ross accepts losses.
    time_stop_seconds: int = 600  # 10 minutes without momentum
    breakout_hold_threshold: float = 0.5  # Must hold 50% of breakout
    
    # After-Hours Exit (prevent overnight holds)
    enable_after_hours_exit: bool = True
    tighten_stop_time_et: str = "18:00"  # 6 PM ET - tighten stops to breakeven
    force_exit_time_et: str = "19:30"  # 7:30 PM ET - force exit all positions
    
    # Spread Exit (liquidity protection)
    enable_spread_exit: bool = True
    max_spread_percent: float = 3.0  # Exit if spread exceeds 3%
    spread_grace_period_seconds: int = 60  # Wait 60s after entry before checking spread
    
    # Scaling In (Ross Cameron Methodology)
    enable_scaling: bool = True  # Ross adds on strength - enabled by default
    max_scale_count: int = 2  # Starter position + 1-2 adds
    scale_size_pct: int = 50  # Add 50% of original size
    min_rvol_for_scale: float = 2.0  # Volume confirmation (2x relative volume)
    allow_scale_below_entry: bool = True  # Allow scaling on pullback to support below entry
    move_stop_to_breakeven_after_scale: bool = False  # Keep technical stop after scale (Ross Cameron)
    
    # Re-Entry After Profit Exit
    max_reentry_count: int = 3  # Max re-entries per symbol (3 = 4 total entries; A/B tested: +$133 vs unrestricted)
    
    # Polling
    check_interval_seconds: int = 2  # Fast polling for day trading
    
    # ==========================================================================
    # EXIT MODE CONFIGURATION (Ross Cameron: Base Hit vs Home Run)
    # ==========================================================================
    # Session-level mode: "base_hit" or "home_run"
    # Base hits = quick 10-20¢ profits (cold market / first trade of day)
    # Home runs = hold for bigger moves, trail stops (hot market / high conviction)
    session_exit_mode: str = "base_hit"  # Default to safer base hit mode
    
    # Base Hit Mode Settings
    base_hit_profit_cents: Decimal = Decimal("18")  # Take profit at +18¢ (Ross's typical)
    base_hit_stop_cents: Decimal = Decimal("15")  # Mental stop at -15¢
    
    # Base Hit Candle Trail (Phase A — Ross Cameron candle-low trailing)
    base_hit_candle_trail_enabled: bool = True  # Enable candle-low trailing for base_hit
    base_hit_trail_activation_cents: Decimal = Decimal("15")  # Start trailing after +15¢ (was 10¢)
    candle_trail_lookback_bars: int = 2  # Trail = lowest low of last N completed candles (was 1)
    
    # Home Run Mode Settings  
    home_run_partial_at_r: float = 2.0  # Take 50% partial at 2:1 R
    home_run_trail_after_r: float = 1.5  # Start trailing stop after 1.5R
    home_run_trail_percent: float = 0.20  # Trail 20% below high_since_entry
    home_run_move_to_be: bool = True  # Move stop to breakeven after partial


@dataclass
class WarriorPosition:
    """
    A Warrior Trading position being monitored.
    
    Contains entry details and intraday tracking.
    """
    position_id: str
    symbol: str
    entry_price: Decimal
    shares: int
    entry_time: datetime
    
    # Stops
    mental_stop: Decimal  # Entry - N cents
    technical_stop: Optional[Decimal] = None  # Support level
    current_stop: Decimal = Decimal("0")  # Active stop
    
    # Targets
    profit_target: Decimal = Decimal("0")  # 2:1 R price
    risk_per_share: Decimal = Decimal("0")  # Entry - stop
    
    # Tracking
    high_since_entry: Decimal = Decimal("0")  # For trailing / MFE
    low_since_entry: Decimal = Decimal("999999")  # For MAE tracking (init high so first price updates it)
    partial_taken: bool = False
    
    # Scaling In
    scale_count: int = 0  # Number of adds taken
    original_shares: int = 0  # Initial position size (for calculating add size)
    last_scale_attempt: Optional[datetime] = None  # Track last scale attempt for cooldown
    recovered_at: Optional[datetime] = None  # When position was recovered from broker sync (grace period)
    
    # Intraday candle tracking (for pattern exits)
    last_candle_low: Decimal = Decimal("0")
    last_candle_high: Decimal = Decimal("0")
    candles_since_entry: int = 0
    
    # Candle-low trailing stop (Phase A — None = not yet activated)
    candle_trail_stop: Optional[Decimal] = None
    
    # Exit Mode Override (per-position, overrides session mode)
    # None = inherit session_exit_mode, "base_hit" or "home_run" = override
    exit_mode_override: Optional[str] = None
