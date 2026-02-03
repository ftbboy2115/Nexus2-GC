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
from pathlib import Path
from typing import Optional, List, Callable, Dict

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
from nexus2.domain.automation.warrior_engine_types import (
    WarriorEngineState,
    EntryTriggerType,
    WarriorEngineConfig,
    WarriorEngineStats,
    WatchedCandidate,
)
from nexus2.utils.time_utils import now_utc


logger = logging.getLogger(__name__)


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
        
        # Per-symbol fail tracking: block entries after too many stops
        # NOTE: Ross's actual rule is 3 CONSECUTIVE daily losses (not per-symbol)
        # Set high (10) to keep mechanism in place without being restrictive
        self._symbol_fails: Dict[str, int] = {}  # symbol -> stop count
        self._max_fails_per_symbol: int = 10  # Relaxed - can lower if needed
        
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
        self._get_order_status: Optional[Callable] = None  # Poll order for actual fill price
    
    def set_callbacks(
        self,
        submit_order: Callable = None,
        get_quote: Callable = None,
        get_quote_with_spread: Callable = None,
        get_positions: Callable = None,
        get_intraday_bars: Callable = None,
        check_pending_fill: Callable = None,
        create_pending_position: Callable = None,
        get_order_status: Callable = None,  # For polling actual fill price
    ):
        """Set callbacks for order execution and data."""
        self._submit_order = submit_order
        self._get_quote = get_quote
        self._get_quote_with_spread = get_quote_with_spread
        self._get_positions = get_positions
        self._get_intraday_bars = get_intraday_bars
        self._check_pending_fill = check_pending_fill
        self._create_pending_position = create_pending_position
        self._get_order_status = get_order_status  # For fill price polling
        
        # Also wire up monitor callbacks
        self.monitor.set_callbacks(
            get_price=get_quote,
            get_intraday_candles=get_intraday_bars,
            record_symbol_fail=self.record_symbol_fail,
            on_profit_exit=self._handle_profit_exit,
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
    
    def _handle_profit_exit(self, symbol: str, exit_price: float, exit_time: datetime):
        """
        Handle profit exit callback - enable re-entry for second wave.
        
        Option A (Base Hit + Re-Entry):
        After taking base_hit profit, reset entry_triggered to allow
        re-entry on volume explosion (with higher bar: 5x instead of 3x).
        
        Args:
            symbol: The symbol that just exited at profit
            exit_price: The price at which we exited
            exit_time: When the exit occurred
        """
        watched = self._watchlist.get(symbol)
        if not watched:
            logger.debug(f"[Warrior Engine] {symbol}: No watched symbol for re-entry")
            return
        
        # Reset entry_triggered to allow re-entry
        watched.entry_triggered = False
        watched.position_opened = False
        
        # Store exit metadata for re-entry guards
        from decimal import Decimal
        watched.last_exit_time = exit_time
        watched.last_exit_price = Decimal(str(exit_price))
        watched.entry_attempt_count += 1
        
        logger.info(
            f"[Warrior Engine] {symbol}: Re-entry ENABLED after profit exit @ ${exit_price:.2f} "
            f"(attempt #{watched.entry_attempt_count})"
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
                        status = calendar.get_market_status()
                        reason = status.reason or "off_hours"
                        next_open = status.next_open.strftime('%Y-%m-%d %H:%M ET') if status.next_open else 'unknown'
                        logger.info(f"[Warrior Scan] Market closed ({reason}) - next open: {next_open}")
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
        
        result = await asyncio.to_thread(self.scanner.scan, self.config.debug_catalyst)
        
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
                # Run in thread pool to avoid blocking event loop
                pmh = await asyncio.to_thread(fmp.get_premarket_high, symbol)
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
    
    def _get_key_levels(self, price: Decimal) -> list:
        """
        Returns key psychological price levels near the given price.
        
        Ross Cameron uses $0.50 and $1.00 levels explicitly for entries and targets,
        but $0.25 levels are also valid entry points based on Level 2 / order book.
        
        Args:
            price: Current price to calculate levels around
            
        Returns:
            List of nearby psychological levels sorted by proximity
        """
        price_float = float(price)
        levels = []
        
        granularity = self.config.level_granularity
        
        if granularity in ("quarter", "all"):
            # $0.25 increments (secondary levels)
            level_25 = Decimal(str(int(price_float * 4) / 4))
            levels.extend([level_25, level_25 + Decimal("0.25"), level_25 + Decimal("0.50")])
        
        if granularity in ("half", "quarter", "all"):
            # $0.50 increments (primary levels - Ross confirmed)
            level_50 = Decimal(str(int(price_float * 2) / 2))
            levels.extend([level_50, level_50 + Decimal("0.50")])
        
        # $1.00 increments (strongest levels - always included)
        level_100 = Decimal(str(int(price_float)))
        levels.extend([level_100, level_100 + Decimal("1.00")])
        
        # Remove duplicates, sort by proximity to current price
        unique_levels = sorted(set(levels))
        
        # Filter to levels within $0.60 of current price (reasonable entry range)
        nearby = [l for l in unique_levels if abs(l - price) < Decimal("0.60")]
        
        return nearby
    
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
                
                # Skip on non-market days (weekends, holidays) and outside extended hours
                # In historical replay mode: skip entry checks - sim step endpoint controls timing
                if self.config.sim_only:
                    # Check if we're in historical replay (HistoricalBarLoader has loaded symbols)
                    # This distinguishes historical replay from real-time sim mode
                    try:
                        from nexus2.adapters.simulation import get_historical_bar_loader
                        loader = get_historical_bar_loader()
                        if loader.get_loaded_symbols():
                            # Historical replay active - sim step endpoint controls timing
                            # Skip here to avoid duplicate check_entry_triggers calls
                            await asyncio.sleep(1)
                            continue
                    except Exception:
                        pass
                    # No historical bar data loaded - fall through to normal operation
                
                from nexus2.adapters.market_data.market_calendar import get_market_calendar
                calendar = get_market_calendar(paper=True)
                if not calendar.is_extended_hours_active():
                    status = calendar.get_market_status()
                    reason = status.reason or "off_hours"
                    logger.debug(f"[Warrior Watch] Market closed ({reason}) - skipping entry checks")
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue
                
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
        """
        Check all watched candidates for entry triggers.
        
        Delegated to warrior_engine_entry module for maintainability.
        """
        from nexus2.domain.automation.warrior_engine_entry import check_entry_triggers
        await check_entry_triggers(self)
    
    async def _check_orb_setup(self, watched: WatchedCandidate, current_price: Decimal):
        """
        Check for Opening Range Breakout setup.
        
        Delegated to warrior_engine_entry module for maintainability.
        """
        from nexus2.domain.automation.warrior_engine_entry import check_orb_setup
        await check_orb_setup(self, watched, current_price)
    
    async def _enter_position(
        self,
        watched: WatchedCandidate,
        entry_price: Decimal,
        trigger_type: EntryTriggerType,
    ):
        """
        Execute entry for a candidate.
        
        Delegated to warrior_engine_entry module for maintainability.
        """
        from nexus2.domain.automation.warrior_engine_entry import enter_position
        await enter_position(self, watched, entry_price, trigger_type)
    
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
            "market_hours": self.is_market_hours(),  # True during regular market hours (9:30 AM - 4:00 PM)
            "extended_hours": self.is_extended_hours() or self.config.sim_only,  # True during extended hours (4 AM - 8 PM) or sim
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
                    "position_opened": w.position_opened,  # True only when order submitted
                    "catalyst_type": w.candidate.catalyst_type,
                    "catalyst_description": w.candidate.catalyst_description,
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

