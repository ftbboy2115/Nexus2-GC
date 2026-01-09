"""
Warrior Automation Engine

Orchestrates Warrior Trading automation:
- Pre-market scanning for gap candidates
- Opening Range Breakout (ORB) at 9:30 AM
- PMH (Pre-Market High) breakout monitoring
- 9:30-11:30 AM trading window focus
- Integration with WarriorScanner and WarriorMonitor

Separate from KK-style AutomationEngine - uses different entry logic.
"""

import asyncio
import logging
from datetime import datetime, time as dt_time, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Callable, Dict
from dataclasses import dataclass, field

from nexus2.domain.scanner.warrior_scanner_service import (
    WarriorScannerService,
    WarriorCandidate,
    WarriorScanSettings,
)
from nexus2.domain.automation.warrior_monitor import (
    WarriorMonitor,
    WarriorMonitorSettings,
    WarriorPosition,
)


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONFIG
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


@dataclass
class WarriorEngineConfig:
    """Configuration for Warrior automation engine."""
    # Trading Window (Ross focuses on first 2 hours)
    market_open: dt_time = field(default_factory=lambda: dt_time(9, 30))
    trading_window_end: dt_time = field(default_factory=lambda: dt_time(11, 30))
    market_close: dt_time = field(default_factory=lambda: dt_time(16, 0))
    
    # Pre-market scan
    premarket_scan_time: dt_time = field(default_factory=lambda: dt_time(9, 15))
    
    # ORB Settings
    orb_timeframe_minutes: int = 1  # 1-minute ORB
    orb_enabled: bool = True
    
    # PMH Breakout
    pmh_enabled: bool = True
    pmh_buffer_cents: Decimal = Decimal("5")  # Buy 5 cents above PMH
    
    # Scanner
    scanner_interval_minutes: int = 5
    max_candidates: int = 5
    
    # Risk
    risk_per_trade: Decimal = Decimal("100")  # $100 per trade
    max_positions: int = 10  # Higher default for testing
    max_daily_loss: Decimal = Decimal("999999")  # Disabled for testing
    max_capital: Decimal = Decimal("5000")  # Max capital per trade
    
    # Position Sizing Limits (for testing with small positions)
    max_shares_per_trade: Optional[int] = 1  # Hard cap on shares (e.g., 1 for testing)
    max_value_per_trade: Optional[Decimal] = None  # Hard cap on $ value (e.g., 100)
    
    # Blacklist - symbols to never trade
    static_blacklist: set = field(default_factory=lambda: {"PLBY"})
    
    # Execution
    sim_only: bool = True  # SAFETY: Default to paper trading


@dataclass
class WarriorEngineStats:
    """Runtime statistics for the engine."""
    started_at: Optional[datetime] = None
    scans_run: int = 0
    candidates_found: int = 0
    entries_triggered: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    daily_pnl: Decimal = Decimal("0")
    last_scan_at: Optional[datetime] = None
    last_error: Optional[str] = None


@dataclass
class WatchedCandidate:
    """A candidate being watched for entry trigger."""
    candidate: WarriorCandidate
    pmh: Decimal  # Pre-market high
    orb_high: Optional[Decimal] = None  # Opening range high
    orb_low: Optional[Decimal] = None  # Opening range low
    orb_established: bool = False
    entry_triggered: bool = False
    added_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# WARRIOR ENGINE
# =============================================================================

