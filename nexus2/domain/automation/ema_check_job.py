"""
End-of-Day MA Check Job

KK-style trailing stop: Exit on daily close below 10/20 MA.

This job should run during the LAST 15 MINUTES of market day (3:45-4:00 PM ET)
so that exits can be submitted as market orders before close.

Supports:
- EMA (exponential moving average)
- SMA (simple moving average)
- Lower of EMA/SMA (whichever is lower acts as tighter stop)
- AUTO mode with affinity-based selection (analyzes consolidation surfing)
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from decimal import Decimal
from typing import Optional, List, Callable
from enum import Enum


logger = logging.getLogger(__name__)


class TrailingMAType(Enum):
    """Which moving average to use for trailing."""
    AUTO = "auto"        # Auto-select based on affinity/ADR% (KK-style enhanced)
    EMA_10 = "ema_10"    # 10 EMA (fast movers)
    EMA_20 = "ema_20"    # 20 EMA (slower stocks)
    SMA_10 = "sma_10"    # 10 SMA
    SMA_20 = "sma_20"    # 20 SMA
    LOWER_10 = "lower_10"  # Lower of 10 EMA and 10 SMA (tight trailing)
    LOWER_20 = "lower_20"  # Lower of 20 EMA and 20 SMA (conservative)


@dataclass
class MAExitSignal:
    """Signal to exit position due to daily close below MA."""
    position_id: str
    symbol: str
    daily_close: Decimal
    ma_value: Decimal
    ma_type: TrailingMAType
    days_held: int
    generated_at: datetime = None
    
    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = datetime.utcnow()


@dataclass
class MACheckResult:
    """Result of end-of-day MA check."""
    positions_checked: int
    exit_signals: List[MAExitSignal]
    errors: List[str]
    check_time: datetime
    is_within_timing_window: bool


def is_within_eod_window() -> bool:
    """
    Check if current time is within the last 15 minutes of market day.
    Market closes at 4:00 PM ET (20:00 UTC during EST, 21:00 UTC during EDT).
    
    Window: 3:45 PM - 4:00 PM ET
    """
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)
    
    # Last 15 minutes: 3:45 PM to 4:00 PM
    start_window = time(15, 45)
    end_window = time(16, 0)
    
    current_time = now_et.time()
    return start_window <= current_time <= end_window


class MACheckJob:
    """
    End-of-day job to check positions against their trailing MA.
    
    KK methodology:
    - Day 1: LoD stop (broker-side)
    - Day 2: Discretionary (LoD reference)
    - Day 3-5: Partial exits, move to breakeven
    - Day 5+: Trail with MA close
    
    Run during last 15 min of market (3:45-4:00 PM ET) for market order exits.
    """
    
    def __init__(
        self,
        min_days_for_trailing: int = 5,  # Start MA trailing after day 5
        default_ma_type: TrailingMAType = TrailingMAType.EMA_10,
        require_timing_window: bool = False,  # If True, only run in 3:45-4:00 PM ET
    ):
        self.min_days_for_trailing = min_days_for_trailing
        self.default_ma_type = default_ma_type
        self.require_timing_window = require_timing_window
        self.adr_threshold = 5.0  # KK uses 5% as fast vs slow threshold
        
        # Callbacks
        self._get_positions: Optional[Callable] = None  # Returns list of open positions
        self._get_daily_close: Optional[Callable] = None  # (symbol) -> Decimal
        self._get_ema: Optional[Callable] = None  # (symbol, period) -> Decimal
        self._get_sma: Optional[Callable] = None  # (symbol, period) -> Decimal
        self._get_adr_percent: Optional[Callable] = None  # (symbol, period) -> Decimal for auto-select
        self._get_price_history: Optional[Callable] = None  # (symbol, days) -> List[dict] for affinity
        self._get_current_date: Optional[Callable] = None  # () -> date (for simulation clock)
        self._execute_exit: Optional[Callable] = None  # (position_id, shares, reason) -> None
        
        # Position-specific MA affinity (overrides AUTO selection)
        self._position_affinities: dict = {}  # {position_id: "10" or "20"}
        
        # Stats
        self.last_check: Optional[datetime] = None
        self.total_checks: int = 0
        self.total_exits: int = 0
    
    def set_callbacks(
        self,
        get_positions: Callable = None,
        get_daily_close: Callable = None,
        get_ema: Callable = None,
        get_sma: Callable = None,
        get_adr_percent: Callable = None,
        get_price_history: Callable = None,
        get_current_date: Callable = None,
        execute_exit: Callable = None,
    ):
        """Set callbacks for data access and execution."""
        if get_positions:
            self._get_positions = get_positions
        if get_daily_close:
            self._get_daily_close = get_daily_close
        if get_ema:
            self._get_ema = get_ema
        if get_sma:
            self._get_sma = get_sma
        if get_adr_percent:
            self._get_adr_percent = get_adr_percent
        if get_price_history:
            self._get_price_history = get_price_history
        if get_current_date:
            self._get_current_date = get_current_date
        if execute_exit:
            self._execute_exit = execute_exit
    
    def set_position_affinity(self, position_id: str, affinity: str):
        """
        Set MA affinity for a specific position.
        
        Called when position is created from a signal that has affinity data.
        
        Args:
            position_id: Position ID
            affinity: "10" or "20"
        """
        if affinity in ("10", "20"):
            self._position_affinities[position_id] = affinity
            logger.debug(f"[MACheck] Set affinity for {position_id}: {affinity}")
    
    async def run(self, dry_run: bool = True) -> MACheckResult:
        """
        Run the end-of-day MA check.
        
        Args:
            dry_run: If True, only log what would happen without executing exits
            
        Returns:
            MACheckResult with positions checked and exit signals
        """
        within_window = is_within_eod_window()
        
        # Check timing window if required
        if self.require_timing_window and not within_window:
            logger.info("[MACheck] Outside trading window (3:45-4:00 PM ET), skipping check")
            return MACheckResult(
                positions_checked=0,
                exit_signals=[],
                errors=["Outside timing window (3:45-4:00 PM ET)"],
                check_time=datetime.utcnow(),
                is_within_timing_window=within_window,
            )
        
        logger.info(f"[MACheck] Starting MA check (within timing window: {within_window})...")
        
        errors = []
        exit_signals = []
        positions_checked = 0
        
        # Get open positions
        if not self._get_positions:
            return MACheckResult(
                positions_checked=0,
                exit_signals=[],
                errors=["No get_positions callback configured"],
                check_time=datetime.utcnow(),
                is_within_timing_window=within_window,
            )
        
        try:
            positions = await self._get_positions()
        except Exception as e:
            logger.error(f"[MACheck] Failed to get positions: {e}")
            return MACheckResult(
                positions_checked=0,
                exit_signals=[],
                errors=[f"Failed to get positions: {e}"],
                check_time=datetime.utcnow(),
                is_within_timing_window=within_window,
            )
        
        if not positions:
            logger.info("[MACheck] No open positions to check")
            return MACheckResult(
                positions_checked=0,
                exit_signals=[],
                errors=[],
                check_time=datetime.utcnow(),
                is_within_timing_window=within_window,
            )
        
        # Check each position
        for position in positions:
            try:
                signal = await self._check_position(position)
                positions_checked += 1
                
                if signal:
                    exit_signals.append(signal)
                    
                    if not dry_run and self._execute_exit:
                        logger.info(f"[MACheck] Executing exit for {signal.symbol}")
                        await self._execute_exit(
                            signal.position_id,
                            position.get("remaining_shares", 0),
                            f"MA close: {signal.daily_close} < {signal.ma_type.value}({signal.ma_value})"
                        )
                        self.total_exits += 1
                    else:
                        logger.info(
                            f"[MACheck] DRY RUN: Would exit {signal.symbol} "
                            f"(close {signal.daily_close} < {signal.ma_type.value} {signal.ma_value})"
                        )
            except Exception as e:
                symbol = position.get("symbol", "unknown")
                logger.error(f"[MACheck] Error checking {symbol}: {e}")
                errors.append(f"{symbol}: {e}")
        
        self.last_check = datetime.utcnow()
        self.total_checks += 1
        
        logger.info(
            f"[MACheck] Complete: {positions_checked} checked, "
            f"{len(exit_signals)} exit signals"
        )
        
        return MACheckResult(
            positions_checked=positions_checked,
            exit_signals=exit_signals,
            errors=errors,
            check_time=datetime.utcnow(),
            is_within_timing_window=within_window,
        )
    
    async def _check_position(self, position: dict) -> Optional[MAExitSignal]:
        """
        Check a single position for MA close exit.
        
        Supports EMA, SMA, and lower-of-both modes.
        Returns MAExitSignal if position should be exited.
        """
        symbol = position.get("symbol", "")
        position_id = position.get("id", "")
        opened_at = position.get("opened_at")
        
        if not symbol or not position_id:
            return None
        
        # Calculate days held
        if isinstance(opened_at, str):
            opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        elif isinstance(opened_at, datetime):
            pass
        else:
            # Fallback: use current Eastern Time (market time) 
            from zoneinfo import ZoneInfo
            et = ZoneInfo("America/New_York")
            opened_at = datetime.now(et)
        
        # Use simulation date if callback provided, otherwise use Eastern Time
        if self._get_current_date:
            current_date = self._get_current_date()
        else:
            # Use Eastern Time (market time) for day calculations
            from zoneinfo import ZoneInfo
            et = ZoneInfo("America/New_York")
            current_date = datetime.now(et).date()
        
        # Convert opened_at to date for comparison (handle timezone-naive datetimes)
        opened_date = opened_at.date() if isinstance(opened_at, datetime) else opened_at
        days_held = (current_date - opened_date).days
        
        # KK Methodology: Character change logic (close < BOTH EMAs) always applies Days 0-4
        # Mature trailing (single MA) only starts Day 5+
        # The min_days_for_trailing setting controls WHEN mature trailing kicks in,
        # but character change checks must ALWAYS run for early positions
        CHARACTER_CHANGE_CUTOFF = 5  # Days 0-4 use character change logic
        is_mature = days_held >= max(self.min_days_for_trailing, CHARACTER_CHANGE_CUTOFF)
        
        # Get daily close
        if not self._get_daily_close:
            return None
        
        try:
            daily_close = await self._get_daily_close(symbol)
            if not daily_close:
                return None
            daily_close = Decimal(str(daily_close))
        except Exception as e:
            logger.warning(f"[MACheck] Could not get daily close for {symbol}: {e}")
            return None
        
        if is_mature:
            # Day 5+: Full MA trailing with auto-selected MA type
            ma_type = self.default_ma_type
            adr_percent = None
            
            if ma_type == TrailingMAType.AUTO:
                ma_type, adr_percent = await self._auto_select_ma(symbol, position_id)
            
            ma_value = await self._get_ma_value(symbol, ma_type)
            
            if ma_value is None:
                return None
            
            if daily_close < ma_value:
                logger.info(
                    f"[MACheck] {symbol}: Day {days_held} - Close ${daily_close} < {ma_type.value} ${ma_value} - EXIT SIGNAL"
                )
                return MAExitSignal(
                    position_id=position_id,
                    symbol=symbol,
                    daily_close=daily_close,
                    ma_value=ma_value,
                    ma_type=ma_type,
                    days_held=days_held,
                )
            
            logger.debug(
                f"[MACheck] {symbol}: Day {days_held} - Close ${daily_close} >= {ma_type.value} ${ma_value} - HOLD"
            )
            return None
        
        else:
            # Day 0-4: Check for CHARACTER CHANGE (close below BOTH 10 and 20 EMA)
            # Per KK: A daily close below MA = character change = exit regardless of days held
            # The min_days buffer is for partial profit-taking, not for ignoring trend breakdowns
            
            ema_10 = await self._get_ma_value(symbol, TrailingMAType.EMA_10)
            ema_20 = await self._get_ma_value(symbol, TrailingMAType.EMA_20)
            
            if ema_10 is None or ema_20 is None:
                logger.debug(f"[MACheck] {symbol}: Day {days_held} - Could not get MAs, skipping")
                return None
            
            # Only exit if close is below BOTH MAs (clear trend breakdown)
            if daily_close < ema_10 and daily_close < ema_20:
                logger.warning(
                    f"[MACheck] {symbol}: Day {days_held} - CHARACTER CHANGE "
                    f"(close ${daily_close} < 10EMA ${ema_10} AND < 20EMA ${ema_20}) - EXIT SIGNAL"
                )
                return MAExitSignal(
                    position_id=position_id,
                    symbol=symbol,
                    daily_close=daily_close,
                    ma_value=ema_10,  # Use tighter MA as reference
                    ma_type=TrailingMAType.EMA_10,
                    days_held=days_held,
                )
            
            logger.debug(
                f"[MACheck] {symbol}: Day {days_held} - Close ${daily_close} (10EMA=${ema_10}, 20EMA=${ema_20}) - trend intact"
            )
        return None
    
    async def _auto_select_ma(self, symbol: str, position_id: str = None) -> tuple[TrailingMAType, float]:
        """
        Auto-select MA type based on affinity and ADR% (KK-style enhanced).
        
        Priority order:
        1. Stored position affinity (from consolidation analysis at entry)
        2. Dynamic affinity analysis (if price history available)
        3. Violation count (choppy = use wider MA)
        4. ADR% threshold (5% = fast mover)
        
        Returns (selected_ma_type, adr_percent)
        """
        adr_percent = 0.0
        
        # Get ADR% for logging and fallback
        if self._get_adr_percent:
            try:
                adr = await self._get_adr_percent(symbol, 20)  # 20-day ADR
                if adr:
                    adr_percent = float(adr)
            except Exception as e:
                logger.warning(f"[MACheck] Could not get ADR% for {symbol}: {e}")
        
        # Priority 1: Check stored affinity
        if position_id and position_id in self._position_affinities:
            affinity = self._position_affinities[position_id]
            ma_type = TrailingMAType.LOWER_10 if affinity == "10" else TrailingMAType.LOWER_20
            logger.info(f"[MACheck] {symbol}: Using stored affinity -> {ma_type.value}")
            return ma_type, adr_percent
        
        # Priority 2: Dynamic affinity analysis (if price history available)
        if self._get_price_history:
            try:
                from nexus2.domain.automation.ma_affinity import (
                    analyze_ma_affinity,
                    select_trailing_ma_from_affinity,
                )
                
                prices = await self._get_price_history(symbol, 60)  # 60 days for analysis
                if prices and len(prices) >= 10:
                    affinity_data = await analyze_ma_affinity(
                        symbol=symbol,
                        prices=prices,
                        get_ema=self._get_ema,
                        get_sma=self._get_sma,
                        get_adr_percent=self._get_adr_percent,
                    )
                    
                    # Use affinity if determined
                    if affinity_data.affinity_ma in ("10", "20"):
                        ma_type_str = select_trailing_ma_from_affinity(affinity_data)
                        ma_type = TrailingMAType.LOWER_10 if ma_type_str == "LOWER_10" else TrailingMAType.LOWER_20
                        logger.info(
                            f"[MACheck] {symbol}: Dynamic affinity -> {ma_type.value} "
                            f"(affinity={affinity_data.affinity_ma}, violations={affinity_data.violations})"
                        )
                        return ma_type, adr_percent
                    
                    # Check violations (Priority 3)
                    if affinity_data.violations >= 2:
                        logger.info(f"[MACheck] {symbol}: Choppy ({affinity_data.violations} violations) -> LOWER_20")
                        return TrailingMAType.LOWER_20, adr_percent
                        
            except Exception as e:
                logger.warning(f"[MACheck] Dynamic affinity analysis failed for {symbol}: {e}")
        
        # Priority 4: ADR-based selection (fallback)
        if adr_percent >= self.adr_threshold:
            logger.info(f"[MACheck] {symbol}: ADR={adr_percent:.1f}% (fast) -> LOWER_10")
            return TrailingMAType.LOWER_10, adr_percent  # Fast mover - tight trailing
        else:
            logger.info(f"[MACheck] {symbol}: ADR={adr_percent:.1f}% (slow) -> LOWER_20")
            return TrailingMAType.LOWER_20, adr_percent  # Slower - give more room
    
    async def _get_ma_value(self, symbol: str, ma_type: TrailingMAType) -> Optional[Decimal]:
        """Get MA value based on the type specified."""
        try:
            if ma_type == TrailingMAType.EMA_10:
                if not self._get_ema:
                    return None
                val = await self._get_ema(symbol, 10)
                return Decimal(str(val)) if val else None
                
            elif ma_type == TrailingMAType.EMA_20:
                if not self._get_ema:
                    return None
                val = await self._get_ema(symbol, 20)
                return Decimal(str(val)) if val else None
                
            elif ma_type == TrailingMAType.SMA_10:
                if not self._get_sma:
                    return None
                val = await self._get_sma(symbol, 10)
                return Decimal(str(val)) if val else None
                
            elif ma_type == TrailingMAType.SMA_20:
                if not self._get_sma:
                    return None
                val = await self._get_sma(symbol, 20)
                return Decimal(str(val)) if val else None
                
            elif ma_type == TrailingMAType.LOWER_10:
                # Use the lower of 10 EMA and 10 SMA (tighter trailing for fast movers)
                ema_val = None
                sma_val = None
                
                if self._get_ema:
                    ema_val = await self._get_ema(symbol, 10)
                if self._get_sma:
                    sma_val = await self._get_sma(symbol, 10)
                
                if ema_val is None and sma_val is None:
                    return None
                
                ema_dec = Decimal(str(ema_val)) if ema_val else None
                sma_dec = Decimal(str(sma_val)) if sma_val else None
                
                if ema_dec and sma_dec:
                    return min(ema_dec, sma_dec)
                return ema_dec or sma_dec
                
            elif ma_type == TrailingMAType.LOWER_20:
                # Use the lower of 20 EMA and 20 SMA (conservative trailing)
                ema_val = None
                sma_val = None
                
                if self._get_ema:
                    ema_val = await self._get_ema(symbol, 20)
                if self._get_sma:
                    sma_val = await self._get_sma(symbol, 20)
                
                if ema_val is None and sma_val is None:
                    return None
                
                ema_dec = Decimal(str(ema_val)) if ema_val else None
                sma_dec = Decimal(str(sma_val)) if sma_val else None
                
                if ema_dec and sma_dec:
                    return min(ema_dec, sma_dec)
                return ema_dec or sma_dec
                
        except Exception as e:
            logger.warning(f"[MACheck] Could not get {ma_type.value} for {symbol}: {e}")
            return None
    
    def get_status(self) -> dict:
        """Get job status."""
        return {
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "total_checks": self.total_checks,
            "total_exits": self.total_exits,
            "min_days_for_trailing": self.min_days_for_trailing,
            "default_ma_type": self.default_ma_type.value,
        }


# Singleton
_ma_check_job: Optional[MACheckJob] = None


def get_ma_check_job() -> MACheckJob:
    """Get singleton MA check job."""
    global _ma_check_job
    if _ma_check_job is None:
        _ma_check_job = MACheckJob()
    return _ma_check_job
