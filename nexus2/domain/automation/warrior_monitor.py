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
from pathlib import Path
from nexus2.utils.time_utils import now_utc, now_et

# Import types from warrior_types module
from nexus2.domain.automation.warrior_types import (
    WarriorExitReason,
    WarriorExitSignal,
    WarriorMonitorSettings,
    WarriorPosition,
)


logger = logging.getLogger(__name__)

# Trade event logging
from nexus2.domain.automation.trade_event_service import trade_event_service


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
        self._submit_scale_order: Optional[Callable] = None  # Scaling order callback
        self._get_order_status: Optional[Callable] = None  # For exit order confirmation
        
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
        
        # NOTE: Pending exit tracking now uses DB status (PENDING_EXIT) instead of in-memory dict
        # See: _is_pending_exit(), _mark_pending_exit(), _clear_pending_exit()
    
    def _load_recently_exited(self):
        """Load recently exited symbols from disk (survives restarts)."""
        try:
            if self._recently_exited_file.exists():
                import json
                from datetime import timezone
                with open(self._recently_exited_file, "r") as f:
                    data = json.load(f)
                now = now_utc()
                # Only load entries less than 1 hour old (stale entries are useless)
                for symbol, ts_str in data.items():
                    # Handle both 'Z' suffix and naive datetimes
                    exit_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    # Ensure timezone-aware (assume UTC if naive)
                    if exit_time.tzinfo is None:
                        exit_time = exit_time.replace(tzinfo=timezone.utc)
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
    
    # =========================================================================
    # PENDING EXIT TRACKING (PSM-based - single source of truth in DB)
    # =========================================================================
    
    def _is_pending_exit(self, symbol: str) -> bool:
        """Check if symbol has a pending exit order (DB status = PENDING_EXIT)."""
        try:
            from nexus2.db.warrior_db import get_warrior_trade_by_symbol
            from nexus2.domain.positions.position_state_machine import PositionStatus
            trade = get_warrior_trade_by_symbol(symbol)
            if trade and trade["status"] == PositionStatus.PENDING_EXIT.value:
                return True
            return False
        except Exception as e:
            logger.warning(f"[Warrior] Error checking pending exit for {symbol}: {e}")
            return False
    
    def _mark_pending_exit(self, symbol: str) -> bool:
        """Mark symbol as pending exit (update DB status to PENDING_EXIT)."""
        try:
            from nexus2.db.warrior_db import get_warrior_trade_by_symbol, update_warrior_status
            from nexus2.domain.positions.position_state_machine import PositionStatus
            trade = get_warrior_trade_by_symbol(symbol)
            if trade:
                update_warrior_status(trade["id"], PositionStatus.PENDING_EXIT.value)
                logger.info(f"[Warrior] {symbol}: Marked PENDING_EXIT in DB")
                return True
            return False
        except Exception as e:
            logger.warning(f"[Warrior] Failed to mark pending exit for {symbol}: {e}")
            return False
    
    def _clear_pending_exit(self, symbol: str, to_closed: bool = True) -> bool:
        """Clear pending exit status (transition to CLOSED or OPEN)."""
        try:
            from nexus2.db.warrior_db import get_warrior_trade_by_symbol, update_warrior_status
            from nexus2.domain.positions.position_state_machine import PositionStatus
            trade = get_warrior_trade_by_symbol(symbol)
            if trade and trade["status"] == PositionStatus.PENDING_EXIT.value:
                new_status = PositionStatus.CLOSED.value if to_closed else PositionStatus.OPEN.value
                update_warrior_status(trade["id"], new_status)
                logger.info(f"[Warrior] {symbol}: {PositionStatus.PENDING_EXIT.value} → {new_status}")
                return True
            return False
        except Exception as e:
            logger.warning(f"[Warrior] Failed to clear pending exit for {symbol}: {e}")
            return False
    
    def _get_pending_exit_symbols(self) -> set:
        """Get all symbols with PENDING_EXIT status."""
        try:
            from nexus2.db.warrior_db import get_warrior_trades_by_status
            from nexus2.domain.positions.position_state_machine import PositionStatus
            trades = get_warrior_trades_by_status(PositionStatus.PENDING_EXIT.value)
            return {t["symbol"] for t in trades}
        except Exception as e:
            logger.warning(f"[Warrior] Failed to get pending exits: {e}")
            return set()
    
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
        submit_scale_order: Callable = None,
        get_order_status: Callable = None,
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
        if submit_scale_order is not None:
            self._submit_scale_order = submit_scale_order
        if get_order_status is not None:
            self._get_order_status = get_order_status
    
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
        trigger_type: str = "ORB",  # PMH_BREAK, ORB, or synced
    ) -> WarriorPosition:
        """
        Add a new position to monitor.
        
        Calculates stops and targets based on Ross Cameron rules.
        """
        s = self.settings
        
        # Clear any pending_exit status for this symbol from previous positions
        # This prevents the new position from being skipped in monitor tick
        if self._is_pending_exit(symbol):
            self._clear_pending_exit(symbol, to_closed=True)
            logger.info(f"[Warrior] {symbol}: Cleared stale pending_exit for new position")
        
        # Mental stop: Entry - N cents (FALLBACK only - used when no candle data)
        mental_stop = entry_price - s.mental_stop_cents / 100
        
        # Technical stop: Support/ORB low - buffer (Ross's actual method: low of entry candle)
        technical_stop = None
        if support_level and s.use_technical_stop:
            technical_stop = support_level - s.technical_stop_buffer_cents / 100
        
        # Current stop: Use CANDLE LOW (technical) as PRIMARY, mental only as FALLBACK
        # Ross's rule: "Max loss per trade = Low of entry candle"
        # NOT "tighter of two" - that causes too many stop-outs
        if technical_stop and s.use_candle_low_stop:
            current_stop = technical_stop  # Ross's actual method
        else:
            current_stop = mental_stop  # Fallback when no candle data
        
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
            entry_time=now_utc(),
            mental_stop=mental_stop,
            technical_stop=technical_stop,
            current_stop=current_stop,
            profit_target=profit_target,
            risk_per_share=risk_per_share,
            high_since_entry=entry_price,
            original_shares=shares,  # Track for scaling calculations
        )
        
        self._positions[position_id] = position
        
        # Log entry event
        trade_event_service.log_warrior_entry(
            position_id=position_id,
            symbol=symbol,
            entry_price=entry_price,
            stop_price=current_stop,
            shares=shares,
            trigger_type=trigger_type,
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
                        status = calendar.get_market_status()
                        reason = status.reason or "off_hours"
                        next_open = status.next_open.strftime('%Y-%m-%d %H:%M ET') if status.next_open else 'unknown'
                        logger.info(f"[Warrior Monitor] Market closed ({reason}) - next open: {next_open}")
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
        self.last_check = now_utc()
        self.checks_run += 1
        
        # Periodic sync with broker (every N checks) - SKIP in sim_mode
        # Sync checks live Alpaca broker which has 0 shares during replay
        if not self.sim_mode:
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
                if self._is_pending_exit(position.symbol):
                    continue
                
                # Pass pre-fetched price to avoid individual API calls
                current_price = prices.get(position.symbol)
                signal = await self._evaluate_position(position, current_price)
                if signal:
                    await self._handle_exit(signal)
                else:
                    # No exit signal - check for scaling opportunity
                    # Skip scaling entirely during closed markets (reduces log spam)
                    should_check_scale = current_price and self.settings.enable_scaling
                    if should_check_scale and not self.sim_mode:
                        from nexus2.adapters.market_data.market_calendar import get_market_calendar
                        calendar = get_market_calendar(paper=True)
                        status = calendar.get_market_status()
                        if not status.is_open:
                            should_check_scale = False  # Don't check during holidays/weekends
                    
                    if should_check_scale:
                        scale_signal = await self._check_scale_opportunity(
                            position, Decimal(str(current_price))
                        )
                        if scale_signal:
                            # Execute scale-in order
                            await self._execute_scale_in(position, scale_signal)
            except Exception as e:
                logger.error(f"[Warrior] Error checking {position.symbol}: {e}")
    
    async def _sync_with_broker(self):
        """Sync monitor state with Alpaca broker positions.
        
        Fixes state drift where:
        - Partial orders submitted but not filled
        - Positions closed manually at broker
        - Shares differ between monitor and broker
        
        Delegated to warrior_monitor_sync module for maintainability.
        """
        from nexus2.domain.automation.warrior_monitor_sync import sync_with_broker
        await sync_with_broker(self)
    
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
        
        Delegated to warrior_monitor_exit module for maintainability.
        """
        from nexus2.domain.automation.warrior_monitor_exit import evaluate_position
        return await evaluate_position(self, position, prefetched_price)
    
    async def _check_scale_opportunity(
        self,
        position: WarriorPosition,
        current_price: Decimal,
    ) -> Optional[Dict]:
        """
        Check if position qualifies for scaling in (Ross Cameron methodology).
        
        Delegated to warrior_monitor_scale module for maintainability.
        """
        from nexus2.domain.automation.warrior_monitor_scale import check_scale_opportunity
        return await check_scale_opportunity(self, position, current_price)
    
    async def _execute_scale_in(
        self,
        position: WarriorPosition,
        scale_signal: Dict,
    ) -> bool:
        """
        Execute a scale-in order (Ross Cameron methodology).
        
        Delegated to warrior_monitor_scale module for maintainability.
        """
        from nexus2.domain.automation.warrior_monitor_scale import execute_scale_in
        return await execute_scale_in(self, position, scale_signal)
    
    async def _handle_exit(self, signal: WarriorExitSignal):
        """
        Handle an exit signal.
        
        Delegated to warrior_monitor_exit module for maintainability.
        """
        from nexus2.domain.automation.warrior_monitor_exit import handle_exit
        await handle_exit(self, signal)
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def _add_realized_pnl(self, pnl: Decimal):
        """Add to realized P&L, resetting if new day."""
        today = now_utc().date()
        if self._pnl_date != today:
            self.realized_pnl_today = Decimal("0")
            self._pnl_date = today
        self.realized_pnl_today += pnl
    
    def reset_daily_pnl(self):
        """Manually reset daily P&L tracking."""
        self.realized_pnl_today = Decimal("0")
        self._pnl_date = now_utc().date()
    
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
    """Get singleton Warrior monitor.
    
    Loads persisted settings on first creation.
    """
    global _warrior_monitor
    if _warrior_monitor is None:
        _warrior_monitor = WarriorMonitor()
        
        # Load persisted settings (including scaling)
        try:
            from nexus2.db.warrior_monitor_settings import load_monitor_settings, apply_monitor_settings
            settings = load_monitor_settings()
            if settings:
                apply_monitor_settings(_warrior_monitor.settings, settings)
        except Exception as e:
            logger.warning(f"[Warrior Monitor] Failed to load settings: {e}")
    
    return _warrior_monitor
