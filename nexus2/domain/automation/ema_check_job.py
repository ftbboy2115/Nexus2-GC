"""
End-of-Day MA Check Job

KK-style trailing stop: Exit on daily close below 10/20 MA.

This job should run during the LAST 15 MINUTES of market day (3:45-4:00 PM ET)
so that exits can be submitted as market orders before close.

Supports:
- EMA (exponential moving average)
- SMA (simple moving average)
- Lower of EMA/SMA (whichever is lower acts as tighter stop)
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
    AUTO = "auto"        # Auto-select based on ADR% (KK-style)
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
        self._execute_exit: Optional[Callable] = None  # (position_id, shares, reason) -> None
        
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
        if execute_exit:
            self._execute_exit = execute_exit
    
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
            opened_at = datetime.utcnow()  # Fallback
        
        days_held = (date.today() - opened_at.date()).days
        
        # Only apply MA trailing after min_days
        if days_held < self.min_days_for_trailing:
            logger.debug(f"[MACheck] {symbol}: Day {days_held} - too early for MA trailing")
            return None
        
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
        
        # Determine MA type (auto-select or use default)
        ma_type = self.default_ma_type
        adr_percent = None
        
        if ma_type == TrailingMAType.AUTO:
            ma_type, adr_percent = await self._auto_select_ma(symbol)
            logger.info(f"[MACheck] {symbol}: ADR={adr_percent:.1f}% -> Auto-selected {ma_type.value}")
        
        # Get MA value
        ma_value = await self._get_ma_value(symbol, ma_type)
        
        if ma_value is None:
            return None
        
        # Check if close is below MA
        if daily_close < ma_value:
            logger.info(
                f"[MACheck] {symbol}: Close ${daily_close} < {ma_type.value} ${ma_value} - EXIT SIGNAL"
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
            f"[MACheck] {symbol}: Close ${daily_close} >= {ma_type.value} ${ma_value} - HOLD"
        )
        return None
    
    async def _auto_select_ma(self, symbol: str) -> tuple[TrailingMAType, float]:
        """
        Auto-select MA type based on ADR% (KK-style).
        
        KK uses:
        - ADR% >= 5% -> Fast mover -> 10 MA (LOWER_10)
        - ADR% < 5% -> Slower stock -> 20 MA (LOWER_20)
        
        Returns (selected_ma_type, adr_percent)
        """
        adr_percent = 0.0
        
        if self._get_adr_percent:
            try:
                adr = await self._get_adr_percent(symbol, 20)  # 20-day ADR
                if adr:
                    adr_percent = float(adr)
            except Exception as e:
                logger.warning(f"[MACheck] Could not get ADR% for {symbol}: {e}")
        
        # KK's threshold: 5% ADR = fast mover
        if adr_percent >= self.adr_threshold:
            return TrailingMAType.LOWER_10, adr_percent  # Fast mover - tight trailing
        else:
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
