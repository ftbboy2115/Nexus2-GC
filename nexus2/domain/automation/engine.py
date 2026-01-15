"""
Automation Engine

Core engine that orchestrates automated trading: scanning, signal generation, 
order execution, and position monitoring.
"""

import asyncio
import logging
from datetime import datetime, time as dt_time
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Callable
from dataclasses import dataclass, field

from .signals import Signal, SignalGenerator
from nexus2.utils.time_utils import now_utc, now_et


logger = logging.getLogger(__name__)


class EngineState(Enum):
    """State of the automation engine."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class EngineConfig:
    """Configuration for the automation engine."""
    # Scanner settings
    scanner_interval_minutes: int = 15
    scanner_mode: str = "gainers"
    scanner_limit: int = 20
    
    # Signal filtering
    min_quality_score: int = 7
    max_stop_percent: float = 5.0
    
    # Risk management
    risk_per_trade: Decimal = Decimal("100")
    max_positions: int = 5
    daily_loss_limit: Decimal = Decimal("1000")
    max_capital: Decimal = Decimal("10000")  # Maximum capital allocated to automation
    
    # Safety
    sim_only: bool = True  # Default to SIM mode
    
    # Market hours (US Eastern)
    market_open: dt_time = field(default_factory=lambda: dt_time(9, 30))
    market_close: dt_time = field(default_factory=lambda: dt_time(16, 0))


@dataclass
class EngineStats:
    """Runtime statistics for the engine."""
    started_at: Optional[datetime] = None
    scans_run: int = 0
    signals_generated: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    daily_pnl: Decimal = Decimal("0")
    last_scan_at: Optional[datetime] = None
    last_error: Optional[str] = None


class AutomationEngine:
    """
    Core automation engine for KK-style trading.
    
    Responsibilities:
    - Run scanner on interval
    - Generate signals from scanner results
    - Execute trades based on signals
    - Monitor positions
    - Enforce risk limits
    """
    
    def __init__(
        self,
        config: EngineConfig = None,
        scanner_func: Callable = None,
        order_func: Callable = None,
        position_func: Callable = None,
    ):
        self.config = config or EngineConfig()
        self.state = EngineState.STOPPED
        self.stats = EngineStats()
        
        # Callbacks
        self._scanner_func = scanner_func
        self._order_func = order_func
        self._position_func = position_func
        
        # Signal generator
        self._signal_gen = SignalGenerator(
            min_quality=self.config.min_quality_score,
            max_stop_percent=self.config.max_stop_percent,
        )
        
        # Background task
        self._task: Optional[asyncio.Task] = None
        self._running = False
    
    @property
    def is_running(self) -> bool:
        return self.state == EngineState.RUNNING
    
    @property
    def is_market_hours(self) -> bool:
        """
        Check if market is currently open.
        
        Uses Alpaca clock API for accurate detection of:
        - Holidays (New Year's, MLK, etc.)
        - Early closes (Black Friday, Christmas Eve)
        - Weekend
        - Regular hours
        """
        try:
            from nexus2.adapters.market_data.market_calendar import get_market_calendar
            calendar = get_market_calendar(paper=self.config.sim_only)
            return calendar.is_market_open()
        except Exception as e:
            logger.warning(f"Market calendar unavailable, using fallback: {e}")
            # Fallback to basic time check
            now = now_et()
            current_time = now.time()
            weekday = now.weekday()
            
            if weekday >= 5:
                return False
            
            return self.config.market_open <= current_time <= self.config.market_close
    
    def start(self) -> dict:
        """Start the automation engine."""
        if self.state == EngineState.RUNNING:
            return {"status": "already_running"}
        
        # Safety check
        if not self.config.sim_only:
            logger.warning("Starting automation in LIVE mode!")
        
        self.state = EngineState.RUNNING
        self.stats.started_at = now_utc()
        self._running = True
        
        logger.info(f"Automation engine started (SIM={self.config.sim_only})")
        
        return {
            "status": "started",
            "sim_only": self.config.sim_only,
            "scanner_interval": self.config.scanner_interval_minutes,
        }
    
    def stop(self) -> dict:
        """Stop the automation engine."""
        if self.state == EngineState.STOPPED:
            return {"status": "already_stopped"}
        
        self._running = False
        self.state = EngineState.STOPPED
        
        if self._task and not self._task.done():
            self._task.cancel()
        
        logger.info("Automation engine stopped")
        
        return {"status": "stopped"}
    
    def pause(self) -> dict:
        """Pause the automation engine."""
        if self.state != EngineState.RUNNING:
            return {"status": "not_running"}
        
        self.state = EngineState.PAUSED
        logger.info("Automation engine paused")
        
        return {"status": "paused"}
    
    def resume(self) -> dict:
        """Resume the automation engine."""
        if self.state != EngineState.PAUSED:
            return {"status": "not_paused"}
        
        self.state = EngineState.RUNNING
        logger.info("Automation engine resumed")
        
        return {"status": "resumed"}
    
    def get_status(self) -> dict:
        """Get current engine status."""
        return {
            "state": self.state.value,
            "sim_only": self.config.sim_only,
            "is_market_hours": self.is_market_hours,
            "config": {
                "scanner_interval": self.config.scanner_interval_minutes,
                "min_quality": self.config.min_quality_score,
                "max_positions": self.config.max_positions,
                "risk_per_trade": str(self.config.risk_per_trade),
                "daily_loss_limit": str(self.config.daily_loss_limit),
            },
            "stats": {
                "started_at": self.stats.started_at.isoformat() if self.stats.started_at else None,
                "scans_run": self.stats.scans_run,
                "signals_generated": self.stats.signals_generated,
                "orders_submitted": self.stats.orders_submitted,
                "orders_filled": self.stats.orders_filled,
                "daily_pnl": str(self.stats.daily_pnl),
                "last_scan_at": self.stats.last_scan_at.isoformat() if self.stats.last_scan_at else None,
                "last_error": self.stats.last_error,
            }
        }
    
    async def run_scan_cycle(self) -> List[Signal]:
        """
        Run one scanner cycle and generate signals.
        
        Returns list of valid signals.
        """
        if not self._scanner_func:
            logger.warning("No scanner function configured")
            return []
        
        try:
            # Run scanner
            results = await self._scanner_func(
                mode=self.config.scanner_mode,
                limit=self.config.scanner_limit,
            )
            
            self.stats.scans_run += 1
            self.stats.last_scan_at = now_utc()
            
            # Handle UnifiedScanResult object vs plain list
            # The scanner callback may return UnifiedScanResult (has .signals) or a list
            if hasattr(results, 'signals'):
                # UnifiedScanResult object - signals are already Signal objects, pre-filtered
                # DO NOT re-filter them - the unified scanner already applied min_quality/stop filters
                scanner_results = results.signals if results.signals else []
                results_count = len(scanner_results)
                
                # Signals are already valid Signal objects - pass through directly
                signals = scanner_results
                logger.info(f"Unified scan complete: {results_count} pre-filtered signals")
            else:
                # Plain list (dict results) - need to convert via SignalGenerator
                scanner_results = results if results else []
                results_count = len(scanner_results)
                
                # Generate signals from dicts
                signals = self._signal_gen.from_scanner_results(
                    scanner_results, 
                    mode=self.config.scanner_mode
                )
                logger.info(f"Scan complete: {results_count} results, {len(signals)} signals")
            
            self.stats.signals_generated += len(signals)
            
            return signals
            
        except Exception as e:
            self.stats.last_error = str(e)
            logger.error(f"Scan cycle failed: {e}")
            return []
    
    def can_open_position(self) -> bool:
        """Check if we can open a new position."""
        # Check max positions
        if self._position_func:
            current_positions = len(self._position_func())
            if current_positions >= self.config.max_positions:
                logger.info(f"At max positions ({current_positions}/{self.config.max_positions})")
                return False
        
        # Check daily loss limit
        if self.stats.daily_pnl <= -self.config.daily_loss_limit:
            logger.warning(f"Daily loss limit hit: {self.stats.daily_pnl}")
            return False
        
        return True
    
    async def process_signal(self, signal: Signal) -> Optional[dict]:
        """
        Process a signal and potentially submit an order.
        
        Returns order result if submitted, None otherwise.
        """
        if not self.can_open_position():
            return None
        
        if not self._order_func:
            logger.warning("No order function configured")
            return None
        
        # Calculate position size
        shares = signal.calculate_shares(self.config.risk_per_trade)
        if shares < 1:
            logger.info(f"Position size too small for {signal.symbol}")
            return None
        
        try:
            # Submit order
            result = await self._order_func(
                symbol=signal.symbol,
                shares=shares,
                stop_price=float(signal.tactical_stop),
                setup_type=signal.setup_type.value,
            )
            
            self.stats.orders_submitted += 1
            logger.info(f"Order submitted: {signal.symbol} x {shares}")
            
            return result
            
        except Exception as e:
            self.stats.last_error = str(e)
            logger.error(f"Order submission failed: {e}")
            return None
