"""
Automation Scheduler

Background scheduler that runs the automation engine on a configurable interval.
Now includes EOD (end-of-day) callback for automatic MA trailing stop checks.
"""

import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, Callable, Awaitable
from nexus2.utils.time_utils import now_et

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """
    Background scheduler for the automation engine.
    
    Runs scan cycles at configurable intervals during market hours.
    Also triggers EOD (end-of-day) callback at 3:45 PM for MA trailing stops.
    """
    
    def __init__(
        self,
        interval_minutes: int = 15,
        market_open: dt_time = dt_time(9, 30),
        market_close: dt_time = dt_time(16, 0),
        eod_check_time: dt_time = dt_time(15, 45),  # 3:45 PM ET for MA trailing
        auto_shutdown_time: dt_time = dt_time(16, 2),  # 4:02 PM ET - auto-shutdown
        auto_execute: bool = False,  # Default to scan-only, no execution
        sim_mode: bool = False,  # Use simulation clock for market hours
    ):
        self.interval_minutes = interval_minutes
        self.market_open = market_open
        self.market_close = market_close
        self.eod_check_time = eod_check_time
        self.auto_shutdown_time = auto_shutdown_time
        self.sim_mode = sim_mode
        self.auto_execute = auto_execute
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._scan_callback: Optional[Callable[[], Awaitable]] = None
        self._execute_callback: Optional[Callable[[], Awaitable]] = None
        self._eod_callback: Optional[Callable[[], Awaitable]] = None
        
        # Track if EOD check was done today
        self._eod_check_done_date: Optional[str] = None
        
        # Track if auto-shutdown was done today
        self._auto_shutdown_done_date: Optional[str] = None
        
        # Stats
        self.cycles_run = 0
        self.eod_checks_run = 0
        self.last_run: Optional[datetime] = None
        self.last_eod_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        # Last scan signals (for UI display)
        self.last_signals: list = []
        self.last_signals_at: Optional[datetime] = None
        
        # Store full scan result for diagnostics
        self.last_scan_result = None
        
        # Load persisted settings
        try:
            from nexus2.db.scheduler_settings import load_scheduler_settings
            saved = load_scheduler_settings()
            if saved:
                if "interval_minutes" in saved:
                    self.interval_minutes = saved["interval_minutes"]
                if "auto_execute" in saved:
                    self.auto_execute = saved["auto_execute"]
        except Exception as e:
            print(f"[Scheduler] Failed to load saved settings: {e}")
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_market_hours(self) -> bool:
        """
        Check if market is currently open.
        
        In sim_mode, uses the simulation clock.
        Otherwise uses Alpaca clock API for accurate detection.
        """
        # In sim_mode, use the simulation clock
        if self.sim_mode:
            try:
                from nexus2.adapters.simulation import get_simulation_clock
                clock = get_simulation_clock()
                return clock.is_market_hours()
            except Exception:
                # If sim clock not available, treat as market hours for testing
                return True
        
        # Real time: use Alpaca calendar
        try:
            from nexus2.adapters.market_data.market_calendar import get_market_calendar
            calendar = get_market_calendar(paper=True)
            return calendar.is_market_open()
        except Exception:
            # Fallback to basic time check
            now = now_et()
            current_time = now.time()
            weekday = now.weekday()
            
            if weekday >= 5:
                return False
            
            return self.market_open <= current_time <= self.market_close
    
    @property
    def is_eod_window(self) -> bool:
        """Check if currently within EOD check window (3:45-4:00 PM ET)."""
        # In sim_mode, use the simulation clock
        if self.sim_mode:
            try:
                from nexus2.adapters.simulation import get_simulation_clock
                clock = get_simulation_clock()
                return clock.is_eod_window()
            except Exception:
                pass
        
        # Real time check - MUST use Eastern Time (VPS may be on UTC)
        import pytz
        eastern = pytz.timezone('America/New_York')
        current_et = datetime.now(eastern)
        current_time = current_et.time()
        weekday = current_et.weekday()
        
        # Weekends
        if weekday >= 5:
            return False
        
        return self.eod_check_time <= current_time <= self.market_close
    
    def set_callbacks(
        self,
        scan_callback: Callable[[], Awaitable] = None,
        execute_callback: Callable[[], Awaitable] = None,
        eod_callback: Callable[[], Awaitable] = None,
    ):
        """Set the callbacks for scanning, executing, and EOD checks."""
        if scan_callback:
            self._scan_callback = scan_callback
        if execute_callback:
            self._execute_callback = execute_callback
        if eod_callback:
            self._eod_callback = eod_callback
    
    async def start(self) -> dict:
        """Start the scheduler."""
        if self._running:
            return {"status": "already_running"}
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        
        logger.info(f"Scheduler started (interval: {self.interval_minutes}m, auto_execute: {self.auto_execute})")
        
        return {
            "status": "started",
            "interval_minutes": self.interval_minutes,
            "auto_execute": self.auto_execute,
            "eod_check_time": str(self.eod_check_time),
        }
    
    async def stop(self) -> dict:
        """Stop the scheduler."""
        if not self._running:
            return {"status": "already_stopped"}
        
        self._running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Scheduler stopped")
        
        return {"status": "stopped"}
    
    async def _run_loop(self):
        """Main scheduling loop with smart pre-market wait."""
        while self._running:
            try:
                now = now_et()
                
                # FAST CHECK: Skip weekends immediately (no API call needed)
                if not self.sim_mode and now.weekday() >= 5:
                    logger.info(f"[Scheduler] Weekend ({now.strftime('%A')}) - skipping scan cycle")
                    await self._smart_wait_for_market_open(now)
                    continue
                
                # Check if market hours (uses sim clock if sim_mode)
                if self.is_market_hours:
                    # CRITICAL: Run EOD check FIRST (before scan) to ensure exits happen before 4PM
                    # The scan can take 4+ minutes due to FMP rate limiting
                    await self._check_eod()
                    
                    # Then run the normal scan/execute cycle
                    await self._run_cycle()
                    
                    # Check if time for auto-shutdown (4:02 PM - stops scheduler after market close)
                    shutdown_triggered = await self._check_auto_shutdown()
                    if shutdown_triggered:
                        break  # Exit loop after shutdown
                    
                    # Normal interval wait (shorter in sim_mode for faster testing)
                    interval_seconds = self.interval_minutes * 60
                    if self.sim_mode:
                        # In sim_mode: advance sim clock by interval, then short real wait
                        from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
                        from nexus2.api.routes.automation_state import get_sim_broker
                        
                        clock = get_simulation_clock()
                        data = get_mock_market_data()
                        broker = get_sim_broker()
                        
                        # Advance sim clock by scan interval
                        clock.advance(minutes=self.interval_minutes)
                        
                        # Update prices for new time
                        if broker:
                            for sym in data.get_symbols():
                                price = data.get_current_price(sym)
                                if price:
                                    broker.set_price(sym, price)
                                    broker._check_stop_orders(sym)
                        
                        print(f"⏰ [SIM] Clock advanced to {clock.current_time.strftime('%Y-%m-%d %H:%M')}")
                        
                        # Short real wait (5 seconds) for rapid testing
                        interval_seconds = 5
                        
                    self.next_run = now_et() + timedelta(seconds=interval_seconds)
                    await asyncio.sleep(interval_seconds)
                    
                else:
                    if self.sim_mode:
                        # In sim_mode, don't wait for market - run anyway
                        logger.info("[SIM] Outside sim market hours but running anyway")
                        await self._run_cycle()
                        await asyncio.sleep(5)  # Short interval for sim
                    else:
                        # Real time: outside market hours, use smart waiting
                        await self._smart_wait_for_market_open(now)
                        
                        # Reset EOD flag at midnight
                        self._reset_eod_flag_if_new_day()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Scheduler error: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(60)
    
    async def _smart_wait_for_market_open(self, now: datetime):
        """
        Smart waiting when outside market hours.
        
        - If market closed for the day (after 4pm): sleep until tomorrow
        - If weekend: sleep until Monday 9:25 AM
        - If before market open today: adaptive sleep (shorter as open approaches)
        """
        import pytz
        
        current_time = now.time()
        weekday = now.weekday()
        
        # Weekend handling
        if weekday >= 5:
            # Calculate time until Monday 9:25 AM
            days_until_monday = (7 - weekday) % 7 or 7
            if weekday == 5:  # Saturday
                days_until_monday = 2
            else:  # Sunday
                days_until_monday = 1
            
            next_monday = now.replace(hour=9, minute=25, second=0, microsecond=0)
            next_monday = next_monday.replace(day=now.day + days_until_monday)
            sleep_seconds = min(3600, (next_monday - now).total_seconds())  # Cap at 1 hour
            logger.debug(f"Weekend - sleeping {sleep_seconds:.0f}s (next check towards Monday)")
            self.next_run = now + timedelta(seconds=sleep_seconds)
            await asyncio.sleep(sleep_seconds)
            return
        
        # If after market close (4pm+), sleep longer
        if current_time >= self.market_close:
            # Market closed for today, sleep 1 hour
            sleep_seconds = 3600
            logger.debug(f"After market close - sleeping {sleep_seconds}s")
            self.next_run = now + timedelta(seconds=sleep_seconds)
            await asyncio.sleep(sleep_seconds)
            return
        
        # Before market open - adaptive waiting
        market_open_today = now.replace(
            hour=self.market_open.hour, 
            minute=self.market_open.minute, 
            second=0, 
            microsecond=0
        )
        seconds_to_open = (market_open_today - now).total_seconds()
        
        if seconds_to_open <= 0:
            # Market should be open - something's off, short wait
            logger.debug("Unexpected state - short wait")
            await asyncio.sleep(30)
            return
        
        if seconds_to_open <= 60:
            # Less than 1 minute to open - check every 10 seconds
            sleep_seconds = 10
            logger.info(f"🔔 Market opens in {seconds_to_open:.0f}s - checking every {sleep_seconds}s")
        elif seconds_to_open <= 300:
            # Less than 5 minutes to open - check every 30 seconds
            sleep_seconds = 30
            logger.info(f"⏰ Market opens in {seconds_to_open/60:.1f}m - checking every {sleep_seconds}s")
        elif seconds_to_open <= 900:
            # Less than 15 minutes to open - check every 60 seconds
            sleep_seconds = 60
            logger.debug(f"Market opens in {seconds_to_open/60:.1f}m - sleeping {sleep_seconds}s")
        else:
            # More than 15 minutes to open - normal interval (capped at 5 min)
            sleep_seconds = min(300, self.interval_minutes * 60)
            logger.debug(f"Market opens in {seconds_to_open/60:.1f}m - sleeping {sleep_seconds}s")
        
        self.next_run = now + timedelta(seconds=sleep_seconds)
        await asyncio.sleep(sleep_seconds)
    
    def _reset_eod_flag_if_new_day(self):
        """Reset EOD check flag if it's a new day."""
        today = now_et().strftime("%Y-%m-%d")
        if self._eod_check_done_date != today:
            self._eod_check_done_date = None
    
    async def _check_eod(self):
        """Check and run EOD callback if in window and not yet done today."""
        if not self._eod_callback:
            return
        
        if not self.is_eod_window:
            return
        
        # Get today's date (use sim clock in sim_mode)
        if self.sim_mode:
            try:
                from nexus2.adapters.simulation import get_simulation_clock
                clock = get_simulation_clock()
                today = clock.get_trading_day()
            except Exception:
                today = now_et().strftime("%Y-%m-%d")
        else:
            today = now_et().strftime("%Y-%m-%d")
        
        if self._eod_check_done_date == today:
            # Already ran EOD check today
            return
        
        # Run EOD check
        mode_indicator = "[SIM EOD]" if self.sim_mode else "[EOD]"
        logger.info(f"{mode_indicator} Running end-of-day MA check...")
        print(f"🌅 {mode_indicator} Running EOD MA trailing stop check for {today}")
        try:
            result = await self._eod_callback()
            self._eod_check_done_date = today
            self.eod_checks_run += 1
            self.last_eod_run = now_et()
            logger.info(f"{mode_indicator} MA check result: {result}")
        except Exception as e:
            logger.error(f"{mode_indicator} MA check error: {e}")
            self.last_error = f"EOD: {e}"
    
    async def _check_auto_shutdown(self) -> bool:
        """
        Check if time for automatic scheduler shutdown (4:02 PM ET).
        
        Prevents overnight resource usage and avoids weekend ghost trades.
        Sends Discord notification on success or failure.
        
        Returns:
            True if shutdown was triggered, False otherwise
        """
        # Skip in sim mode - let simulation run continuously
        if self.sim_mode:
            return False
        
        # Get today's date
        import pytz
        eastern = pytz.timezone('America/New_York')
        current_et = datetime.now(eastern)
        today = current_et.strftime("%Y-%m-%d")
        current_time = current_et.time()
        
        # Skip if already shut down today
        if self._auto_shutdown_done_date == today:
            return False
        
        # Check if we're at or past shutdown time
        if current_time < self.auto_shutdown_time:
            return False
        
        # Time to shut down!
        logger.info(f"[AutoShutdown] Triggering automatic shutdown at {current_et.strftime('%H:%M:%S ET')}")
        print(f"\U0001f319 [AutoShutdown] Stopping scheduler at {current_et.strftime('%H:%M:%S ET')}")
        
        shutdown_success = True
        error_message = None
        
        try:
            # Stop the scheduler
            self._running = False
            self._auto_shutdown_done_date = today
            
            # Also stop the position monitor (import here to avoid circular imports)
            try:
                from nexus2.api.routes.automation_state import get_monitor
                monitor = get_monitor()
                if monitor and monitor._running:
                    await monitor.stop()
                    logger.info("[AutoShutdown] Position monitor stopped")
            except Exception as e:
                logger.warning(f"[AutoShutdown] Monitor stop failed: {e}")
                error_message = f"Monitor: {e}"
            
        except Exception as e:
            shutdown_success = False
            error_message = str(e)
            logger.error(f"[AutoShutdown] Failed: {e}")
        
        # Send Discord notification
        try:
            from nexus2.adapters.notifications.discord import DiscordNotifier
            notifier = DiscordNotifier()
            
            if shutdown_success:
                message = f"\U0001f319 **NAC Scheduler Shutdown Complete**\n"
                message += f"Time: {current_et.strftime('%I:%M %p ET')}\n"
                message += f"Cycles run today: {self.cycles_run}\n"
                message += f"EOD checks: {self.eod_checks_run}"
                if error_message:
                    message += f"\n\u26a0\ufe0f Warning: {error_message}"
            else:
                message = f"\u274c **NAC Scheduler Shutdown FAILED**\n"
                message += f"Time: {current_et.strftime('%I:%M %p ET')}\n"
                message += f"Error: {error_message}"
            
            notifier.send_system_alert(message)
            logger.info(f"[AutoShutdown] Discord notification sent")
            
        except Exception as e:
            logger.warning(f"[AutoShutdown] Discord notification failed: {e}")
        
        return shutdown_success
    
    async def _run_cycle(self):
        """Run one scan/execute cycle."""
        self.last_run = now_et()
        self.cycles_run += 1
        
        logger.info(f"Running cycle #{self.cycles_run}")
        
        try:
            if self.auto_execute and self._execute_callback:
                # Full automation - scan and execute
                result = await self._execute_callback()
                logger.info(f"Execute result: {result}")
            elif self._scan_callback:
                # Scan only
                result = await self._scan_callback()
                # Store signals for UI display
                if result:
                    # Check if result is a UnifiedScanResult (has diagnostics) or just signals
                    if hasattr(result, 'signals'):
                        self.last_signals = result.signals if result.signals else []
                        self.last_scan_result = result  # Store full result with diagnostics
                    else:
                        self.last_signals = result if isinstance(result, list) else []
                        self.last_scan_result = None
                    self.last_signals_at = now_et()
                    
                    # Send Discord notification for new signals
                    self._send_discord_notification(self.last_signals)
                    
                logger.info(f"Scan result: {len(result) if result else 0} signals")
            else:
                logger.warning("No callbacks configured")
                
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Cycle error: {e}")
    
    def _send_discord_notification(self, signals: list) -> None:
        """Send Discord notification for new signals."""
        try:
            from nexus2.adapters.notifications.discord import DiscordNotifier
            
            notifier = DiscordNotifier()
            if not notifier.config.enabled:
                return
            
            # Format signal message
            signal_lines = []
            for sig in signals[:5]:  # Limit to 5 signals
                symbol = getattr(sig, 'symbol', sig.get('symbol', '?'))
                setup_type = getattr(sig, 'setup_type', sig.get('setup_type', '?'))
                if hasattr(setup_type, 'value'):
                    setup_type = setup_type.value
                quality = getattr(sig, 'quality_score', sig.get('quality_score', '?'))
                entry = getattr(sig, 'entry_price', sig.get('entry_price', 0))
                stop = getattr(sig, 'tactical_stop', sig.get('tactical_stop', 0))
                
                signal_lines.append(f"**{symbol}** ({setup_type}) - Q:{quality}/10 | Entry: ${entry} | Stop: ${stop}")
            
            message = f"Found {len(signals)} signal(s) at {self.last_signals_at.strftime('%H:%M:%S')}:\n"
            message += "\n".join(signal_lines)
            
            if len(signals) > 5:
                message += f"\n... and {len(signals) - 5} more"
            
            notifier.send_scanner_alert(message)
            logger.info(f"[Discord] Sent notification for {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"[Discord] Notification failed: {e}")
    
    def get_status(self) -> dict:
        """Get current scheduler status."""
        # Get Eastern Time for debugging
        import pytz
        eastern = pytz.timezone('America/New_York')
        current_et = datetime.now(eastern)
        
        return {
            "running": self._running,
            "interval_minutes": self.interval_minutes,
            "auto_execute": self.auto_execute,
            "is_market_hours": self.is_market_hours,
            "is_eod_window": self.is_eod_window,
            "eod_check_time": str(self.eod_check_time),
            "market_close_time": str(self.market_close),
            "eod_check_done_today": self._eod_check_done_date == now_et().strftime("%Y-%m-%d"),
            "cycles_run": self.cycles_run,
            "eod_checks_run": self.eod_checks_run,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_eod_run": self.last_eod_run.isoformat() if self.last_eod_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_error": self.last_error,
            "last_signals_count": len(self.last_signals) if self.last_signals else 0,
            "last_signals_at": self.last_signals_at.isoformat() if self.last_signals_at else None,
            "eastern_time": current_et.strftime("%Y-%m-%d %H:%M:%S ET"),
        }
    
    def get_last_signals(self) -> list:
        """Get signals from last scan cycle for UI display."""
        if not self.last_signals:
            return []
        
        # Include the scan timestamp with each signal
        found_at = self.last_signals_at.isoformat() if self.last_signals_at else None
        
        # Convert Signal objects to dicts for JSON serialization
        signals = []
        for sig in self.last_signals:
            if hasattr(sig, '__dict__'):
                # Signal object
                signals.append({
                    "symbol": getattr(sig, 'symbol', ''),
                    "setup_type": getattr(sig, 'setup_type', '').value if hasattr(getattr(sig, 'setup_type', ''), 'value') else str(getattr(sig, 'setup_type', '')),
                    "quality_score": getattr(sig, 'quality_score', 0),
                    "tier": getattr(sig, 'tier', ''),
                    "entry_price": str(getattr(sig, 'entry_price', 0)),
                    "tactical_stop": str(getattr(sig, 'tactical_stop', 0)),
                    "stop_percent": getattr(sig, 'stop_percent', 0),
                    "rs_percentile": getattr(sig, 'rs_percentile', 0),
                    "found_at": found_at,
                })
            elif isinstance(sig, dict):
                sig_copy = sig.copy()
                sig_copy["found_at"] = found_at
                signals.append(sig_copy)
        
        return signals
