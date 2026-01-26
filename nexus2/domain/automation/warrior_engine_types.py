"""
Warrior Engine Types

Shared enums and dataclasses for the Warrior Trading automation engine.
Extracted from warrior_engine.py for modularity.
"""

from datetime import datetime, time as dt_time
from decimal import Decimal
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

# Import for type reference
from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate


# =============================================================================
# ENUMS
# =============================================================================


class WarriorEngineState(Enum):
    """State of the Warrior engine."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    PREMARKET = "premarket"  # Before 9:30, scanning only


class EntryTriggerType(Enum):
    """Type of entry trigger."""
    ORB = "orb"  # Opening Range Breakout (9:30 AM)
    PMH_BREAK = "pmh_break"  # Pre-Market High breakout
    BULL_FLAG = "bull_flag"  # First green after pullback
    VWAP_RECLAIM = "vwap_reclaim"  # Reclaim VWAP with volume
    VWAP_BREAK = "vwap_break"  # Break above VWAP after consolidation below (Ross: Jan 20 2026)
    DIP_FOR_LEVEL = "dip_for_level"  # Dip + level break (Ross: TNMG $3.93 → $4.00)
    PULLBACK = "pullback"  # General pullback entry (first candle new high)
    MICRO_PULLBACK = "micro_pullback"  # For extended stocks (>100% gap): swing high break


# =============================================================================
# CONFIG DATACLASSES
# =============================================================================


@dataclass
class WarriorEngineConfig:
    """Configuration for Warrior automation engine."""
    # Trading Window - Extended hours for Warrior (4 AM - 7:30 PM ET)
    # Ross trades 7 AM - 10 AM, but we allow full extended window
    market_open: dt_time = field(default_factory=lambda: dt_time(4, 0))  # Pre-market start
    trading_window_end: dt_time = field(default_factory=lambda: dt_time(19, 30))  # Last entry at 7:30 PM
    market_close: dt_time = field(default_factory=lambda: dt_time(20, 0))  # Extended hours end
    
    # Pre-market scan (Ross starts watching at 7 AM)
    premarket_scan_time: dt_time = field(default_factory=lambda: dt_time(7, 0))
    
    # ORB Settings
    orb_timeframe_minutes: int = 1  # 1-minute ORB
    orb_enabled: bool = True
    
    # PMH Breakout
    pmh_enabled: bool = True
    pmh_buffer_cents: Decimal = Decimal("5")  # Buy 5 cents above PMH
    
    # VWAP Break - Ross Cameron (Jan 20 2026): "I took this trade for the break through VWAP"
    vwap_break_enabled: bool = True
    
    # Scanner
    scanner_interval_minutes: int = 5
    max_candidates: int = 5
    
    # Entry Selectivity - Ross Cameron (Jan 20 2026): Only take the "A+ setup"
    # "TWWG was the ONLY trade I took today" - quality over quantity
    top_pick_only: bool = True  # Only enter highest-scoring candidate
    min_entry_score: int = 6  # Minimum score to consider for entry (was 0)
    
    # Risk
    risk_per_trade: Decimal = Decimal("125")  # $125 per trade
    max_positions: int = 10  # Higher default for testing
    max_daily_loss: Decimal = Decimal("999999")  # Disabled for testing
    max_capital: Decimal = Decimal("5000")  # Max capital per trade
    
    # Position Sizing Limits (for testing with small positions)
    max_shares_per_trade: Optional[int] = 1  # Hard cap on shares (e.g., 1 for testing)
    max_value_per_trade: Optional[Decimal] = None  # Hard cap on $ value (e.g., 100)
    
    # Blacklist - symbols to never trade
    static_blacklist: set = field(default_factory=lambda: {"PLBY"})
    
    # Entry Spread Filter - reject entries with wide bid-ask spreads
    max_entry_spread_percent: float = 3.0  # 3% threshold (Ross Cameron avoids >2-3%)
    
    # Execution
    sim_only: bool = False  # Default to paper trading on Alpaca
    
    # Debug
    debug_catalyst: bool = True  # Temp: debug catalyst detection
    
    # DIP-FOR-LEVEL entry pattern (Phase 2 expansion)
    # Ross methodology: candle-based detection, not fixed % thresholds
    dip_for_level_enabled: bool = True  # Enable dip-for-level entries
    pullback_enabled: bool = True  # Enable general pullback entries
    bull_flag_enabled: bool = True  # Enable bull flag pattern (first green after red pullback)
    level_proximity_cents: int = 10  # How close to level to trigger (default 10c)
    level_granularity: str = "quarter"  # "quarter" ($0.25), "half" ($0.50), "whole" ($1.00)
    require_macd_positive: bool = True  # Ross-confirmed: MACD must be positive for entry
    
    # MICRO-PULLBACK settings (for extended stocks)
    micro_pullback_enabled: bool = True  # Enable micro-pullback entries for extended stocks
    extension_threshold: float = 200.0  # Gap % above which to use micro-pullback instead of PMH (was 100, raised to fix PAVM regression)
    micro_pullback_min_dip: float = 1.0  # Minimum pullback % to trigger (too shallow = no setup)
    micro_pullback_max_dip: float = 5.0  # Maximum pullback % (deeper = reversal, not pullback)
    micro_pullback_macd_tolerance: float = -0.10  # Allow MACD slightly negative for scalps (Ross relaxes rule)


@dataclass
class WarriorEngineStats:
    """Runtime statistics for the engine."""
    started_at: Optional[datetime] = None
    scans_run: int = 0
    candidates_found: int = 0  # Unique candidates found (not duplicates)
    entries_triggered: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    daily_pnl: Decimal = Decimal("0")
    last_scan_at: Optional[datetime] = None
    last_error: Optional[str] = None
    _seen_candidates: set = field(default_factory=set)  # Track unique symbols


@dataclass
class WatchedCandidate:
    """A candidate being watched for entry trigger."""
    candidate: WarriorCandidate
    pmh: Decimal  # Pre-market high
    orb_high: Optional[Decimal] = None  # Opening range high
    orb_low: Optional[Decimal] = None  # Opening range low
    orb_established: bool = False
    entry_triggered: bool = False
    entry_attempt_count: int = 0  # Track re-entry attempts (Ross: MACD gate on re-entry)
    last_below_pmh: bool = False  # True if price was below PMH since last entry attempt
    last_below_vwap: bool = False  # True if price was below VWAP (for VWAP break detection)
    added_at: datetime = field(default_factory=datetime.utcnow)
    
    # Level tracking for DIP_FOR_LEVEL pattern (Phase 2 expansion)
    recent_high: Optional[Decimal] = None  # Intraday high for pullback detection
    dip_from_high_pct: float = 0.0  # Current pullback depth %
    target_level: Optional[Decimal] = None  # Nearest psychological level
    
    # VWAP/EMA tracking for dynamic scoring (Ross: trend matters for TOP_PICK_ONLY)
    current_vwap: Optional[Decimal] = None  # Current VWAP value
    current_ema_9: Optional[Decimal] = None  # Current 9 EMA value
    current_price: Optional[Decimal] = None  # Last known price
    is_above_vwap: bool = False  # True if price > VWAP
    is_above_ema_9: bool = False  # True if price > 9 EMA
    trend_updated_at: Optional[datetime] = None  # When trend data was last updated
    
    # Bull flag pattern tracking (Ross: "first green after pullback")
    last_candle_was_green: Optional[bool] = None  # Track previous candle color
    consecutive_red_candles: int = 0  # Count of consecutive red candles before potential flag break
    
    # Candle Over Candle confirmation (Ross: "buy as second candle breaks high of first")
    # When PMH is first exceeded, we store the candle's high as control_candle_high.
    # Entry only triggers when a SUBSEQUENT candle breaks this high.
    # This naturally filters rejection wicks (like LCFY 08:01 with high $7.26, close $6.20)
    control_candle_high: Optional[Decimal] = None  # High of control candle for confirmation
    control_candle_time: Optional[str] = None  # Time string of control candle (e.g., "08:01")
    
    # MICRO-PULLBACK tracking (for extended stocks >100% gap)
    swing_high: Optional[Decimal] = None  # Recent local high for micro-pullback detection
    swing_high_time: Optional[str] = None  # When swing high was set
    pullback_low: Optional[Decimal] = None  # Low after swing high (pullback depth)
    micro_pullback_ready: bool = False  # Pullback detected, ready for entry on break
    
    @property
    def dynamic_score(self) -> int:
        """
        Calculate dynamic score for TOP_PICK_ONLY ranking.
        
        Adds trend bonus to quality_score:
        - +3 if above VWAP AND above 9 EMA (trending strongly)
        - +1 if above VWAP only
        - -2 if below VWAP (fading/weak)
        
        This ensures trending stocks like BNAI outrank fading stocks like RVYL
        even if RVYL has higher static metrics (RVOL, price sweet spot).
        """
        base_score = getattr(self.candidate, 'quality_score', 0) or 0
        
        # Trend bonus (only if we have VWAP data)
        if self.current_vwap is not None and self.current_price is not None:
            if self.is_above_vwap:
                if self.is_above_ema_9:
                    base_score += 3  # Strong trend: above both VWAP and 9 EMA
                else:
                    base_score += 1  # Moderate: above VWAP but below 9 EMA
            else:
                base_score -= 2  # Weak/fading: below VWAP
        
        return max(base_score, 0)  # Don't go negative


