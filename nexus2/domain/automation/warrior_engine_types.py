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
    level_proximity_cents: int = 10  # How close to level to trigger (default 10c)
    level_granularity: str = "quarter"  # "quarter" ($0.25), "half" ($0.50), "whole" ($1.00)
    require_macd_positive: bool = True  # Ross-confirmed: MACD must be positive for entry


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

