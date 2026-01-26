"""
Position Monitor

Monitors open positions for stop hits, profit targets, and exit signals.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
from nexus2.utils.time_utils import now_utc, now_et


logger = logging.getLogger(__name__)

# Trade event logging
from nexus2.domain.automation.trade_event_service import trade_event_service


class ExitReason(Enum):
    """Reason for exiting a position."""
    STOP_HIT = "stop_hit"
    PROFIT_TARGET = "profit_target"
    TRAILING_STOP = "trailing_stop"
    PARTIAL_EXIT = "partial_exit"
    MANUAL = "manual"


@dataclass
class ExitSignal:
    """Signal to exit a position."""
    position_id: str
    symbol: str
    reason: ExitReason
    exit_price: Decimal
    shares_to_exit: int  # Can be partial
    pnl_estimate: Decimal
    stop_price: Decimal = Decimal("0")  # For stop hit notifications
    generated_at: datetime = None
    # Analytics fields for trade review
    days_held: int = 0  # Days from open to exit
    exit_type: str = ""  # "partial", "stop", "ma_trail"
    trigger_reason: str = ""  # "Day 3 + in profit", "Close < 10 EMA"
    r_multiple: float = 0.0  # Gain in R at exit
    
    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = now_utc()


class PositionMonitor:
    """
    Monitors open positions for exit conditions.
    
    KK-style rules:
    - Stop-loss: Exit if price hits tactical stop
    - Trailing stop: Move stop to breakeven after 1R gain
    - Partial exit: Take profits on strength (Day 3-5, 2R+)
    
    Supports two modes:
    - Polling mode: Checks prices every N seconds (default)
    - Streaming mode: Real-time price updates via Alpaca WebSocket
    """
    
    def __init__(
        self,
        check_interval_seconds: int = 60,
        enable_trailing_stops: bool = True,
        enable_partial_exits: bool = True,
        breakeven_threshold_r: float = 1.0,  # Move to breakeven at 1R
        partial_exit_threshold_r: float = 2.0,  # Start partials at 2R (legacy, not KK-style)
        partial_exit_percent: float = 0.25,  # Exit 25% at a time (legacy)
        use_streaming: bool = False,  # Use real-time streaming instead of polling
        # KK-style day-based partials
        kk_style_partials: bool = True,  # Use day-based instead of R-based
        partial_exit_days: int = 3,  # Days before partial (KK: 3-5)
        partial_exit_fraction: float = 0.5,  # Sell 50% (KK: 1/3 to 1/2)
        # EOD window (KK-style: exits only in EOD window)
        eod_window_start_hour: int = 15,  # 3:45 PM ET = 15:45
        eod_window_start_minute: int = 45,
        eod_window_end_hour: int = 15,  # 3:55 PM ET = 15:55
        eod_window_end_minute: int = 55,
        eod_only_mode: bool = True,  # If True, only check exits during EOD window
    ):
        self.check_interval = check_interval_seconds
        self.enable_trailing_stops = enable_trailing_stops
        self.enable_partial_exits = enable_partial_exits
        self.breakeven_threshold_r = breakeven_threshold_r
        self.partial_exit_threshold_r = partial_exit_threshold_r
        self.partial_exit_percent = partial_exit_percent
        self.use_streaming = use_streaming
        # KK-style
        self.kk_style_partials = kk_style_partials
        self.partial_exit_days = partial_exit_days
        self.partial_exit_fraction = partial_exit_fraction
        # EOD window configuration
        self.eod_window_start_hour = eod_window_start_hour
        self.eod_window_start_minute = eod_window_start_minute
        self.eod_window_end_hour = eod_window_end_hour
        self.eod_window_end_minute = eod_window_end_minute
        self.eod_only_mode = eod_only_mode
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Streaming client (optional)
        self._streaming_client = None
        
        # Callbacks
        self._get_positions: Optional[Callable] = None
        self._get_price: Optional[Callable] = None
        self._execute_exit: Optional[Callable] = None
        self._update_stop: Optional[Callable] = None  # For trailing stops
        
        # Deduplication: track positions with pending exits
        self._pending_exits: set = set()
        
        # Stats
        self.checks_run = 0
        self.exits_triggered = 0
        self.partials_triggered = 0  # Track partial exits
        self.last_check: Optional[datetime] = None
        self.last_error: Optional[str] = None
    
    def set_callbacks(
        self,
        get_positions: Callable = None,
        get_price: Callable[[str], Decimal] = None,
        execute_exit: Callable = None,
        update_stop: Callable = None,
        streaming_client = None,  # AlpacaStreamingClient instance
    ):
        """Set the callbacks for position data and execution."""
        self._get_positions = get_positions
        self._get_price = get_price
        self._execute_exit = execute_exit
        self._update_stop = update_stop
        self._streaming_client = streaming_client
    
    async def start(self) -> dict:
        """Start monitoring positions."""
        if self._running:
            return {"status": "already_running"}
        
        self._running = True
        
        # Choose monitoring mode
        if self.use_streaming and self._streaming_client:
            # Streaming mode: register price callback
            self._streaming_client.set_callbacks(
                on_price_update=self._on_streaming_price_update
            )
            await self._streaming_client.start()
            
            # Also subscribe to current positions
            await self._subscribe_to_positions()
            
            logger.info("Position monitor started (streaming mode)")
        else:
            # Polling mode: periodic checks
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info(f"Position monitor started (polling: {self.check_interval}s)")
        
        return {
            "status": "started",
            "mode": "streaming" if self.use_streaming else "polling",
            "check_interval": self.check_interval,
        }
    
    async def stop(self) -> dict:
        """Stop monitoring."""
        if not self._running:
            return {"status": "already_stopped"}
        
        self._running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Position monitor stopped")
        return {"status": "stopped"}
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                # Skip on non-market days (weekends, holidays)
                from nexus2.adapters.market_data.market_calendar import get_market_calendar
                calendar = get_market_calendar(paper=True)
                if not calendar.is_market_open():
                    logger.debug("Market closed - skipping position check")
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue
                
                await self._check_positions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(30)  # Wait before retry
    
    def _is_in_eod_window(self) -> bool:
        """
        Check if current time is within the EOD window (3:45-3:55 PM ET).
        
        Per KK strategy: Trailing and Trend-Break exits are executed between
        3:45 PM and 3:55 PM ET to ensure execution before the 4:00 PM close.
        """
        current_et = now_et()
        current_minutes = current_et.hour * 60 + current_et.minute
        start_minutes = self.eod_window_start_hour * 60 + self.eod_window_start_minute
        end_minutes = self.eod_window_end_hour * 60 + self.eod_window_end_minute
        return start_minutes <= current_minutes <= end_minutes
    
    async def _check_positions(self):
        """Check all open positions for exit conditions."""
        self.last_check = now_utc()
        self.checks_run += 1
        
        if not self._get_positions:
            logger.warning("No get_positions callback")
            return
        
        positions = await self._get_positions()
        if not positions:
            return
        
        # KK-style: Only check exits during EOD window (3:45-3:55 PM ET)
        if self.eod_only_mode and not self._is_in_eod_window():
            current_et = now_et()
            logger.debug(
                f"Outside EOD window ({current_et.strftime('%H:%M')} ET) - "
                f"skipping exit checks for {len(positions)} positions"
            )
            return
        
        logger.info(f"[EOD Window] Checking {len(positions)} positions for exit conditions")
        
        for position in positions:
            try:
                exit_signal = await self._evaluate_position(position)
                if exit_signal:
                    await self._handle_exit(exit_signal)
            except Exception as e:
                logger.error(f"Error evaluating position {position.get('symbol', '?')}: {e}")
    
    async def _evaluate_position(self, position: dict) -> Optional[ExitSignal]:
        """
        Evaluate a single position for exit conditions.
        
        Returns ExitSignal if exit should occur, None otherwise.
        """
        symbol = position.get("symbol", "")
        entry_price = Decimal(str(position.get("entry_price", 0) or 0))
        
        # Handle None stop values - positions without stops can't be evaluated
        raw_current_stop = position.get("current_stop")
        raw_initial_stop = position.get("initial_stop")
        
        if not raw_current_stop and not raw_initial_stop:
            # External position without stops - skip evaluation
            return None
        
        current_stop = Decimal(str(raw_current_stop or 0))
        initial_stop = Decimal(str(raw_initial_stop or 0))
        shares = int(position.get("remaining_shares", 0))
        position_id = position.get("id", "")
        
        if shares <= 0:
            return None
        
        # Get current price
        if not self._get_price:
            return None
        
        current_price = await self._get_price(symbol)
        if not current_price:
            return None
        
        current_price = Decimal(str(current_price))
        
        # Calculate R multiple
        risk_per_share = entry_price - initial_stop
        if risk_per_share <= 0:
            return None
        
        current_gain = current_price - entry_price
        r_multiple = float(current_gain / risk_per_share)
        
        # Check 1: Stop-loss hit
        # Skip if already pending exit (prevents duplicate notifications)
        if position_id in self._pending_exits:
            logger.debug(f"[STOP CHECK] {symbol}: Skipping - exit already pending")
            return None
        
        if current_price <= current_stop:
            logger.warning(
                f"[STOP CHECK] {symbol}: price=${current_price} <= stop=${current_stop} "
                f"(entry=${entry_price}) -> TRIGGERING EXIT"
            )
            # Mark as pending to prevent duplicates
            self._pending_exits.add(position_id)
            
            pnl = (current_price - entry_price) * shares
            return ExitSignal(
                position_id=position_id,
                symbol=symbol,
                reason=ExitReason.STOP_HIT,
                exit_price=current_price,
                shares_to_exit=shares,
                pnl_estimate=pnl,
                stop_price=current_stop,
            )
        else:
            # Log non-triggering checks at debug level
            logger.debug(
                f"[STOP CHECK] {symbol}: price=${current_price} > stop=${current_stop} -> OK"
            )
        
        # Check 2: Trailing stop (move to breakeven at 1R)
        # KK-style: Don't trail on Day 0 - let the trade work
        if self.enable_trailing_stops and r_multiple >= self.breakeven_threshold_r:
            # Calculate days held
            opened_at = position.get("opened_at")
            days_held = 0
            if opened_at:
                if isinstance(opened_at, str):
                    opened_at = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                # Make timezone-aware if naive (assume ET)
                if opened_at.tzinfo is None:
                    from zoneinfo import ZoneInfo
                    opened_at = opened_at.replace(tzinfo=ZoneInfo("America/New_York"))
                days_held = (now_et().date() - opened_at.date()).days
            
            # Only trail after Day 0
            if days_held >= 1 and current_stop < entry_price:
                logger.info(f"{symbol}: Moving stop to breakeven at {r_multiple:.1f}R (Day {days_held})")
                if self._update_stop:
                    await self._update_stop(position_id, entry_price)
                    # Log breakeven event
                    trade_event_service.log_nac_breakeven(position_id, symbol, entry_price)
            elif days_held == 0 and current_stop < entry_price:
                logger.debug(f"{symbol}: Skipping breakeven trail on Day 0 (at {r_multiple:.1f}R)")
        
        # Check 3: Partial exit (KK-style day-based or legacy R-based)
        if self.enable_partial_exits:
            partial_signal = await self._check_partial_exit(
                position, current_price, entry_price, shares, r_multiple
            )
            if partial_signal:
                return partial_signal
        
        return None
    
    async def _check_partial_exit(
        self,
        position: dict,
        current_price: Decimal,
        entry_price: Decimal,
        shares: int,
        r_multiple: float,
    ) -> Optional[ExitSignal]:
        """Check if partial exit should be triggered (KK-style or legacy)."""
        position_id = position.get("id", "")
        symbol = position.get("symbol", "")
        
        # Check if partial already taken
        partial_taken = position.get("partial_taken", False)
        if partial_taken:
            return None  # Already took partial, don't do another
        
        # KK-style: Day-based partial exit
        if self.kk_style_partials:
            opened_at = position.get("opened_at")
            if not opened_at:
                return None
            
            # Calculate days held
            if isinstance(opened_at, str):
                opened_at = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
            # Make timezone-aware if naive (assume ET)
            if opened_at.tzinfo is None:
                from zoneinfo import ZoneInfo
                opened_at = opened_at.replace(tzinfo=ZoneInfo("America/New_York"))
            days_held = (now_et().date() - opened_at.date()).days
            
            # Check: Days >= threshold AND in profit
            if days_held >= self.partial_exit_days and current_price > entry_price:
                shares_to_exit = int(shares * self.partial_exit_fraction)
                if shares_to_exit >= 1:
                    pnl = (current_price - entry_price) * shares_to_exit
                    logger.info(
                        f"[KK Partial] {symbol}: Day {days_held} + in profit -> "
                        f"Selling {shares_to_exit} shares ({self.partial_exit_fraction*100:.0f}%)"
                    )
                    self.partials_triggered += 1
                    
                    # Also move stop to breakeven
                    if self._update_stop:
                        logger.info(f"[KK Partial] {symbol}: Moving stop to breakeven ${entry_price}")
                        await self._update_stop(position_id, entry_price)
                        # Log breakeven event
                        trade_event_service.log_nac_breakeven(position_id, symbol, entry_price)
                    
                    return ExitSignal(
                        position_id=position_id,
                        symbol=symbol,
                        reason=ExitReason.PARTIAL_EXIT,
                        exit_price=current_price,
                        shares_to_exit=shares_to_exit,
                        pnl_estimate=pnl,
                        days_held=days_held,
                        exit_type="partial",
                        trigger_reason=f"Day {days_held} + in profit",
                        r_multiple=r_multiple,
                    )
        else:
            # Legacy R-based partial exit
            if r_multiple >= self.partial_exit_threshold_r:
                shares_to_exit = int(shares * self.partial_exit_percent)
                if shares_to_exit >= 1:
                    pnl = (current_price - entry_price) * shares_to_exit
                    return ExitSignal(
                        position_id=position_id,
                        symbol=symbol,
                        reason=ExitReason.PARTIAL_EXIT,
                        exit_price=current_price,
                        shares_to_exit=shares_to_exit,
                        pnl_estimate=pnl,
                    )
        
        return None
    
    async def _handle_exit(self, signal: ExitSignal):
        """Handle an exit signal."""
        logger.info(f"Exit signal: {signal.symbol} - {signal.reason.value} - {signal.shares_to_exit} shares")
        
        # PSM: Set to PENDING_EXIT before executing
        try:
            from nexus2.db.nac_db import set_pending_exit, set_exit_order_id, confirm_exit
            set_pending_exit(signal.position_id)
        except Exception as psm_err:
            logger.debug(f"[NAC PSM] set_pending_exit failed (may not be in nac_db): {psm_err}")
        
        if self._execute_exit:
            try:
                exit_result = await self._execute_exit(signal)
                self.exits_triggered += 1
                
                # PSM: Store exit order ID and confirm exit
                try:
                    if exit_result and hasattr(exit_result, 'broker_order_id'):
                        set_exit_order_id(signal.position_id, str(exit_result.broker_order_id))
                    
                    # Determine if partial or full exit
                    is_partial = signal.reason == ExitReason.PARTIAL_EXIT
                    from nexus2.db.nac_db import confirm_exit as nac_confirm_exit
                    nac_confirm_exit(
                        trade_id=signal.position_id,
                        exit_price=float(signal.exit_price),
                        exit_reason=signal.reason.value,
                        quantity_exited=signal.shares_to_exit if is_partial else None,
                    )
                except Exception as psm_confirm_err:
                    logger.debug(f"[NAC PSM] confirm_exit skipped: {psm_confirm_err}")
                
                # Log trade event
                if signal.reason == ExitReason.PARTIAL_EXIT:
                    trade_event_service.log_nac_partial_exit(
                        position_id=signal.position_id,
                        symbol=signal.symbol,
                        shares_sold=signal.shares_to_exit,
                        exit_price=signal.exit_price,
                        pnl=signal.pnl_estimate,
                        days_held=signal.days_held,
                    )
                else:
                    exit_type_map = {
                        ExitReason.STOP_HIT: "stop_hit",
                        ExitReason.TRAILING_STOP: "trailing_stop",
                        ExitReason.PROFIT_TARGET: "profit_target",
                    }
                    trade_event_service.log_nac_exit(
                        position_id=signal.position_id,
                        symbol=signal.symbol,
                        exit_price=signal.exit_price,
                        exit_type=exit_type_map.get(signal.reason, "manual"),
                        pnl=signal.pnl_estimate,
                        reason=signal.trigger_reason or signal.reason.value,
                    )
                
                # Clear from pending exits
                self._pending_exits.discard(signal.position_id)
                
                # Send Discord notification for exit
                try:
                    from nexus2.db import SessionLocal, SchedulerSettingsRepository
                    from nexus2.adapters.notifications import DiscordNotifier
                    
                    db = SessionLocal()
                    try:
                        settings_repo = SchedulerSettingsRepository(db)
                        settings = settings_repo.get()
                        discord_enabled = getattr(settings, 'discord_alerts_enabled', 'true') == 'true'
                        sim_mode = getattr(settings, 'sim_mode', 'false') == 'true'
                    finally:
                        db.close()
                    
                    if discord_enabled:
                        notifier = DiscordNotifier()
                        mode_label = "🧪 SIM" if sim_mode else "🔴 LIVE"
                        pnl_emoji = "✅" if signal.pnl_estimate >= 0 else "❌"
                        
                        reason_label = signal.reason.value.upper().replace("_", " ")
                        stop_info = f" @ ${signal.stop_price}" if signal.stop_price else ""
                        notifier.send_trade_alert(
                            message=f"{mode_label} | EXIT: {signal.symbol} x {signal.shares_to_exit}\n{reason_label}{stop_info} | P&L: {pnl_emoji} ${signal.pnl_estimate:.2f}",
                            trade_id=signal.position_id[:8] if signal.position_id else "N/A"
                        )
                except Exception as e:
                    logger.warning(f"Discord exit notification failed: {e}")
                    
            except Exception as e:
                logger.error(f"Exit execution failed: {e}")
                self.last_error = str(e)
                
                # PSM: Revert PENDING_EXIT on failure
                try:
                    from nexus2.db.nac_db import revert_pending_exit
                    revert_pending_exit(signal.position_id)
                except Exception:
                    pass
                
                # Clear from pending on failure too (allow retry next cycle)
                self._pending_exits.discard(signal.position_id)
        else:
            logger.warning("No execute_exit callback - signal not acted on")
    
    def get_status(self) -> dict:
        """Get monitor status."""
        return {
            "running": self._running,
            "mode": "streaming" if self.use_streaming else "polling",
            "check_interval_seconds": self.check_interval,
            "checks_run": self.checks_run,
            "exits_triggered": self.exits_triggered,
            "last_check": (self.last_check.isoformat() + "Z") if self.last_check else None,
            "last_error": self.last_error,
            "settings": {
                "trailing_stops": self.enable_trailing_stops,
                "partial_exits": self.enable_partial_exits,
                "breakeven_at_r": self.breakeven_threshold_r,
                "partial_at_r": self.partial_exit_threshold_r,
                "kk_style_partials": self.kk_style_partials,
                "partial_exit_days": self.partial_exit_days,
                "partial_exit_fraction": self.partial_exit_fraction,
                "eod_only_mode": self.eod_only_mode,
                "eod_window": f"{self.eod_window_start_hour}:{self.eod_window_start_minute:02d}-{self.eod_window_end_hour}:{self.eod_window_end_minute:02d} ET",
            },
            "partials_triggered": self.partials_triggered,
            "in_eod_window": self._is_in_eod_window() if self._running else None,
        }
    
    # =========================================================================
    # Streaming Mode Methods
    # =========================================================================
    
    async def _subscribe_to_positions(self):
        """Subscribe streaming client to all open position symbols."""
        if not self._streaming_client or not self._get_positions:
            return
        
        positions = await self._get_positions()
        symbols = [p.get("symbol") for p in positions if p.get("symbol")]
        
        if symbols:
            await self._streaming_client.subscribe(symbols)
            logger.info(f"Subscribed to positions: {symbols}")
    
    def _on_streaming_price_update(self, symbol: str, price: Decimal):
        """
        Handle real-time price update from streaming client.
        
        This is called synchronously from the streaming callback,
        so we schedule the async check.
        """
        import asyncio
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._check_position_for_symbol(symbol, price))
        except RuntimeError:
            # No running loop
            pass
    
    async def _check_position_for_symbol(self, symbol: str, current_price: Decimal):
        """Check a specific position when its price updates."""
        if not self._get_positions:
            return
        
        positions = await self._get_positions()
        
        # Find position for this symbol
        position = next((p for p in positions if p.get("symbol") == symbol), None)
        if not position:
            return
        
        self.last_check = now_utc()
        self.checks_run += 1
        
        try:
            # Check stop hit
            current_stop = Decimal(str(position.get("current_stop", 0)))
            entry_price = Decimal(str(position.get("entry_price", 0)))
            initial_stop = Decimal(str(position.get("initial_stop", 0)))
            shares = int(position.get("remaining_shares", 0))
            position_id = position.get("id", "")
            
            if shares <= 0:
                return
            
            # Stop-loss check (real-time)
            if current_price <= current_stop:
                pnl = (current_price - entry_price) * shares
                signal = ExitSignal(
                    position_id=position_id,
                    symbol=symbol,
                    reason=ExitReason.STOP_HIT,
                    exit_price=current_price,
                    shares_to_exit=shares,
                    pnl_estimate=pnl,
                )
                await self._handle_exit(signal)
                logger.warning(f"🛑 STOP HIT: {symbol} at ${current_price} (stop was ${current_stop})")
            
            # Trailing stop logic
            if self.enable_trailing_stops:
                risk_per_share = entry_price - initial_stop
                if risk_per_share > 0:
                    r_multiple = float((current_price - entry_price) / risk_per_share)
                    
                    # Move to breakeven at 1R
                    if r_multiple >= self.breakeven_threshold_r and current_stop < entry_price:
                        if self._update_stop:
                            await self._update_stop(position_id, entry_price)
                            logger.info(f"📈 {symbol}: Trailing stop moved to breakeven at {r_multiple:.1f}R")
        
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Error checking position {symbol}: {e}")