class WarriorEngine:
    """
    Warrior Trading automation engine.
    
    Ross Cameron entry patterns:
    1. ORB (Opening Range Breakout) - Buy break of first 1-min candle high
    2. PMH (Pre-Market High) - Buy break of pre-market high
    3. Bull Flag - Buy first green after 2-3 red candle pullback
    
    Trading window: 9:30 AM - 11:30 AM ET (first 2 hours)
    """
    
    def __init__(
        self,
        config: Optional[WarriorEngineConfig] = None,
        scanner: Optional[WarriorScannerService] = None,
        monitor: Optional[WarriorMonitor] = None,
    ):
        self.config = config or WarriorEngineConfig()
        self.scanner = scanner or WarriorScannerService()
        # Use singleton monitor so callbacks set elsewhere are shared
        if monitor:
            self.monitor = monitor
        else:
            from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
            self.monitor = get_warrior_monitor()
        
        self.state = WarriorEngineState.STOPPED
        self.stats = WarriorEngineStats()
        
        # Load saved settings if they exist
        try:
            from nexus2.db.warrior_settings import load_warrior_settings, apply_settings_to_config
            saved = load_warrior_settings()
            if saved:
                apply_settings_to_config(self.config, saved)
        except Exception as e:
            print(f"[Warrior] Failed to load saved settings: {e}")
        
        # Watched candidates
        self._watchlist: Dict[str, WatchedCandidate] = {}
        
        # Blacklist - symbols that can't be traded (Alpaca rejects)
        self._blacklist: set = set()
        
        # Tasks
        self._scan_task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        
        # Scan interrupt (for config changes)
        self._scan_interrupt: Optional[asyncio.Event] = None
        self._last_scan_started: Optional[datetime] = None
        self._last_scan_result: Optional[dict] = None  # Store last scan results for UI
        
        # Callbacks (to be wired up)
        self._submit_order: Optional[Callable] = None
        self._get_quote: Optional[Callable] = None
        self._get_positions: Optional[Callable] = None
        self._get_intraday_bars: Optional[Callable] = None
    
    def set_callbacks(
        self,
        submit_order: Callable = None,
        get_quote: Callable = None,
        get_positions: Callable = None,
        get_intraday_bars: Callable = None,
    ):
        """Set callbacks for order execution and data."""
        self._submit_order = submit_order
        self._get_quote = get_quote
        self._get_positions = get_positions
        self._get_intraday_bars = get_intraday_bars
        
        # Also wire up monitor callbacks
        self.monitor.set_callbacks(
            get_price=get_quote,
            get_intraday_candles=get_intraday_bars,
        )
    
    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================
    
    @property
    def is_running(self) -> bool:
        return self.state in (WarriorEngineState.RUNNING, WarriorEngineState.PREMARKET)
    
    def _get_eastern_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    
    def is_trading_window(self) -> bool:
        """Check if within 9:30 AM - 11:30 AM trading window."""
        now = self._get_eastern_time().time()
        return self.config.market_open <= now <= self.config.trading_window_end
    
    def is_market_hours(self) -> bool:
        """Check if market is open."""
        now = self._get_eastern_time().time()
        return self.config.market_open <= now <= self.config.market_close
    
    def is_premarket(self) -> bool:
        """Check if in pre-market scan window."""
        now = self._get_eastern_time().time()
        return self.config.premarket_scan_time <= now < self.config.market_open
    
    # =========================================================================
    # ENGINE CONTROL
    # =========================================================================
    
    async def start(self) -> dict:
        """Start the Warrior engine."""
        if self.state != WarriorEngineState.STOPPED:
            return {"status": "already_running"}
        
        self.stats.started_at = datetime.utcnow()
        
        # Determine initial state
        if self.is_premarket():
            self.state = WarriorEngineState.PREMARKET
        else:
            self.state = WarriorEngineState.RUNNING
        
        # Start background tasks
        self._scan_task = asyncio.create_task(self._scan_loop())
        self._watch_task = asyncio.create_task(self._watch_loop())
        
        # Start monitor
        await self.monitor.start()
        
        logger.info(f"[Warrior Engine] Started in {self.state.value} mode")
        return {
            "status": "started",
            "state": self.state.value,
            "sim_only": self.config.sim_only,
        }
    
    async def stop(self) -> dict:
        """Stop the Warrior engine."""
        if self.state == WarriorEngineState.STOPPED:
            return {"status": "already_stopped"}
        
        self.state = WarriorEngineState.STOPPED
        
        # Cancel tasks
        for task in [self._scan_task, self._watch_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop monitor
        await self.monitor.stop()
        
        # Clear watchlist
        self._watchlist.clear()
        
        logger.info("[Warrior Engine] Stopped")
        return {"status": "stopped"}
    
    async def pause(self) -> dict:
        """Pause the engine (keep state, stop new entries)."""
        if self.state in (WarriorEngineState.STOPPED, WarriorEngineState.PAUSED):
            return {"status": "already_paused"}
        
        self.state = WarriorEngineState.PAUSED
        logger.info("[Warrior Engine] Paused")
        return {"status": "paused"}
    
    async def resume(self) -> dict:
        """Resume the engine."""
        if self.state != WarriorEngineState.PAUSED:
            return {"status": "not_paused"}
        
        self.state = WarriorEngineState.RUNNING
        logger.info("[Warrior Engine] Resumed")
        return {"status": "resumed"}
    
    # =========================================================================
    # SCANNING
    # =========================================================================
    
    async def _scan_loop(self):
        """Background loop for scanning candidates."""
        # Create interrupt event for this loop
        self._scan_interrupt = asyncio.Event()
        
        while self.state != WarriorEngineState.STOPPED:
            try:
                if self.state == WarriorEngineState.PAUSED:
                    await asyncio.sleep(10)
                    continue
                
                # Record when this scan started
                self._last_scan_started = datetime.utcnow()
                
                # Run scan
                await self._run_scan()
                
                # Wait for next interval (interruptible)
                wait_seconds = self.config.scanner_interval_minutes * 60
                try:
                    # Wait until either: (1) timeout expires, or (2) interrupt event is set
                    await asyncio.wait_for(
                        self._scan_interrupt.wait(),
                        timeout=wait_seconds
                    )
                    # If we get here, event was set (interrupted)
                    self._scan_interrupt.clear()
                    logger.info("[Warrior Scan] Sleep interrupted by config change")
                except asyncio.TimeoutError:
                    # Normal timeout - continue to next scan
                    pass
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats.last_error = str(e)
                logger.error(f"[Warrior Scan] Error: {e}")
                await asyncio.sleep(30)
    
    def interrupt_scan_sleep(self):
        """Interrupt current scan sleep (called when interval is reduced)."""
        if self._scan_interrupt and not self._scan_interrupt.is_set():
            self._scan_interrupt.set()
            logger.info("[Warrior Scan] Interrupt signal sent")
    
    async def _run_scan(self):
        """Run one scan cycle."""
        self.stats.scans_run += 1
        self.stats.last_scan_at = datetime.utcnow()
        
        logger.info("[Warrior Scan] Running scan...")
        
        result = self.scanner.scan(verbose=False)
        
        self.stats.candidates_found += len(result.candidates)
        
        # Add top candidates to watchlist
        for candidate in result.candidates[:self.config.max_candidates]:
            if candidate.symbol not in self._watchlist:
                # Get pre-market high
                pmh = await self._get_premarket_high(candidate.symbol)
                
                self._watchlist[candidate.symbol] = WatchedCandidate(
                    candidate=candidate,
                    pmh=pmh or candidate.session_high,
                )
                logger.info(
                    f"[Warrior Watch] Added {candidate.symbol}: "
                    f"gap={candidate.gap_percent:.1f}%, PMH=${pmh or candidate.session_high}"
                )
        
        # Store scan result for UI visibility
        self._last_scan_result = {
            "scan_time": datetime.utcnow().isoformat(),
            "processed_count": result.processed_count,
            "candidates": [
                {
                    "symbol": c.symbol,
                    "gap_percent": float(c.gap_percent),
                    "rvol": float(c.relative_volume),
                    "float_shares": c.float_shares,
                    "price": float(c.price),
                    "in_watchlist": c.symbol in self._watchlist,
                }
                for c in result.candidates
            ],
        }
        
        logger.info(f"[Warrior Scan] Found {len(result.candidates)} candidates, watching {len(self._watchlist)}")
    
    async def _get_premarket_high(self, symbol: str) -> Optional[Decimal]:
        """Get pre-market high for a symbol.
        
        Uses FMP intraday bars to calculate max(high) from pre-market (4AM-9:29AM).
        This is the TRUE PMH - doesn't update during regular session.
        """
        try:
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            
            fmp = get_fmp_adapter()
            if fmp:
                pmh = fmp.get_premarket_high(symbol)
                if pmh:
                    return pmh
        except Exception as e:
            logger.warning(f"[Warrior PMH] FMP lookup failed for {symbol}: {e}")
        
        # Fallback to quote day_high if FMP fails (less accurate)
        if self._get_quote:
            quote = await self._get_quote(symbol)
            if quote:
                return Decimal(str(getattr(quote, 'day_high', 0) or 0))
        return None
    
    # =========================================================================
    # ENTRY WATCHING
    # =========================================================================
    
    async def _watch_loop(self):
        """Background loop for watching entry triggers."""
        while self.state != WarriorEngineState.STOPPED:
            try:
                if self.state == WarriorEngineState.PAUSED:
                    await asyncio.sleep(5)
                    continue
                
                # NOTE: No time restriction - trades qualified setups ANY time
                # Pre-market and after-hours moves can be explosive on small-caps
                # (no halts outside regular hours)
                
                # Check each watched candidate
                await self._check_entry_triggers()
                
                # Fast polling 
                await asyncio.sleep(5)  # 5 second checks
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats.last_error = str(e)
                logger.error(f"[Warrior Watch] Error: {e}")
                await asyncio.sleep(10)
    
    async def _check_entry_triggers(self):
        """Check all watched candidates for entry triggers."""
        if not self._get_quote:
            return
        
        for symbol, watched in list(self._watchlist.items()):
            if watched.entry_triggered:
                continue  # Already entered
            
            try:
                current_price = await self._get_quote(symbol)
                if not current_price:
                    continue
                
                current_price = Decimal(str(current_price))
                
                # ORB trigger at 9:30
                if self.config.orb_enabled and not watched.orb_established:
                    await self._check_orb_setup(watched, current_price)
                
                # PMH breakout
                if self.config.pmh_enabled:
                    trigger_price = watched.pmh + self.config.pmh_buffer_cents / 100
                    if current_price >= trigger_price:
                        logger.info(f"[Warrior Entry] {symbol}: PMH BREAKOUT at ${current_price}")
                        await self._enter_position(
                            watched, 
                            current_price, 
                            EntryTriggerType.PMH_BREAK
                        )
                
                # ORB breakout (after ORB established)
                if watched.orb_established and watched.orb_high:
                    if current_price > watched.orb_high:
                        logger.info(f"[Warrior Entry] {symbol}: ORB BREAKOUT at ${current_price}")
                        await self._enter_position(
                            watched,
                            current_price,
                            EntryTriggerType.ORB
                        )
                        
            except Exception as e:
                logger.error(f"[Warrior Watch] Error checking {symbol}: {e}")
    
    async def _check_orb_setup(self, watched: WatchedCandidate, current_price: Decimal):
        """Check for Opening Range Breakout setup."""
        # Get first 1-minute candle
        et_now = self._get_eastern_time()
        
        # Only establish ORB in first minute after open
        if et_now.time() > dt_time(9, 31):
            if self._get_intraday_bars:
                bars = await self._get_intraday_bars(
                    watched.candidate.symbol, 
                    timeframe="1min",
                    limit=1
                )
                if bars and len(bars) > 0:
                    first_bar = bars[0]
                    watched.orb_high = first_bar.high
                    watched.orb_low = first_bar.low
                    watched.orb_established = True
                    logger.info(
                        f"[Warrior ORB] {watched.candidate.symbol}: "
                        f"High=${watched.orb_high}, Low=${watched.orb_low}"
                    )
    
    async def _enter_position(
        self,
        watched: WatchedCandidate,
        entry_price: Decimal,
        trigger_type: EntryTriggerType,
    ):
        """Execute entry for a candidate."""
        symbol = watched.candidate.symbol
        
        # Check blacklist (static config + dynamic from broker rejections)
        if symbol in self.config.static_blacklist or symbol in self._blacklist:
            logger.info(f"[Warrior Entry] {symbol}: Blacklisted, skipping")
            watched.entry_triggered = True  # Mark to prevent retries
            return
        
        # Check if we already hold this symbol (prevents double-buying after restart)
        if self._get_positions:
            try:
                positions = await self._get_positions()
                held_symbols = {p.get("symbol") or p.symbol for p in positions if p}
                if symbol in held_symbols:
                    logger.info(f"[Warrior Entry] {symbol}: Already holding position, skipping")
                    watched.entry_triggered = True  # Mark as triggered to prevent retries
                    return
            except Exception as e:
                logger.warning(f"[Warrior Entry] {symbol}: Position check failed: {e}")
        
        # Check if we can open new position (max positions, daily loss)
        if not await self._can_open_position():
            logger.info(f"[Warrior Entry] {symbol}: Cannot open (max positions or daily loss)")
            return
        
        # Mark as triggered
        watched.entry_triggered = True
        self.stats.entries_triggered += 1
        
        # Calculate position size
        # Mental stop = entry - 15 cents (default)
        mental_stop = entry_price - self.monitor.settings.mental_stop_cents / 100
        risk_per_share = entry_price - mental_stop
        
        if risk_per_share <= 0:
            logger.warning(f"[Warrior Entry] {symbol}: Invalid risk calculation")
            return
        
        shares = int(self.config.risk_per_trade / risk_per_share)
        
        # Cap by max capital
        max_shares = int(self.config.max_capital / entry_price)
        shares = min(shares, max_shares)
        
        # Apply testing limits
        if self.config.max_shares_per_trade is not None:
            shares = min(shares, self.config.max_shares_per_trade)
        if self.config.max_value_per_trade is not None:
            max_by_value = int(self.config.max_value_per_trade / entry_price)
            shares = min(shares, max_by_value)
        
        if shares < 1:
            logger.info(f"[Warrior Entry] {symbol}: Position too small")
            return
        
        # Submit order - Ross uses limit order with 5¢ offset above ask
        # This prevents slippage on fast stocks while ensuring quick fills
        limit_offset = Decimal("0.05")  # 5 cents above entry price
        limit_price = (entry_price + limit_offset).quantize(Decimal("0.01"))  # Round to 2 decimals for Alpaca
        
        if self._submit_order:
            try:
                order_result = await self._submit_order(
                    symbol=symbol,
                    shares=shares,
                    side="buy",
                    order_type="limit",  # Limit order, not market
                    limit_price=float(limit_price),  # 5¢ above current price
                    stop_loss=None,  # Mental stop, not broker stop
                )
                
                # Check for blacklist response from broker
                if isinstance(order_result, dict) and order_result.get("blacklist"):
                    self._blacklist.add(symbol)
                    logger.warning(f"[Warrior Entry] {symbol}: Added to blacklist - {order_result.get('error')}")
                    watched.entry_triggered = True
                    return
                
                if order_result is None:
                    logger.warning(f"[Warrior Entry] {symbol}: Order returned None")
                    return
                
                self.stats.orders_submitted += 1
                
                # Add to monitor
                support_level = watched.orb_low or watched.candidate.session_low or entry_price * Decimal("0.95")
                
                # Handle both dict and object return types
                if hasattr(order_result, 'client_order_id'):
                    order_id = str(order_result.client_order_id)
                elif isinstance(order_result, dict):
                    order_id = order_result.get("order_id", symbol)
                else:
                    order_id = symbol
                
                self.monitor.add_position(
                    position_id=order_id,
                    symbol=symbol,
                    entry_price=entry_price,
                    shares=shares,
                    support_level=support_level,
                )
                
                # Log to Warrior DB for restart recovery
                try:
                    from nexus2.db.warrior_db import log_warrior_entry
                    mental_stop_cents = Decimal(str(self.monitor.settings.mental_stop_cents))
                    profit_target_r = Decimal(str(self.monitor.settings.profit_target_r))
                    target = entry_price + (mental_stop_cents / 100 * profit_target_r)
                    log_warrior_entry(
                        trade_id=order_id,
                        symbol=symbol,
                        entry_price=float(entry_price),
                        quantity=shares,
                        stop_price=float(mental_stop),
                        target_price=float(target),
                        trigger_type=trigger_type.value,
                        support_level=float(support_level),
                    )
                except Exception as e:
                    logger.warning(f"[Warrior Entry] DB log failed: {e}")
                
                logger.info(
                    f"[Warrior Entry] {symbol}: Bought {shares} shares @ ${entry_price} "
                    f"({trigger_type.value})"
                )
                
            except Exception as e:
                logger.error(f"[Warrior Entry] {symbol}: Order failed: {e}")
                self.stats.last_error = str(e)
        else:
            logger.warning(f"[Warrior Entry] {symbol}: No submit_order callback")
    
    async def _can_open_position(self) -> bool:
        """Check if we can open a new position."""
        # Check position count
        if self._get_positions:
            positions = await self._get_positions()
            print(f"[Debug] Positions count: {len(positions)}, max: {self.config.max_positions}")
            if len(positions) >= self.config.max_positions:
                print(f"[Debug] Blocked by position count")
                return False
        
        # Check daily loss
        print(f"[Debug] Daily P&L: {self.stats.daily_pnl}, max_loss: {self.config.max_daily_loss}")
        if self.stats.daily_pnl <= -self.config.max_daily_loss:
            logger.warning("[Warrior] Daily loss limit reached")
            return False
        
        return True
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_status(self) -> dict:
        """Get engine status."""
        return {
            "state": self.state.value,
            "trading_window": self.is_trading_window(),
            "market_hours": self.is_market_hours(),
            "watchlist_count": len(self._watchlist),
            "watchlist": [
                {
                    "symbol": w.candidate.symbol,
                    "gap_percent": float(w.candidate.gap_percent),
                    "rvol": float(w.candidate.relative_volume),
                    "pmh": float(w.pmh),
                    "orb_high": float(w.orb_high) if w.orb_high else None,
                    "orb_established": w.orb_established,
                    "entry_triggered": w.entry_triggered,
                }
                for w in self._watchlist.values()
            ],
            "stats": {
                "started_at": self.stats.started_at.isoformat() if self.stats.started_at else None,
                "scans_run": self.stats.scans_run,
                "candidates_found": self.stats.candidates_found,
                "entries_triggered": self.stats.entries_triggered,
                "orders_submitted": self.stats.orders_submitted,
                "daily_pnl": float(self.stats.daily_pnl),
                "last_scan_at": self.stats.last_scan_at.isoformat() if self.stats.last_scan_at else None,
                "last_error": self.stats.last_error,
            },
            "monitor": self.monitor.get_status(),
            "config": {
                "sim_only": self.config.sim_only,
                "risk_per_trade": float(self.config.risk_per_trade),
                "max_positions": self.config.max_positions,
                "max_candidates": self.config.max_candidates,
                "scanner_interval_minutes": self.config.scanner_interval_minutes,
                "max_daily_loss": float(self.config.max_daily_loss),
                "orb_enabled": self.config.orb_enabled,
                "pmh_enabled": self.config.pmh_enabled,
            },
            "last_scan_result": self._last_scan_result,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_warrior_engine: Optional[WarriorEngine] = None


def get_warrior_engine() -> WarriorEngine:
    """Get singleton Warrior engine."""
    global _warrior_engine
    if _warrior_engine is None:
        _warrior_engine = WarriorEngine()
    return _warrior_engine
