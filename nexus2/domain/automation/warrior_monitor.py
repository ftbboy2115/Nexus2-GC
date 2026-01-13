"""
Warrior Position Monitor

Monitors Warrior Trading positions with Ross Cameron exit rules:
- Mental stops (10-20 cents)
- Character exits (candle-under-candle, topping tail)
- 2:1 R profit target partials
- Breakeven stop after partial

Separate from KK-style PositionMonitor - uses different exit logic.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Callable, Dict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


logger = logging.getLogger(__name__)

# Trade event logging
from nexus2.domain.automation.trade_event_service import trade_event_service


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class WarriorExitReason(Enum):
    """Reasons for exiting a Warrior position."""
    MENTAL_STOP = "mental_stop"  # 10-20 cents
    TECHNICAL_STOP = "technical_stop"  # Support level
    CANDLE_UNDER_CANDLE = "candle_under_candle"  # New low
    TOPPING_TAIL = "topping_tail"  # Rejection at highs
    PROFIT_TARGET = "profit_target"  # 2:1 R
    PARTIAL_EXIT = "partial_exit"  # 50% at target
    BREAKOUT_FAILURE = "breakout_failure"  # Failed to hold breakout
    TIME_STOP = "time_stop"  # No momentum after entry
    AFTER_HOURS_EXIT = "after_hours_exit"  # Forced exit before overnight hold
    SPREAD_EXIT = "spread_exit"  # Liquidity drying up - spread too wide
    MANUAL = "manual"


@dataclass
class WarriorExitSignal:
    """Signal to exit a Warrior position."""
    position_id: str
    symbol: str
    reason: WarriorExitReason
    exit_price: Decimal
    shares_to_exit: int
    pnl_estimate: Decimal
    stop_price: Decimal = Decimal("0")
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Analytics
    r_multiple: float = 0.0
    trigger_description: str = ""
    
    # Escalating exit - offset percent below bid (e.g., 0.02 = 2% below bid)
    exit_offset_percent: float = 0.01  # Default 1%



@dataclass
class WarriorMonitorSettings:
    """Settings for Warrior position monitoring."""
    # Mental Stop (primary stop)
    mental_stop_cents: Decimal = Decimal("15")  # Default 15 cents (10-20 range)
    use_technical_stop: bool = True  # Also use support levels
    technical_stop_buffer_cents: Decimal = Decimal("5")  # 2-5 cents below support
    
    # Profit Targets (Ross-style: can use fixed cents OR R-multiple)
    profit_target_cents: Decimal = Decimal("0")  # If > 0, use fixed cents (e.g., 20 = +20¢)
    profit_target_r: float = 2.0  # 2:1 R target (used if profit_target_cents = 0)
    partial_exit_fraction: float = 0.5  # Sell 50% at target
    move_stop_to_breakeven: bool = True  # After partial
    
    # Character Exit Patterns
    enable_candle_under_candle: bool = True
    enable_topping_tail: bool = True
    topping_tail_threshold: float = 0.6  # Wick > 60% of candle range
    
    # Time Stop (no momentum)
    enable_time_stop: bool = True
    time_stop_seconds: int = 120  # 2 minutes without momentum
    breakout_hold_threshold: float = 0.5  # Must hold 50% of breakout
    
    # After-Hours Exit (prevent overnight holds)
    enable_after_hours_exit: bool = True
    tighten_stop_time_et: str = "18:00"  # 6 PM ET - tighten stops to breakeven
    force_exit_time_et: str = "19:30"  # 7:30 PM ET - force exit all positions
    
    # Spread Exit (liquidity protection)
    enable_spread_exit: bool = True
    max_spread_percent: float = 3.0  # Exit if spread exceeds 3%
    spread_grace_period_seconds: int = 60  # Wait 60s after entry before checking spread
    
    # Polling
    check_interval_seconds: int = 2  # Fast polling for day trading


@dataclass
class WarriorPosition:
    """
    A Warrior Trading position being monitored.
    
    Contains entry details and intraday tracking.
    """
    position_id: str
    symbol: str
    entry_price: Decimal
    shares: int
    entry_time: datetime
    
    # Stops
    mental_stop: Decimal  # Entry - N cents
    technical_stop: Optional[Decimal] = None  # Support level
    current_stop: Decimal = Decimal("0")  # Active stop
    
    # Targets
    profit_target: Decimal = Decimal("0")  # 2:1 R price
    risk_per_share: Decimal = Decimal("0")  # Entry - stop
    
    # Tracking
    high_since_entry: Decimal = Decimal("0")  # For trailing
    partial_taken: bool = False
    
    # Intraday candle tracking (for pattern exits)
    last_candle_low: Decimal = Decimal("0")
    last_candle_high: Decimal = Decimal("0")
    candles_since_entry: int = 0


# =============================================================================
# WARRIOR MONITOR SERVICE
# =============================================================================

class WarriorMonitor:
    """
    Monitors Warrior Trading positions for exit conditions.
    
    Ross Cameron exit rules:
    1. Mental stop (10-20 cents) - no broker stop visible to HFT
    2. Technical stop (support - 2-5 cents)
    3. Candle-under-candle (new low)
    4. Topping tail (rejection at highs)
    5. 2:1 R profit target -> 50% partial, move stop to breakeven
    6. Breakout failure (didn't hold breakout level)
    """
    
    def __init__(self, settings: Optional[WarriorMonitorSettings] = None):
        self.settings = settings or WarriorMonitorSettings()
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Positions being monitored
        self._positions: Dict[str, WarriorPosition] = {}
        
        # Callbacks
        self._get_price: Optional[Callable] = None
        self._get_prices_batch: Optional[Callable] = None  # Batch quotes to reduce API calls
        self._get_quote_with_spread: Optional[Callable] = None  # For spread exit trigger
        self._get_intraday_candles: Optional[Callable] = None  # For pattern detection
        self._execute_exit: Optional[Callable] = None
        self._update_stop: Optional[Callable] = None
        self._get_broker_positions: Optional[Callable] = None  # For Alpaca sync
        self._record_symbol_fail: Optional[Callable] = None  # 2-strike rule callback
        
        # Sync tracking
        self._sync_counter = 0
        self._sync_interval = 5  # Sync every 5 checks (~10 seconds)
        
        # Stats
        self.checks_run = 0
        self.exits_triggered = 0
        self.partials_triggered = 0
        self.last_check: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        # Simulation mode flag - bypass time checks for Mock Market testing
        self.sim_mode: bool = False
        
        # P&L Tracking
        self.realized_pnl_today: Decimal = Decimal("0")
        self._pnl_date: Optional[datetime] = None  # Track date for reset
        
        # Recently exited tracking - prevents auto-recovery race conditions
        # Format: {symbol: exit_time}
        self._recently_exited: Dict[str, datetime] = {}
        self._recovery_cooldown_seconds = 120  # Don't auto-recover for 120s after exit (orders need time to fill)
        self._recently_exited_file = Path(__file__).parent.parent.parent.parent / "data" / "recently_exited.json"
        self._load_recently_exited()
        
        # Pending exit tracking - prevents duplicate exit orders
        # Format: {symbol: exit_submitted_at}
        self._pending_exits: Dict[str, datetime] = {}
        self._pending_exits_file = Path(__file__).parent.parent.parent.parent / "data" / "pending_exits.json"
        self._load_pending_exits()
    
    def _load_recently_exited(self):
        """Load recently exited symbols from disk (survives restarts)."""
        try:
            if self._recently_exited_file.exists():
                import json
                with open(self._recently_exited_file, "r") as f:
                    data = json.load(f)
                now = datetime.utcnow()
                # Only load entries less than 1 hour old (stale entries are useless)
                for symbol, ts_str in data.items():
                    exit_time = datetime.fromisoformat(ts_str)
                    if (now - exit_time).total_seconds() < 3600:  # 1 hour max
                        self._recently_exited[symbol] = exit_time
                if self._recently_exited:
                    logger.info(f"[Warrior] Loaded {len(self._recently_exited)} recently exited symbols from disk")
        except Exception as e:
            logger.warning(f"[Warrior] Failed to load recently exited: {e}")
    
    def _save_recently_exited(self):
        """Save recently exited symbols to disk."""
        try:
            import json
            # Convert datetime to ISO strings
            data = {symbol: dt.isoformat() for symbol, dt in self._recently_exited.items()}
            self._recently_exited_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._recently_exited_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[Warrior] Failed to save recently exited: {e}")
    
    def _load_pending_exits(self):
        """Load pending exits from disk (survives restarts)."""
        try:
            if self._pending_exits_file.exists():
                import json
                with open(self._pending_exits_file, "r") as f:
                    data = json.load(f)
                now = datetime.utcnow()
                # Only load entries less than 1 hour old (stale entries are cleared)
                for symbol, ts_str in data.items():
                    exit_time = datetime.fromisoformat(ts_str)
                    if (now - exit_time).total_seconds() < 3600:  # 1 hour max
                        self._pending_exits[symbol] = exit_time
                if self._pending_exits:
                    logger.info(f"[Warrior] Loaded {len(self._pending_exits)} pending exits from disk")
        except Exception as e:
            logger.warning(f"[Warrior] Failed to load pending exits: {e}")
    
    def _save_pending_exits(self):
        """Save pending exits to disk."""
        try:
            import json
            data = {symbol: dt.isoformat() for symbol, dt in self._pending_exits.items()}
            self._pending_exits_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._pending_exits_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[Warrior] Failed to save pending exits: {e}")
    
    def set_callbacks(
        self,
        get_price: Callable = None,
        get_prices_batch: Callable = None,
        get_quote_with_spread: Callable = None,
        get_intraday_candles: Callable = None,
        execute_exit: Callable = None,
        update_stop: Callable = None,
        get_broker_positions: Callable = None,
        record_symbol_fail: Callable = None,
    ):
        """Set callbacks for price data and execution.
        
        Only updates callbacks where a non-None value is provided.
        This preserves callbacks set by broker enable.
        """
        if get_price is not None:
            self._get_price = get_price
        if get_prices_batch is not None:
            self._get_prices_batch = get_prices_batch
        if get_quote_with_spread is not None:
            self._get_quote_with_spread = get_quote_with_spread
        if get_intraday_candles is not None:
            self._get_intraday_candles = get_intraday_candles
        if execute_exit is not None:
            self._execute_exit = execute_exit
        if update_stop is not None:
            self._update_stop = update_stop
        if get_broker_positions is not None:
            self._get_broker_positions = get_broker_positions
        if record_symbol_fail is not None:
            self._record_symbol_fail = record_symbol_fail
    
    # =========================================================================
    # POSITION MANAGEMENT
    # =========================================================================
    
    def add_position(
        self,
        position_id: str,
        symbol: str,
        entry_price: Decimal,
        shares: int,
        support_level: Optional[Decimal] = None,
    ) -> WarriorPosition:
        """
        Add a new position to monitor.
        
        Calculates stops and targets based on Ross Cameron rules.
        """
        s = self.settings
        
        # Mental stop: Entry - N cents
        mental_stop = entry_price - s.mental_stop_cents / 100
        
        # Technical stop: Support - buffer (if provided)
        technical_stop = None
        if support_level and s.use_technical_stop:
            technical_stop = support_level - s.technical_stop_buffer_cents / 100
        
        # Current stop: Use tighter of mental vs technical
        if technical_stop and technical_stop > mental_stop:
            current_stop = technical_stop  # Technical is tighter
        else:
            current_stop = mental_stop
        
        # Risk per share
        risk_per_share = entry_price - current_stop
        
        # Profit target: Either fixed cents OR R-based
        if s.profit_target_cents > 0:
            # Fixed cents target (Ross-style: 15-20 cents)
            profit_target = entry_price + s.profit_target_cents / 100
        else:
            # R-based target (default 2:1)
            profit_target = entry_price + (risk_per_share * Decimal(str(s.profit_target_r)))
        
        position = WarriorPosition(
            position_id=position_id,
            symbol=symbol,
            entry_price=entry_price,
            shares=shares,
            entry_time=datetime.utcnow(),
            mental_stop=mental_stop,
            technical_stop=technical_stop,
            current_stop=current_stop,
            profit_target=profit_target,
            risk_per_share=risk_per_share,
            high_since_entry=entry_price,
        )
        
        self._positions[position_id] = position
        
        # Log entry event
        trade_event_service.log_warrior_entry(
            position_id=position_id,
            symbol=symbol,
            entry_price=entry_price,
            stop_price=current_stop,
            shares=shares,
            trigger_type="ORB",  # Default, can be overridden by caller
        )
        
        logger.info(
            f"[Warrior] Added {symbol}: entry=${entry_price}, "
            f"stop=${current_stop}, target=${profit_target}"
        )
        
        return position
    
    def remove_position(self, position_id: str) -> bool:
        """Remove a position from monitoring."""
        if position_id in self._positions:
            del self._positions[position_id]
            return True
        return False
    
    def get_positions(self) -> List[WarriorPosition]:
        """Get all monitored positions."""
        return list(self._positions.values())
    
    # =========================================================================
    # MONITORING LOOP
    # =========================================================================
    
    async def start(self) -> dict:
        """Start monitoring positions."""
        if self._running:
            return {"status": "already_running"}
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        
        logger.info(f"[Warrior Monitor] Started (interval: {self.settings.check_interval_seconds}s)")
        return {"status": "started", "interval": self.settings.check_interval_seconds}
    
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
        
        logger.info("[Warrior Monitor] Stopped")
        return {"status": "stopped"}
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                # Skip on non-market days (weekends, holidays) and outside extended hours
                # BUT: bypass in sim_mode for Mock Market testing anytime
                if not self.sim_mode:
                    from nexus2.adapters.market_data.market_calendar import get_market_calendar
                    calendar = get_market_calendar(paper=True)
                    if not calendar.is_extended_hours_active():
                        logger.debug("[Warrior Monitor] Outside extended hours (4 AM - 8 PM) - skipping position check")
                        await asyncio.sleep(60)  # Check again in 1 minute
                        continue
                
                await self._check_all_positions()
                await asyncio.sleep(self.settings.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"[Warrior Monitor] Error: {e}")
                await asyncio.sleep(5)
    
    async def _check_all_positions(self):
        """Check all positions for exit conditions."""
        self.last_check = datetime.utcnow()
        self.checks_run += 1
        
        # Periodic sync with broker (every N checks)
        self._sync_counter += 1
        if self._sync_counter >= self._sync_interval:
            self._sync_counter = 0
            await self._sync_with_broker()
        
        if not self._positions:
            return
        
        # Fetch all prices in ONE batch call to reduce API rate limits
        symbols = [p.symbol for p in self._positions.values()]
        prices = {}
        
        if self._get_prices_batch:
            try:
                prices = await self._get_prices_batch(symbols)
            except Exception as e:
                logger.error(f"[Warrior] Batch quote failed: {e}")
        
        for position_id, position in list(self._positions.items()):
            try:
                # Skip positions with pending exit orders (prevents duplicate exits)
                if position.symbol in self._pending_exits:
                    continue
                
                # Pass pre-fetched price to avoid individual API calls
                current_price = prices.get(position.symbol)
                signal = await self._evaluate_position(position, current_price)
                if signal:
                    await self._handle_exit(signal)
            except Exception as e:
                logger.error(f"[Warrior] Error checking {position.symbol}: {e}")
    
    async def _sync_with_broker(self):
        """Sync monitor state with Alpaca broker positions.
        
        Fixes state drift where:
        - Partial orders submitted but not filled
        - Positions closed manually at broker
        - Shares differ between monitor and broker
        """
        if not self._get_broker_positions:
            return
        
        try:
            broker_positions = await self._get_broker_positions()
            
            # Skip sync if broker returned error (None)
            if broker_positions is None:
                logger.warning("[Warrior Sync] Skipping sync - broker returned error")
                return
            
            # Build lookup: symbol -> broker qty
            broker_map = {}
            for pos in broker_positions:
                # Handle both dict and object types
                if isinstance(pos, dict):
                    symbol = pos.get("symbol")
                    qty = int(pos.get("qty", 0))
                else:
                    symbol = pos.symbol
                    qty = int(pos.qty)
                broker_map[symbol] = qty
            
            # Sync each monitored position
            for position_id, position in list(self._positions.items()):
                symbol = position.symbol
                broker_qty = broker_map.get(symbol, 0)
                
                if broker_qty == 0:
                    # Position closed at broker - remove from monitor
                    logger.warning(
                        f"[Warrior Sync] {symbol}: Broker has 0 shares, removing from monitor"
                    )
                    self.remove_position(position_id)
                elif broker_qty != position.shares:
                    # Shares mismatch - update monitor to match broker
                    old_shares = position.shares
                    position.shares = broker_qty
                    
                    # If broker has fewer shares, partial was taken
                    if broker_qty < old_shares:
                        position.partial_taken = True
                    
                    logger.info(
                        f"[Warrior Sync] {symbol}: Updated shares {old_shares} -> {broker_qty}"
                    )
            
            # Check for broker positions not in monitor (orphaned at broker)
            # Auto-recover these by adding them back to monitor
            monitored_symbols = {p.symbol for p in self._positions.values()}
            now = datetime.utcnow()
            
            # Clean up old entries from recently exited
            expired = [s for s, t in self._recently_exited.items() 
                       if (now - t).total_seconds() > self._recovery_cooldown_seconds]
            for s in expired:
                del self._recently_exited[s]
            
            for symbol, qty in broker_map.items():
                if symbol not in monitored_symbols and qty > 0:
                    # Skip if pending exit (prevents re-adding position we're trying to close)
                    if symbol in self._pending_exits:
                        logger.debug(f"[Warrior Sync] {symbol}: Skipping recovery (pending exit)")
                        continue
                    # Skip if recently exited (prevent race condition with pending sell orders)
                    if symbol in self._recently_exited:
                        exit_time = self._recently_exited[symbol]
                        secs_ago = (now - exit_time).total_seconds()
                        logger.debug(f"[Warrior Sync] {symbol}: Skipping recovery (exited {secs_ago:.0f}s ago)")
                        continue
                    # Find the broker position data to get entry price
                    broker_pos = None
                    for pos in broker_positions:
                        pos_symbol = pos.get("symbol") if isinstance(pos, dict) else getattr(pos, "symbol", None)
                        if pos_symbol == symbol:
                            broker_pos = pos
                            break
                    
                    # Get entry price from broker or estimate from current
                    if isinstance(broker_pos, dict):
                        entry_price = Decimal(str(broker_pos.get("avg_price", 0)))
                    else:
                        entry_price = Decimal(str(getattr(broker_pos, "avg_price", 0)))
                    
                    if entry_price > 0:
                        # Auto-recover: Add position back to monitor
                        from uuid import uuid4
                        stop_price = entry_price - self.settings.mental_stop_cents / 100
                        profit_target_r = Decimal(str(self.settings.profit_target_r))
                        target_price = entry_price + (self.settings.mental_stop_cents / 100 * profit_target_r)
                        
                        position = WarriorPosition(
                            position_id=str(uuid4()),
                            symbol=symbol,
                            entry_price=entry_price,
                            shares=qty,
                            entry_time=datetime.utcnow(),
                            current_stop=stop_price,
                            profit_target=target_price,
                            mental_stop=stop_price,
                            technical_stop=None,
                        )
                        self._positions[position.position_id] = position
                        logger.info(
                            f"[Warrior Sync] {symbol}: Auto-recovered from broker ({qty} shares @ ${entry_price:.2f})"
                        )
                    else:
                        logger.warning(
                            f"[Warrior Sync] {symbol}: Found at broker ({qty} shares) but cannot recover - no entry price"
                        )
            
            # Confirm pending exits that are now fully closed at broker
            for symbol in list(self._pending_exits.keys()):
                if broker_map.get(symbol, 0) == 0:
                    # Position gone from broker = exit confirmed
                    del self._pending_exits[symbol]
                    self._save_pending_exits()
                    logger.info(f"[Warrior Sync] {symbol}: Exit confirmed by broker")
        except Exception as e:
            logger.error(f"[Warrior Sync] Error syncing with broker: {e}")
    
    # =========================================================================
    # EXIT EVALUATION (Ross Cameron Rules)
    # =========================================================================
    
    async def _evaluate_position(
        self, 
        position: WarriorPosition,
        prefetched_price: Optional[float] = None,
    ) -> Optional[WarriorExitSignal]:
        """
        Evaluate position for exit conditions.
        
        Checks (in order of priority):
        1. Stop hit (mental or technical)
        2. Candle-under-candle pattern
        3. Topping tail rejection
        4. Profit target reached
        
        Args:
            position: The position to evaluate
            prefetched_price: Pre-fetched price from batch quote (avoids individual API call)
        """
        # Use pre-fetched price if available, otherwise fall back to individual call
        # Note: price=0 is treated as invalid (impossible for real tradeable stocks)
        if prefetched_price is not None and prefetched_price != 0:
            current_price = Decimal(str(prefetched_price))
        elif self._get_price:
            price = await self._get_price(position.symbol)
            
            # If Alpaca fails, try FMP as backup source
            if price is None or price == 0:
                logger.info(f"[Warrior] {position.symbol}: Alpaca quote failed, trying FMP fallback...")
                try:
                    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
                    fmp = get_fmp_adapter()
                    fmp_quote = fmp.get_quote(position.symbol)
                    if fmp_quote and fmp_quote.price and fmp_quote.price > 0:
                        price = float(fmp_quote.price)
                        logger.info(f"[Warrior] {position.symbol}: FMP fallback successful, price=${price}")
                except Exception as e:
                    logger.warning(f"[Warrior] {position.symbol}: FMP fallback failed: {e}")
            
            # If still no valid price after fallback
            if price is None or price == 0:
                logger.warning(
                    f"[Warrior] {position.symbol}: All quote sources failed (price={price})! "
                    f"STOP CHECK SKIPPED (stop=${position.current_stop})"
                )
                return None
            current_price = Decimal(str(price))
        else:
            logger.error(f"[Warrior] {position.symbol}: No price callback configured!")
            return None
        
        s = self.settings
        
        # Update high since entry
        if current_price > position.high_since_entry:
            position.high_since_entry = current_price
        
        # Calculate current R
        if position.risk_per_share > 0:
            current_gain = current_price - position.entry_price
            r_multiple = float(current_gain / position.risk_per_share)
        else:
            r_multiple = 0.0
        
        # =====================================================================
        # CHECK 0: After-Hours Exit (prevent overnight holds)
        # =====================================================================
        if s.enable_after_hours_exit:
            from zoneinfo import ZoneInfo
            et_now = datetime.now(ZoneInfo("America/New_York"))
            current_time_str = et_now.strftime("%H:%M")
            
            # Force exit at 7:30 PM ET with ESCALATING offset
            # Every 2 minutes, increase offset by 2% to ensure fill before 8 PM
            if current_time_str >= s.force_exit_time_et:
                pnl = (current_price - position.entry_price) * position.shares
                
                # Parse force_exit_time to calculate minutes elapsed
                force_hour, force_min = map(int, s.force_exit_time_et.split(":"))
                force_exit_dt = et_now.replace(hour=force_hour, minute=force_min, second=0, microsecond=0)
                minutes_since_force = (et_now - force_exit_dt).total_seconds() / 60
                
                # Escalating offset: 2% base, +2% every 2 minutes, max 10%
                # 0-2 min: 2%, 2-4 min: 4%, 4-6 min: 6%, 6-8 min: 8%, 8+ min: 10%
                offset_tier = min(int(minutes_since_force / 2), 4)  # 0-4 tiers
                exit_offset = 0.02 + (offset_tier * 0.02)  # 2% to 10%
                
                logger.warning(
                    f"[Warrior] {position.symbol}: AFTER-HOURS EXIT at ${current_price} "
                    f"(offset={exit_offset*100:.0f}%, {minutes_since_force:.1f}min since {s.force_exit_time_et} ET)"
                )
                return WarriorExitSignal(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    reason=WarriorExitReason.AFTER_HOURS_EXIT,
                    exit_price=current_price,
                    shares_to_exit=position.shares,
                    pnl_estimate=pnl,
                    stop_price=position.current_stop,
                    r_multiple=r_multiple,
                    trigger_description=f"Force exit at {s.force_exit_time_et} ET (offset={exit_offset*100:.0f}%)",
                    exit_offset_percent=exit_offset,  # Pass offset to executor
                )
            
            # Tighten stop to breakeven at 6 PM ET (if profitable)
            if current_time_str >= s.tighten_stop_time_et:
                if current_price > position.entry_price and position.current_stop < position.entry_price:
                    old_stop = position.current_stop
                    position.current_stop = position.entry_price
                    logger.info(
                        f"[Warrior] {position.symbol}: After-hours stop tightened to breakeven "
                        f"${position.current_stop} (was ${old_stop})"
                    )
        
        # =====================================================================
        # CHECK 0.5: Spread Exit (liquidity protection)
        # =====================================================================
        if s.enable_spread_exit:
            # Only check spread after grace period (avoid exit on volatile open)
            seconds_since_entry = (datetime.utcnow() - position.entry_time).total_seconds()
            if seconds_since_entry >= s.spread_grace_period_seconds:
                # Get bid/ask spread from quote callback if available
                if self._get_quote_with_spread:
                    try:
                        spread_data = await self._get_quote_with_spread(position.symbol)
                        if spread_data:
                            liquidity_status = spread_data.get("liquidity_status", "unknown")
                            spread_pct = spread_data.get("spread_percent")
                            bid = spread_data.get("bid", 0)
                            ask = spread_data.get("ask", 0)
                            
                            # Log based on liquidity status
                            if liquidity_status == "ok" and spread_pct is not None:
                                # Normal case - valid bid/ask
                                logger.info(
                                    f"[Warrior] {position.symbol}: Spread {spread_pct:.1f}% "
                                    f"(max={s.max_spread_percent}%, bid=${bid:.2f}, ask=${ask:.2f})"
                                )
                                
                                if spread_pct > s.max_spread_percent:
                                    pnl = (current_price - position.entry_price) * position.shares
                                    logger.warning(
                                        f"[Warrior] {position.symbol}: SPREAD EXIT - spread {spread_pct:.1f}% "
                                        f"(max={s.max_spread_percent}%, bid=${bid}, ask=${ask})"
                                    )
                                    return WarriorExitSignal(
                                        position_id=position.position_id,
                                        symbol=position.symbol,
                                        reason=WarriorExitReason.SPREAD_EXIT,
                                        exit_price=current_price,
                                        shares_to_exit=position.shares,
                                        pnl_estimate=pnl,
                                        stop_price=position.current_stop,
                                        r_multiple=r_multiple,
                                        trigger_description=f"Spread {spread_pct:.1f}% > max {s.max_spread_percent}%",
                                    )
                            elif liquidity_status == "no_ask_liquidity":
                                # No sellers - can't calculate spread, log warning
                                logger.debug(
                                    f"[Warrior] {position.symbol}: No ask liquidity (bid=${bid:.2f}, ask=N/A) - spread check skipped"
                                )
                            elif liquidity_status == "no_bid_liquidity":
                                # No buyers - bearish, log warning
                                logger.warning(
                                    f"[Warrior] {position.symbol}: No bid liquidity (bid=N/A, ask=${ask:.2f}) - caution!"
                                )
                            else:
                                # No quote at all
                                logger.debug(
                                    f"[Warrior] {position.symbol}: No quote data available for spread check"
                                )
                    except Exception as e:
                        logger.debug(f"[Warrior] {position.symbol}: Spread check failed: {e}")
        
        # =====================================================================
        # CHECK 1: Stop Hit (Mental or Technical)
        # =====================================================================
        if current_price <= position.current_stop:
            pnl = (current_price - position.entry_price) * position.shares
            logger.warning(
                f"[Warrior] {position.symbol}: STOP HIT at ${current_price} "
                f"(stop was ${position.current_stop})"
            )
            return WarriorExitSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                reason=WarriorExitReason.MENTAL_STOP,
                exit_price=current_price,
                shares_to_exit=position.shares,
                pnl_estimate=pnl,
                stop_price=position.current_stop,
                r_multiple=r_multiple,
                trigger_description=f"Price ${current_price} <= stop ${position.current_stop}",
            )
        
        # =====================================================================
        # CHECK 2: Candle-Under-Candle (New Low)
        # =====================================================================
        if s.enable_candle_under_candle and self._get_intraday_candles:
            candles = await self._get_intraday_candles(position.symbol, timeframe="1min", limit=3)
            if candles and len(candles) >= 2:
                current_candle = candles[-1]
                prev_candle = candles[-2]
                
                # New low = current low < previous low
                if current_candle.low < prev_candle.low:
                    # Also confirm it's red (close < open)
                    if current_candle.close < current_candle.open:
                        pnl = (current_price - position.entry_price) * position.shares
                        logger.info(
                            f"[Warrior] {position.symbol}: Candle-under-candle detected"
                        )
                        return WarriorExitSignal(
                            position_id=position.position_id,
                            symbol=position.symbol,
                            reason=WarriorExitReason.CANDLE_UNDER_CANDLE,
                            exit_price=current_price,
                            shares_to_exit=position.shares,
                            pnl_estimate=pnl,
                            r_multiple=r_multiple,
                            trigger_description="New candle low (character exit)",
                        )
        
        # =====================================================================
        # CHECK 3: Topping Tail (Rejection at Highs)
        # =====================================================================
        if s.enable_topping_tail and self._get_intraday_candles:
            candles = await self._get_intraday_candles(position.symbol, timeframe="1min", limit=2)
            if candles:
                current_candle = candles[-1]
                candle_range = current_candle.high - current_candle.low
                
                if candle_range > 0:
                    # Upper wick = high - max(open, close)
                    body_top = max(current_candle.open, current_candle.close)
                    upper_wick = current_candle.high - body_top
                    wick_ratio = float(upper_wick / candle_range)
                    
                    # Topping tail: wick > 60% of range, at/near highs
                    is_near_high = current_candle.high >= position.high_since_entry * Decimal("0.995")
                    
                    if wick_ratio >= s.topping_tail_threshold and is_near_high:
                        pnl = (current_price - position.entry_price) * position.shares
                        logger.info(
                            f"[Warrior] {position.symbol}: Topping tail detected "
                            f"(wick {wick_ratio*100:.0f}%)"
                        )
                        return WarriorExitSignal(
                            position_id=position.position_id,
                            symbol=position.symbol,
                            reason=WarriorExitReason.TOPPING_TAIL,
                            exit_price=current_price,
                            shares_to_exit=position.shares,
                            pnl_estimate=pnl,
                            r_multiple=r_multiple,
                            trigger_description=f"Topping tail ({wick_ratio*100:.0f}% wick)",
                        )
        
        # =====================================================================
        # CHECK 4: Profit Target (2:1 R) -> Partial Exit
        # =====================================================================
        if not position.partial_taken and current_price >= position.profit_target:
            shares_to_exit = int(position.shares * s.partial_exit_fraction)
            if shares_to_exit >= 1:
                pnl = (current_price - position.entry_price) * shares_to_exit
                logger.info(
                    f"[Warrior] {position.symbol}: Profit target hit at {r_multiple:.1f}R "
                    f"-> Partial exit ({shares_to_exit} shares)"
                )
                
                # Mark partial taken
                position.partial_taken = True
                position.shares -= shares_to_exit
                
                # Move stop to breakeven
                if s.move_stop_to_breakeven:
                    position.current_stop = position.entry_price
                    if self._update_stop:
                        await self._update_stop(position.position_id, position.entry_price)
                    # Log breakeven event
                    trade_event_service.log_warrior_breakeven(
                        position_id=position.position_id,
                        symbol=position.symbol,
                        entry_price=position.entry_price,
                    )
                    logger.info(f"[Warrior] {position.symbol}: Stop moved to breakeven")
                
                self.partials_triggered += 1
                
                # Determine target description
                if self.settings.profit_target_cents > 0:
                    target_desc = f"Fixed +{self.settings.profit_target_cents}¢ target hit"
                else:
                    target_desc = f"{self.settings.profit_target_r}:1 R target hit (${position.profit_target})"
                
                return WarriorExitSignal(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    reason=WarriorExitReason.PARTIAL_EXIT,
                    exit_price=current_price,
                    shares_to_exit=shares_to_exit,
                    pnl_estimate=pnl,
                    r_multiple=r_multiple,
                    trigger_description=target_desc,
                )
        
        return None
    
    async def _handle_exit(self, signal: WarriorExitSignal):
        """Handle an exit signal."""
        logger.info(
            f"[Warrior] Exit: {signal.symbol} - {signal.reason.value} - "
            f"{signal.shares_to_exit} shares (P&L: ${signal.pnl_estimate:.2f})"
        )
        
        order_success = False
        
        # Mark pending exit BEFORE submitting order (prevents duplicate exit signals)
        if signal.reason != WarriorExitReason.PARTIAL_EXIT:
            self._pending_exits[signal.symbol] = datetime.utcnow()
            self._save_pending_exits()
            logger.info(f"[Warrior] {signal.symbol}: Marked pending exit")
        
        if self._execute_exit:
            try:
                # execute_exit returns {"order": order, "actual_exit_price": float} or None
                result = await self._execute_exit(signal)
                self.exits_triggered += 1
                order_success = True
                
                # Get actual exit price from broker execution (more accurate than signal estimate)
                if result and isinstance(result, dict) and "actual_exit_price" in result:
                    actual_exit_price = Decimal(str(result["actual_exit_price"]))
                    # Recalculate P&L with actual exit price
                    position = self._positions.get(signal.position_id)
                    if position:
                        actual_pnl = (actual_exit_price - position.entry_price) * signal.shares_to_exit
                    else:
                        actual_pnl = signal.pnl_estimate  # Fallback
                else:
                    # Fallback to signal values if no actual price returned
                    actual_exit_price = signal.exit_price
                    actual_pnl = signal.pnl_estimate
                
                # Log trade event with actual values
                exit_reason_map = {
                    WarriorExitReason.MENTAL_STOP: "mental_stop",
                    WarriorExitReason.TECHNICAL_STOP: "technical_stop",
                    WarriorExitReason.CANDLE_UNDER_CANDLE: "candle_under_candle",
                    WarriorExitReason.TOPPING_TAIL: "topping_tail",
                    WarriorExitReason.TIME_STOP: "time_stop",
                    WarriorExitReason.AFTER_HOURS_EXIT: "after_hours_exit",
                    WarriorExitReason.BREAKOUT_FAILURE: "breakout_failure",
                }
                
                if signal.reason == WarriorExitReason.PARTIAL_EXIT:
                    trade_event_service.log_warrior_partial_exit(
                        position_id=signal.position_id,
                        symbol=signal.symbol,
                        shares_sold=signal.shares_to_exit,
                        exit_price=actual_exit_price,
                        pnl=actual_pnl,
                        r_multiple=signal.r_multiple,
                    )
                else:
                    trade_event_service.log_warrior_exit(
                        position_id=signal.position_id,
                        symbol=signal.symbol,
                        exit_price=actual_exit_price,
                        exit_reason=exit_reason_map.get(signal.reason, "manual"),
                        pnl=actual_pnl,
                    )
                
                # Track realized P&L with actual value
                self._add_realized_pnl(actual_pnl)
                    
            except Exception as e:
                logger.error(f"[Warrior] Exit execution failed: {e}")
                self.last_error = str(e)
        else:
            logger.warning("[Warrior] No execute_exit callback - signal not acted on")
        
        # CRITICAL: Always remove position on FULL exit, even if order fails!
        # This prevents infinite loop when Alpaca rejects (wash trade, etc.)
        # The position will remain on Alpaca and need manual close.
        if signal.reason != WarriorExitReason.PARTIAL_EXIT:
            # Track as recently exited to prevent auto-recovery race
            self._recently_exited[signal.symbol] = datetime.utcnow()
            self._save_recently_exited()  # Persist to disk for restart survival
            
            # 2-Strike Rule: only count if order was successful
            if order_success:
                stop_reasons = {
                    WarriorExitReason.MENTAL_STOP,
                    WarriorExitReason.TECHNICAL_STOP,
                    WarriorExitReason.BREAKOUT_FAILURE,
                }
                if signal.reason in stop_reasons and self._record_symbol_fail:
                    self._record_symbol_fail(signal.symbol)
            
            self.remove_position(signal.position_id)
            logger.info(f"[Warrior] {signal.symbol}: Removed from monitor (order_success={order_success})")
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def _add_realized_pnl(self, pnl: Decimal):
        """Add to realized P&L, resetting if new day."""
        today = datetime.utcnow().date()
        if self._pnl_date != today:
            self.realized_pnl_today = Decimal("0")
            self._pnl_date = today
        self.realized_pnl_today += pnl
    
    def reset_daily_pnl(self):
        """Manually reset daily P&L tracking."""
        self.realized_pnl_today = Decimal("0")
        self._pnl_date = datetime.utcnow().date()
    
    def get_status(self) -> dict:
        """Get monitor status."""
        return {
            "running": self._running,
            "positions_count": len(self._positions),
            "check_interval_seconds": self.settings.check_interval_seconds,
            "checks_run": self.checks_run,
            "exits_triggered": self.exits_triggered,
            "partials_triggered": self.partials_triggered,
            "realized_pnl_today": float(self.realized_pnl_today),
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_error": self.last_error,
            "settings": {
                "mental_stop_cents": float(self.settings.mental_stop_cents),
                "profit_target_cents": float(self.settings.profit_target_cents),
                "profit_target_r": self.settings.profit_target_r,
                "partial_exit_fraction": self.settings.partial_exit_fraction,
                "candle_under_candle": self.settings.enable_candle_under_candle,
                "topping_tail": self.settings.enable_topping_tail,
            },
        }


# =============================================================================
# SINGLETON
# =============================================================================

_warrior_monitor: Optional[WarriorMonitor] = None


def get_warrior_monitor() -> WarriorMonitor:
    """Get singleton Warrior monitor."""
    global _warrior_monitor
    if _warrior_monitor is None:
        _warrior_monitor = WarriorMonitor()
    return _warrior_monitor
