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
import json
import logging
from datetime import datetime, time as dt_time, timezone, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
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
from nexus2.utils.time_utils import now_utc


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
        
        # Pending entries - track symbols with pending buy orders (prevents duplicates)
        self._pending_entries: Dict[str, datetime] = {}  # symbol -> order_submitted_at
        self._pending_entries_file = Path(__file__).parent.parent.parent.parent / "data" / "pending_entries.json"
        self._load_pending_entries()
        
        # 2-Strike Rule: track daily stop-out failures per symbol
        # After max_fails stops, block further entries for the day
        self._symbol_fails: Dict[str, int] = {}  # symbol -> stop count
        self._max_fails_per_symbol: int = 2  # Ross methodology: 2 fails = done
        
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
        self._get_quote_with_spread: Optional[Callable] = None  # For entry spread filter
        self._get_positions: Optional[Callable] = None
        self._get_intraday_bars: Optional[Callable] = None
        self._check_pending_fill: Optional[Callable] = None  # Check for pending buy orders
        self._create_pending_position: Optional[Callable] = None  # Create PENDING_FILL position
    
    def set_callbacks(
        self,
        submit_order: Callable = None,
        get_quote: Callable = None,
        get_quote_with_spread: Callable = None,
        get_positions: Callable = None,
        get_intraday_bars: Callable = None,
        check_pending_fill: Callable = None,
        create_pending_position: Callable = None,
    ):
        """Set callbacks for order execution and data."""
        self._submit_order = submit_order
        self._get_quote = get_quote
        self._get_quote_with_spread = get_quote_with_spread
        self._get_positions = get_positions
        self._get_intraday_bars = get_intraday_bars
        self._check_pending_fill = check_pending_fill
        self._create_pending_position = create_pending_position
        
        # Also wire up monitor callbacks
        self.monitor.set_callbacks(
            get_price=get_quote,
            get_intraday_candles=get_intraday_bars,
            record_symbol_fail=self.record_symbol_fail,
        )
    
    def _load_pending_entries(self):
        """Load pending entries from disk (survives restarts)."""
        try:
            if self._pending_entries_file.exists():
                import json
                with open(self._pending_entries_file, "r") as f:
                    data = json.load(f)
                loaded_count = 0
                expired_count = 0
                for symbol, ts in data.items():
                    entry_time = datetime.fromisoformat(ts)
                    # Handle timezone-naive timestamps from old files
                    if entry_time.tzinfo is None:
                        from datetime import timezone
                        entry_time = entry_time.replace(tzinfo=timezone.utc)
                    # Expire pending entries older than 10 minutes (order likely filled or cancelled)
                    if (now_utc() - entry_time).total_seconds() < 600:
                        self._pending_entries[symbol] = entry_time
                        loaded_count += 1
                    else:
                        expired_count += 1
                if loaded_count > 0:
                    logger.info(f"[Warrior Engine] Loaded {loaded_count} pending entries from disk")
                if expired_count > 0:
                    logger.info(f"[Warrior Engine] Expired {expired_count} stale pending entries")
        except json.JSONDecodeError as e:
            logger.error(f"[Warrior Engine] Corrupt pending entries file - deleting: {e}")
            print(f"⚠️ [Warrior Engine] Corrupt pending_entries.json - deleting and starting fresh")
            self._pending_entries_file.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"[Warrior Engine] Failed to load pending entries: {type(e).__name__}: {e}")
            print(f"⚠️ [Warrior Engine] Error loading pending entries: {e}")
    
    def _save_pending_entries(self):
        """Save pending entries to disk."""
        try:
            import json
            data = {symbol: dt.isoformat() for symbol, dt in self._pending_entries.items()}
            self._pending_entries_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._pending_entries_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[Warrior Engine] Failed to save pending entries: {e}")
    
    def clear_pending_entry(self, symbol: str):
        """Clear a pending entry (called when order fills or is cancelled)."""
        if symbol in self._pending_entries:
            del self._pending_entries[symbol]
            self._save_pending_entries()
            logger.info(f"[Warrior Engine] Cleared pending entry for {symbol}")
    
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
        """Check if market is open (regular hours 9:30 AM - 4 PM)."""
        now = self._get_eastern_time().time()
        return self.config.market_open <= now <= self.config.market_close
    
    def is_extended_hours(self) -> bool:
        """Check if within extended trading hours (4 AM - 8 PM on market days)."""
        from nexus2.adapters.market_data.market_calendar import get_market_calendar
        calendar = get_market_calendar(paper=True)
        return calendar.is_extended_hours_active()
    
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
        
        self.stats.started_at = now_utc()
        
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
                
                # Skip on non-market days (weekends, holidays) and outside extended hours
                # BUT: bypass in sim_only mode for Mock Market testing anytime
                if not self.config.sim_only:
                    from nexus2.adapters.market_data.market_calendar import get_market_calendar
                    calendar = get_market_calendar(paper=True)
                    if not calendar.is_extended_hours_active():
                        logger.debug("[Warrior Scan] Outside extended hours (4 AM - 8 PM) - skipping scan")
                        await asyncio.sleep(60)  # Check again in 1 minute
                        continue
                
                # Record when this scan started
                self._last_scan_started = now_utc()
                
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
        self.stats.last_scan_at = datetime.now(timezone.utc)
        
        logger.info("[Warrior Scan] Running scan...")
        
        result = self.scanner.scan(verbose=self.config.debug_catalyst)
        
        # Count only NEW candidates (not seen before this session)
        for candidate in result.candidates:
            if candidate.symbol not in self.stats._seen_candidates:
                self.stats._seen_candidates.add(candidate.symbol)
                self.stats.candidates_found += 1
        
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
            "scan_time": now_utc().isoformat(),
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
        
        # Process queued multi-model comparisons (non-blocking, respects rate limits)
        try:
            from nexus2.domain.automation.ai_catalyst_validator import get_multi_validator
            multi_validator = get_multi_validator()
            comparisons = multi_validator.process_queue(max_items=5)
            if comparisons:
                stats = multi_validator.get_stats()
                logger.info(f"[MultiModel] Processed {len(comparisons)} comparisons, queue: {stats['queue_size']} remaining")
        except Exception as e:
            logger.debug(f"[MultiModel] Queue processing error: {e}")
    
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
        last_date = None  # Track current trading day for midnight reset
        
        while self.state != WarriorEngineState.STOPPED:
            try:
                if self.state == WarriorEngineState.PAUSED:
                    await asyncio.sleep(5)
                    continue
                
                # Day boundary check: clear stale watchlist entries at midnight ET
                # Prevents Friday's watchlist from triggering orders on Monday
                et_now = self._get_eastern_time()
                current_date = et_now.date()
                if last_date is not None and current_date != last_date:
                    if self._watchlist:
                        stale_symbols = list(self._watchlist.keys())
                        self._watchlist.clear()
                        logger.info(f"[Warrior Watch] New day - cleared stale watchlist: {stale_symbols}")
                last_date = current_date
                
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
        
        # 2-Strike Rule: block entry if symbol has hit max failures today
        symbol_fails = self._symbol_fails.get(symbol, 0)
        if symbol_fails >= self._max_fails_per_symbol:
            logger.info(
                f"[Warrior Entry] {symbol}: 2-strike rule - {symbol_fails} stops today, "
                f"skipping (max={self._max_fails_per_symbol})"
            )
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
        
        # Check for pending entry orders (unfilled buy orders) - prevents duplicates
        if symbol in self._pending_entries:
            logger.info(f"[Warrior Entry] {symbol}: Pending buy order exists, skipping")
            watched.entry_triggered = True  # Mark as triggered to prevent retries
            return
        
        # Check re-entry cooldown: block entry if symbol was recently exited
        # This prevents immediately buying back after exit (e.g., after spread exit or stop)
        if symbol in self.monitor._recently_exited:
            exit_time = self.monitor._recently_exited[symbol]
            seconds_ago = (now_utc() - exit_time).total_seconds()
            cooldown = self.monitor._recovery_cooldown_seconds
            if seconds_ago < cooldown:
                logger.info(
                    f"[Warrior Entry] {symbol}: Re-entry cooldown - exited {seconds_ago:.0f}s ago "
                    f"(waiting {cooldown}s), skipping"
                )
                watched.entry_triggered = True  # Mark as triggered to prevent retries
                return
        
        # Entry Spread Filter: reject stocks with wide bid-ask spreads
        # Wide spreads cause unpredictable fills and difficult exits (e.g., SOGP 46% spread)
        # Also capture current ask for limit price calculation
        current_ask = None  # Will be set if we get valid quote data
        if self._get_quote_with_spread and self.config.max_entry_spread_percent > 0:
            try:
                spread_data = await self._get_quote_with_spread(symbol)
                if spread_data:
                    bid = spread_data.get("bid", 0)
                    ask = spread_data.get("ask", 0)
                    
                    if bid > 0 and ask > 0:
                        current_ask = Decimal(str(ask))  # Store for limit price
                        spread_percent = ((ask - bid) / bid) * 100
                        
                        if spread_percent > self.config.max_entry_spread_percent:
                            logger.warning(
                                f"[Warrior Entry] {symbol}: REJECTED - spread {spread_percent:.1f}% > "
                                f"{self.config.max_entry_spread_percent}% threshold "
                                f"(bid=${bid:.2f}, ask=${ask:.2f})"
                            )
                            watched.entry_triggered = True  # Mark to prevent retries
                            return
                        else:
                            logger.debug(
                                f"[Warrior Entry] {symbol}: Spread OK {spread_percent:.1f}% "
                                f"(max={self.config.max_entry_spread_percent}%)"
                            )
                    elif bid <= 0 or ask <= 0:
                        logger.warning(
                            f"[Warrior Entry] {symbol}: No valid bid/ask data "
                            f"(bid=${bid}, ask=${ask}) - proceeding with caution"
                        )
            except Exception as e:
                logger.warning(f"[Warrior Entry] {symbol}: Spread check failed: {e} - proceeding")
        
        # Technical Validation: Check VWAP/EMA alignment per Ross Cameron
        # Entry should be above VWAP and near 9 EMA support
        if self._get_intraday_bars:
            try:
                candles = await self._get_intraday_bars(symbol, "5min", limit=50)
                if candles and len(candles) >= 10:
                    from nexus2.domain.indicators import get_technical_service
                    tech = get_technical_service()
                    
                    # Convert candles to dict format for pandas-ta
                    candle_dicts = [
                        {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                        for c in candles
                    ]
                    snapshot = tech.get_snapshot(symbol, candle_dicts, entry_price)
                    
                    # Check: price should be above VWAP (Ross Cameron rule)
                    if snapshot.vwap and entry_price < snapshot.vwap:
                        logger.warning(
                            f"[Warrior Entry] {symbol}: REJECTED - below VWAP "
                            f"(${entry_price:.2f} < VWAP ${snapshot.vwap:.2f})"
                        )
                        watched.entry_triggered = True
                        return
                    
                    # Check: price should be above 9 EMA (within 1% tolerance)
                    if snapshot.ema_9 and entry_price < snapshot.ema_9 * Decimal("0.99"):
                        logger.warning(
                            f"[Warrior Entry] {symbol}: REJECTED - below 9 EMA "
                            f"(${entry_price:.2f} < 9EMA ${snapshot.ema_9:.2f})"
                        )
                        watched.entry_triggered = True
                        return
                    
                    # Log technical confirmation
                    logger.info(
                        f"[Warrior Entry] {symbol}: Technical OK - "
                        f"VWAP=${snapshot.vwap:.2f if snapshot.vwap else 'N/A'}, "
                        f"9EMA=${snapshot.ema_9:.2f if snapshot.ema_9 else 'N/A'}, "
                        f"MACD={snapshot.macd_crossover}"
                    )
            except Exception as e:
                logger.debug(f"[Warrior Entry] {symbol}: Technical check failed: {e} - proceeding")
        
        # Check if we can open new position (max positions, daily loss)
        if not await self._can_open_position():
            logger.info(f"[Warrior Entry] {symbol}: Cannot open (max positions or daily loss)")
            return
        
        # Mark as triggered
        watched.entry_triggered = True
        self.stats.entries_triggered += 1
        
        # Calculate position size
        # Use technical stop (swing low, VWAP, or EMA) per Ross Cameron methodology
        # Falls back to 15 cents if technical data unavailable
        mental_stop = None
        stop_method = "fallback_15c"
        
        if self._get_intraday_bars:
            try:
                candles = await self._get_intraday_bars(symbol, "5min", limit=50)
                if candles and len(candles) >= 5:
                    from nexus2.domain.indicators import get_stop_calculator
                    stop_calc = get_stop_calculator()
                    candle_dicts = [
                        {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                        for c in candles
                    ]
                    mental_stop, stop_method = stop_calc.get_best_stop(
                        candle_dicts, entry_price, symbol
                    )
                    logger.info(
                        f"[Warrior Entry] {symbol}: Stop ${mental_stop:.2f} via {stop_method}"
                    )
            except Exception as e:
                logger.debug(f"[Warrior Entry] {symbol}: Technical stop calc failed: {e}")
        
        if mental_stop is None:
            mental_stop = entry_price - self.monitor.settings.mental_stop_cents / 100
            stop_method = "fallback_15c"
        
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
        
        # Submit order - Ross uses limit order with offset above ask
        # Use current ask if available, otherwise fall back to percentage offset
        limit_offset = Decimal("0.05")  # 5 cents offset when ask is available
        if current_ask and current_ask > 0:
            # Use current ask price (more accurate for fast movers)
            limit_price = (current_ask + limit_offset).quantize(Decimal("0.01"))
            logger.info(f"[Warrior Entry] {symbol}: Limit based on ask ${current_ask:.2f} + ${limit_offset} = ${limit_price:.2f}")
        else:
            # Fallback: 1.5% above entry price (scales better for runners)
            # This handles pre-market when Alpaca doesn't provide bid/ask
            fallback_multiplier = Decimal("1.015")  # 1.5% above entry
            limit_price = (entry_price * fallback_multiplier).quantize(Decimal("0.01"))
            logger.info(f"[Warrior Entry] {symbol}: Limit based on entry ${entry_price:.2f} x 1.015 = ${limit_price:.2f} (no bid/ask)")
        
        # Mark pending entry BEFORE submitting order (prevents duplicate entries on restart)
        self._pending_entries[symbol] = now_utc()
        self._save_pending_entries()
        logger.info(f"[Warrior Entry] {symbol}: Marked pending entry")
        
        if self._submit_order:
            try:
                order_result = await self._submit_order(
                    symbol=symbol,
                    shares=shares,
                    side="buy",
                    order_type="limit",  # Limit order, not market
                    limit_price=float(limit_price),  # offset above ask
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
                
                # Check if order is filled (not just submitted)
                order_status = None
                filled_qty = 0
                if hasattr(order_result, 'status'):
                    order_status = str(order_result.status)
                    filled_qty = getattr(order_result, 'filled_qty', 0) or 0
                elif isinstance(order_result, dict):
                    order_status = order_result.get("status")
                    filled_qty = order_result.get("filled_qty", 0) or 0
                
                # If order is not filled yet, skip monitor add - auto-recovery will handle it
                if order_status and order_status.lower() not in ("filled", "partially_filled"):
                    logger.info(
                        f"[Warrior Entry] {symbol}: Order pending (status={order_status}) - "
                        f"auto-recovery will sync when filled"
                    )
                    return
                
                # CRITICAL: Use ACTUAL fill price from Alpaca, not intended entry
                # This prevents immediate stop-outs when market price differs from quote
                actual_fill_price = entry_price  # Default to intended price
                slippage_cents = Decimal("0")  # Track slippage
                
                if hasattr(order_result, 'filled_avg_price') and order_result.filled_avg_price:
                    actual_fill_price = Decimal(str(order_result.filled_avg_price))
                    slippage_cents = (actual_fill_price - entry_price) * 100  # In cents
                    if slippage_cents != 0:
                        slippage_bps = (actual_fill_price / entry_price - 1) * 10000  # Basis points
                        logger.info(
                            f"[Warrior Slippage] {symbol}: Fill ${actual_fill_price:.2f} vs "
                            f"intended ${entry_price:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
                        )
                elif isinstance(order_result, dict) and order_result.get("filled_avg_price"):
                    actual_fill_price = Decimal(str(order_result["filled_avg_price"]))
                    slippage_cents = (actual_fill_price - entry_price) * 100
                    if slippage_cents != 0:
                        slippage_bps = (actual_fill_price / entry_price - 1) * 10000
                        logger.info(
                            f"[Warrior Slippage] {symbol}: Fill ${actual_fill_price:.2f} vs "
                            f"intended ${entry_price:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
                        )
                
                # Recalculate stop based on actual fill price
                actual_stop = actual_fill_price - self.monitor.settings.mental_stop_cents / 100
                
                self.monitor.add_position(
                    position_id=order_id,
                    symbol=symbol,
                    entry_price=actual_fill_price,  # Use ACTUAL fill price
                    shares=int(filled_qty) if filled_qty else shares,  # Use actual filled qty
                    support_level=support_level,
                    trigger_type=trigger_type.value,  # PMH_BREAK, ORB
                )
                
                # Log to Warrior DB for restart recovery
                try:
                    from nexus2.db.warrior_db import log_warrior_entry
                    mental_stop_cents = Decimal(str(self.monitor.settings.mental_stop_cents))
                    profit_target_r = Decimal(str(self.monitor.settings.profit_target_r))
                    target = actual_fill_price + (mental_stop_cents / 100 * profit_target_r)
                    log_warrior_entry(
                        trade_id=order_id,
                        symbol=symbol,
                        entry_price=float(actual_fill_price),  # Use actual fill
                        quantity=shares,
                        stop_price=float(actual_stop),  # Use recalculated stop
                        target_price=float(target),
                        trigger_type=trigger_type.value,
                        support_level=float(support_level),
                    )
                except Exception as e:
                    logger.warning(f"[Warrior Entry] DB log failed: {e}")
                
                logger.info(
                    f"[Warrior Entry] {symbol}: Bought {shares} shares @ ${actual_fill_price} "
                    f"({trigger_type.value})"
                )
                
                # Clear pending entry on successful fill
                self.clear_pending_entry(symbol)
                
            except Exception as e:
                logger.error(f"[Warrior Entry] {symbol}: Order failed: {e}")
                self.stats.last_error = str(e)
                # Clear pending entry on failure (allow retry)
                self.clear_pending_entry(symbol)
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
    
    def record_symbol_fail(self, symbol: str):
        """
        Record a stop-out failure for a symbol.
        
        Called by WarriorMonitor when a position is exited via mental_stop.
        After max_fails_per_symbol stops, further entries are blocked.
        """
        current = self._symbol_fails.get(symbol, 0)
        self._symbol_fails[symbol] = current + 1
        logger.info(
            f"[Warrior 2-Strike] {symbol}: Fail #{self._symbol_fails[symbol]} "
            f"(max={self._max_fails_per_symbol})"
        )
    
    def reset_daily_fails(self):
        """Reset daily fail counters. Call at start of trading day."""
        self._symbol_fails.clear()
        logger.info("[Warrior] Daily fail counters reset")
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_status(self) -> dict:
        """Get engine status."""
        return {
            "state": self.state.value,
            "trading_window": self.is_trading_window(),
            "market_hours": self.is_extended_hours() or self.config.sim_only,  # True during extended hours or sim
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
                "next_scan": (
                    (self.stats.last_scan_at + timedelta(minutes=self.config.scanner_interval_minutes)).isoformat()
                    if self.stats.last_scan_at and self.state != WarriorEngineState.STOPPED
                    else None
                ),
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
                "max_shares_per_trade": self.config.max_shares_per_trade,
            },
            "last_scan_result": self._last_scan_result,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_warrior_engine: Optional[WarriorEngine] = None


def get_warrior_engine() -> WarriorEngine:
    """Get singleton Warrior engine.
    
    Loads persisted settings on first creation.
    """
    global _warrior_engine
    if _warrior_engine is None:
        _warrior_engine = WarriorEngine()
        
        # Load persisted settings
        try:
            from nexus2.db.warrior_settings import load_warrior_settings, apply_settings_to_config
            settings = load_warrior_settings()
            if settings:
                apply_settings_to_config(_warrior_engine.config, settings)
        except Exception as e:
            logger.warning(f"[Warrior] Failed to load settings: {e}")
    
    return _warrior_engine

