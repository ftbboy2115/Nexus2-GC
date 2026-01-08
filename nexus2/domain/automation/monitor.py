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


logger = logging.getLogger(__name__)


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
            self.generated_at = datetime.utcnow()


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
                await self._check_positions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(30)  # Wait before retry
    
    async def _check_positions(self):
        """Check all open positions for exit conditions."""
        self.last_check = datetime.utcnow()
        self.checks_run += 1
        
        if not self._get_positions:
            logger.warning("No get_positions callback")
            return
        
        positions = await self._get_positions()
        if not positions:
            return
        
        logger.debug(f"Checking {len(positions)} positions")
        
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
        if self.enable_trailing_stops and r_multiple >= self.breakeven_threshold_r:
            if current_stop < entry_price:
                # Update stop to breakeven (handled separately, not an exit)
                logger.info(f"{symbol}: Moving stop to breakeven at {r_multiple:.1f}R")
                if self._update_stop:
                    await self._update_stop(position_id, entry_price)
        
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
            days_held = (datetime.now(opened_at.tzinfo) - opened_at).days if opened_at.tzinfo else (datetime.now() - opened_at).days
            
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
        
        if self._execute_exit:
            try:
                await self._execute_exit(signal)
                self.exits_triggered += 1
                
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
            },
            "partials_triggered": self.partials_triggered,
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
        
        self.last_check = datetime.utcnow()
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

