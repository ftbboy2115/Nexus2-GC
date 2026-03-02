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
    partial_exit_fraction: float = 0.25  # Sell 25% at target (sweep: 0%=$356K, 25%=$299K, 50%=$233K)
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
    
    # EoD Entry Cutoff & Progressive Spread Gates (Feb 27 fix)
    # Prevents new entries in late post-market; tightens spread requirements after hours
    eod_entry_cutoff_time: str = "19:00"  # Block ALL new entries after 7 PM ET
    eod_phase1_max_spread_pct: float = 2.0  # Post-market (4-6 PM): max 2% spread
    eod_phase2_max_spread_pct: float = 1.0  # Late post-market (6-7 PM): max 1% spread
    
    # Spread Exit (liquidity protection)
    enable_spread_exit: bool = True
    max_spread_percent: float = 3.0  # Exit if spread exceeds 3%
    spread_grace_period_seconds: int = 60  # Wait 60s after entry before checking spread
    
    # Scaling In (Ross Cameron Methodology)
    # ⚠️ ACCIDENTAL BEHAVIOR (Feb 16, 2026): With enable_improved_scaling=False,
    # the pullback zone check always evaluates to True (line 133 of warrior_monitor_scale.py:
    # is_pullback_zone = current_price <= entry OR allow_scale_below_entry). Combined with
    # last_scale_attempt=None on first check (cooldown guard skipped), this produces a single
    # scale on the first eligible bar for EVERY case → 1.5x position size → +$3,681 (+38% P&L).
    # This is NOT intentional but IS profitable. Keeping until proper Ross scaling is built.
    # See: reports/2026-02-16/research_ross_add_methodology.md for redesign plan.
    enable_scaling: bool = True  # Ross adds on strength - enabled by default
    max_scale_count: int = 4  # Starter position + up to 3 adds (sweep: 2=$233K, 4=$278K, 5=$278K)
    scale_size_pct: int = 50  # Add 50% of original size
    min_rvol_for_scale: float = 2.0  # Volume confirmation (2x relative volume)
    allow_scale_below_entry: bool = True  # Allow scaling on pullback to support below entry
    move_stop_to_breakeven_after_scale: bool = False  # Keep technical stop after scale (Ross Cameron)
    
    # Scaling v2: Ross Cameron Level-Break Methodology
    # Replaces accidental pullback scaling with structural level breaks ($X.00, $X.50)
    # A/B testable: enable_level_break_scaling=True (new) vs False (accidental legacy)
    # Feb 27 2026: Redesigned as "Take Profit → Add Back" (Ross §3.1)
    # Level-break scaling now REQUIRES a prior partial exit before adding back.
    # This prevents naked pyramiding (v2 regression: -$91K). Ross's cycle:
    #   sell partial at $7 → stock holds → add back at $7.01 → sell at $7.50 → repeat
    enable_level_break_scaling: bool = False  # Level-break disabled; structural exits enabled
    level_break_increment: float = 0.50       # $0.50 = whole + half dollar levels
    level_break_min_distance_cents: int = 10  # Skip levels closer than 10¢ from reference
    level_break_macd_gate: bool = True        # MACD negative blocks scaling (fail-closed)
    level_break_macd_tolerance: float = -0.02 # MACD histogram tolerance (matches entry gate)
    level_break_max_add_backs: int = 10       # Max add-back cycles (effectively unlimited; Ross keeps going until stock stops holding)
    level_break_hold_bars: int = 2            # Stock must hold above partial level for N bars before add-back
    level_break_require_partial: bool = True  # MUST have taken partial profit before add-back (Ross methodology)
    
    # Guard Toggles (for GC param sweep A/B testing)
    enable_profit_check_guard: bool = False  # Block adds when position >25% gain (not Ross methodology, for A/B testing)
    
    # L2 Entry Gate (order book conditions before entry)
    l2_gate_mode: str = "log_only"         # "log_only" | "warn" | "block"
    l2_wall_threshold_volume: int = 10000  # Minimum volume to count as a wall
    l2_wall_proximity_pct: float = 1.0     # Wall must be within X% above entry to trigger
    
    # Momentum Scaling (add on strength — Ross adds at $10, $11, $12 etc.)
    # Independent from pullback scaling above — uses separate counters for A/B testing
    enable_momentum_adds: bool = False      # A/B testable: add shares on breakout continuation
    momentum_add_interval: float = 1.00     # Min price move above last add/entry before triggering ($1)
    momentum_add_size_pct: int = 50         # Size of each momentum add (% of original position)
    max_momentum_adds: int = 3              # Max momentum adds per position
    
    # Re-Entry After Profit Exit
    max_reentry_count: int = 3  # Max re-entries per symbol (3 = 4 total entries; A/B tested: +$133 vs unrestricted)
    block_reentry_after_loss: bool = True  # Fix 6: Block re-entry if last exit was a loss (no revenge trading)
    max_reentry_after_loss: int = 3  # Fix 7: Allow N consecutive losses before blocking (Ross: 3-5 trades/stock)
    live_reentry_cooldown_minutes: int = 10  # Live-mode cooldown: wait N minutes after exit before re-entry (matches sim cooldown)
    
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
    base_hit_profit_pct: float = 0.0  # Fix 2: REJECTED — net negative alone and combined with Fix 1
    base_hit_stop_cents: Decimal = Decimal("15")  # Mental stop at -15¢
    
    # Structural Profit Levels (Fix 3: A/B testable)
    # When enabled, replaces flat +18¢ fallback with next structural price level
    # Ross Cameron exits at whole/half dollar levels ($5, $5.50, $6, etc.)
    enable_structural_levels: bool = True  # Scaling v2: enabled for structural level exits
    structural_level_increment: float = 0.50  # $0.50 = whole + half dollars
    structural_level_min_distance_cents: int = 10  # Skip levels closer than 10¢
    
    # Base Hit Candle Trail (Phase A — Ross Cameron candle-low trailing)
    base_hit_candle_trail_enabled: bool = True  # Enable candle-low trailing for base_hit
    base_hit_trail_activation_cents: Decimal = Decimal("15")  # Start trailing after +15¢ (was 10¢)
    trail_activation_pct: float = 0.0  # Fix 2: REJECTED — net negative alone and combined with Fix 1
    candle_trail_lookback_bars: int = 2  # Trail = lowest low of last N completed candles (was 1)
    
    # Home Run Mode Settings  
    home_run_partial_at_r: float = 2.0  # Take 50% partial at 2:1 R
    home_run_trail_after_r: float = 1.5  # Start trailing stop after 1.5R
    home_run_trail_percent: float = 0.20  # Trail 20% below high_since_entry
    home_run_move_to_be: bool = True  # Move stop to breakeven after partial
    
    # Partial-Then-Ride (Fix 1: A/B testable)
    # When True: base_hit exits sell 50% and switch remainder to home_run trailing
    # When False: base_hit exits sell 100% (current behavior)
    enable_partial_then_ride: bool = True  # Fix 1: Combined test with Fix 2.
    
    # Home Run Trail Improvement (Fix 4: REJECTED — all sub-fixes neutral or harmful)
    enable_improved_home_run_trail: bool = False  # Fix 4: REJECTED
    home_run_stop_after_partial: str = "trail_level"  # 4a: neutral (trail_level ≈ breakeven)
    home_run_skip_topping_tail: bool = True  # 4b: neutral (topping tail never fires on these cases)
    home_run_candle_trail_enabled: bool = False  # 4c: REJECTED — -16% regression, trail too tight
    home_run_candle_trail_lookback: int = 5  # N-bar low (wider than base_hit's 2)
    
    # Scaling Fix (Fix 5: sim-aware cooldown + pullback zone)
    # When True: skip wall-clock cooldown in sim, strict pullback zone → barely better than no scaling
    # When False: accidental 1-scale-per-case behavior → +38% P&L (see comment above)
    # True baseline comparison: enable_scaling=False → $9,617 (true un-scaled)
    enable_improved_scaling: bool = False  # Fix 5: KEEP OFF — redesigning scaling per Ross methodology


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
    last_momentum_add_price: Optional[Decimal] = None  # Track price of last momentum add
    momentum_add_count: int = 0                         # Number of momentum adds taken
    last_level_break_price: Optional[Decimal] = None    # Scaling v2: price of last level-break scale-in
    recovered_at: Optional[datetime] = None  # When position was recovered from broker sync (grace period)
    
    # Take Profit → Add Back tracking (Ross §3.1: sell at level → add back if holds)
    partial_profit_locked: bool = False                  # True after structural partial exit (ready for add-back)
    last_partial_level: Optional[Decimal] = None         # Price level where partial was taken
    last_partial_shares: int = 0                         # How many shares were sold in partial (add-back size)
    add_back_count: int = 0                              # How many add-back cycles completed
    bars_since_partial: int = 0                          # Bars elapsed since partial exit (for hold confirmation)
    
    # Intraday candle tracking (for pattern exits)
    last_candle_low: Decimal = Decimal("0")
    last_candle_high: Decimal = Decimal("0")
    candles_since_entry: int = 0
    
    # Candle-low trailing stop (Phase A — None = not yet activated)
    candle_trail_stop: Optional[Decimal] = None
    
    # Exit Mode Override (per-position, overrides session mode)
    # None = inherit session_exit_mode, "base_hit" or "home_run" = override
    exit_mode_override: Optional[str] = None
