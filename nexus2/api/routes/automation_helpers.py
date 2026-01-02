"""
Automation Helper Functions

Helper functions for automation system - auto-start, scanner config, callbacks.
Extracted from automation.py for cleaner separation of concerns.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytz

from nexus2.db import SessionLocal
from nexus2.db.repository import PositionRepository, PositionExitRepository, SchedulerSettingsRepository

logger = logging.getLogger(__name__)


# ==================== AUTO-START HELPERS ====================

async def auto_start_checker(
    get_scheduler_fn,
    get_engine_fn,
    get_monitor_fn,
    configure_and_start_fn,
):
    """
    Background task that checks if scheduler should auto-start.
    
    Runs every 60 seconds and checks:
    1. Is auto-start enabled?
    2. Is current time (ET) matching the configured start time?
    3. Is scheduler not already running?
    
    If all conditions met, starts the scheduler and sends Discord notification.
    """
    from nexus2.api.routes.automation_state import (
        get_auto_start_triggered_today,
        set_auto_start_triggered_today,
    )
    
    et_tz = pytz.timezone('America/New_York')
    
    while True:
        try:
            # Get current ET time
            now_et = datetime.now(et_tz)
            current_time = now_et.strftime("%H:%M")
            
            # Reset trigger flag at midnight
            if current_time == "00:00":
                set_auto_start_triggered_today(False)
            
            # Skip if already triggered today
            if get_auto_start_triggered_today():
                await asyncio.sleep(60)
                continue
            
            # Check scheduler settings
            db = SessionLocal()
            try:
                repo = SchedulerSettingsRepository(db)
                settings = repo.get()
                
                # Check if auto-start is enabled and time matches
                if (settings.auto_start_enabled == "true" and 
                    settings.auto_start_time and
                    settings.auto_start_time == current_time):
                    
                    # Check if scheduler is not already running
                    scheduler = get_scheduler_fn()
                    if not scheduler.is_running:
                        logger.info(f"[AutoStart] Time matched ({current_time} ET) - starting full automation")
                        print(f"🚀 [AutoStart] Starting full automation at {current_time} ET")
                        
                        # Start Engine first (sync method)
                        engine = get_engine_fn()
                        if engine.state.name != "RUNNING":
                            engine.start()  # Sync, returns dict
                            print("[AutoStart] Engine started")
                        
                        # Start Monitor (async method)
                        monitor = get_monitor_fn()
                        if not monitor._running:
                            await monitor.start()  # Async, returns dict
                            print("[AutoStart] Monitor started")
                        
                        # Configure scheduler with callbacks (same as manual UI start)
                        await configure_and_start_fn(engine, scheduler)
                        print("[AutoStart] Scheduler started with full callbacks")
                        
                        set_auto_start_triggered_today(True)
                        
                        # Send Discord notification
                        try:
                            from nexus2.adapters.notifications.discord import DiscordNotifier
                            notifier = DiscordNotifier()
                            if notifier.config.enabled:
                                notifier.send_system_alert(
                                    f"🚀 Full Automation Started at {current_time} ET (Engine + Monitor + Scheduler)",
                                    level="success"
                                )
                                print("[AutoStart] Discord notification sent")
                            else:
                                print("[AutoStart] Discord disabled (no webhook URL configured)")
                            logger.info("[AutoStart] Full automation started with Discord notification")
                        except Exception as e:
                            logger.warning(f"[AutoStart] Discord notification failed: {e}")
                    else:
                        logger.debug(f"[AutoStart] Scheduler already running, skipping")
                        set_auto_start_triggered_today(True)
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[AutoStart] Checker error: {e}")
        
        await asyncio.sleep(60)


def start_auto_start_checker(get_scheduler_fn, get_engine_fn, get_monitor_fn, configure_and_start_fn):
    """Start the auto-start checker background task."""
    from nexus2.api.routes.automation_state import get_auto_start_task, set_auto_start_task
    
    task = get_auto_start_task()
    if task is None:
        task = asyncio.create_task(
            auto_start_checker(get_scheduler_fn, get_engine_fn, get_monitor_fn, configure_and_start_fn)
        )
        set_auto_start_task(task)
        logger.info("[AutoStart] Checker started")
    return task


# ==================== SCANNER CONFIG HELPERS ====================

async def configure_scanner_from_settings(engine, scheduler):
    """
    Configure engine scanner and scheduler settings from database.
    
    This is the shared scanner configuration logic used by both manual start
    and auto-start. Returns settings dict for logging/reference.
    
    Returns:
        dict with settings applied
    """
    from nexus2.domain.automation.services import create_unified_scanner_callback
    
    db = SessionLocal()
    try:
        settings_repo = SchedulerSettingsRepository(db)
        sched_settings = settings_repo.get()
        
        # Read settings
        min_quality = sched_settings.min_quality
        stop_mode = sched_settings.stop_mode or "atr"
        max_stop_atr = float(sched_settings.max_stop_atr) if sched_settings.max_stop_atr else 1.0
        max_stop_percent = float(sched_settings.max_stop_percent) if sched_settings.max_stop_percent else 5.0
        scan_modes = sched_settings.scan_modes.split(",") if sched_settings.scan_modes else ["ep", "breakout", "htf"]
        htf_frequency = sched_settings.htf_frequency or "every_cycle"
        
        # Read auto_execute from settings (default False for safety)
        auto_execute_setting = getattr(sched_settings, 'auto_execute', 'false')
        auto_execute = auto_execute_setting == "true" if isinstance(auto_execute_setting, str) else bool(auto_execute_setting)
        
        # Read sim_mode from settings (default False)
        sim_mode_setting = getattr(sched_settings, 'sim_mode', 'false')
        sim_mode = sim_mode_setting == "true" if isinstance(sim_mode_setting, str) else bool(sim_mode_setting)
        
        # Set scheduler flags
        scheduler.auto_execute = auto_execute
        scheduler.sim_mode = sim_mode  # Use sim clock for market hours
        
        # Sync engine config with settings (fixes trading_mode display)
        engine.config.sim_only = sim_mode
        
        # Configure engine scanner (with sim_mode for MockMarketData injection)
        engine._scanner_func = await create_unified_scanner_callback(
            min_quality=min_quality,
            max_stop_percent=max_stop_percent,
            stop_mode=stop_mode,
            max_stop_atr=max_stop_atr,
            scan_modes=scan_modes,
            htf_frequency=htf_frequency,
            sim_mode=sim_mode,  # NEW: Use MockMarketData when True
        )
        
        settings_used = {
            "min_quality": min_quality,
            "stop_mode": stop_mode,
            "max_stop_atr": max_stop_atr,
            "max_stop_percent": max_stop_percent,
            "scan_modes": scan_modes,
            "htf_frequency": htf_frequency,
            "auto_execute": auto_execute,
            "sim_mode": sim_mode,  # NEW
        }
        
        logger.info(f"[Scheduler] Scanner configured: {settings_used}")
        
        return settings_used
    finally:
        db.close()


# ==================== EOD CALLBACK FACTORY ====================

def create_eod_callback(market_data, broker):
    """
    Create the EOD callback function for 3:45 PM MA trailing stop check.
    
    This is shared between manual start and auto-start to avoid duplication.
    Uses AUTO MA type (KK-style: ADR% determines 10 vs 20 MA).
    
    Args:
        market_data: Market data provider for quotes and MAs
        broker: Broker for submitting exit orders
    
    Returns:
        Async callback function for EOD check
    """
    async def eod_callback():
        """Run MA check at end of day for trailing stops."""
        from nexus2.domain.automation.ema_check_job import MACheckJob, TrailingMAType
        
        logger.info("[EOD] Running automatic MA trailing stop check...")
        
        # Create job with AUTO MA selection (KK-style: ADR% determines 10 vs 20 MA)
        job = MACheckJob(
            min_days_for_trailing=5,
            default_ma_type=TrailingMAType.AUTO,  # Dynamic based on ADR%
            require_timing_window=False,  # Already in window, so don't require it again
        )
        
        # Callback: Get open positions
        async def get_positions():
            db = SessionLocal()
            try:
                position_repo = PositionRepository(db)
                positions = position_repo.get_open()
                return [
                    {
                        "id": p.id,
                        "symbol": p.symbol,
                        "opened_at": p.opened_at,
                        "remaining_shares": p.remaining_shares,
                        "entry_price": p.entry_price,
                    }
                    for p in positions
                ]
            finally:
                db.close()
        
        # Callback: Get daily close
        async def get_daily_close(symbol: str):
            if market_data:
                try:
                    quote = market_data.get_quote(symbol)
                    if quote and hasattr(quote, 'close'):
                        return quote.close
                    elif quote and hasattr(quote, 'price'):
                        return quote.price
                except Exception as e:
                    logger.warning(f"[EOD] Could not get close for {symbol}: {e}")
            return None
        
        # Callback: Get EMA
        async def get_ema(symbol: str, period: int):
            if market_data:
                try:
                    return market_data.get_ema(symbol, period)
                except Exception as e:
                    logger.warning(f"[EOD] Could not get EMA{period} for {symbol}: {e}")
            return None
        
        # Callback: Get SMA
        async def get_sma(symbol: str, period: int):
            if market_data:
                try:
                    return market_data.get_sma(symbol, period)
                except Exception as e:
                    logger.warning(f"[EOD] Could not get SMA{period} for {symbol}: {e}")
            return None
        
        # Callback: Get ADR% (for AUTO MA selection)
        async def get_adr_percent(symbol: str, period: int):
            if market_data:
                try:
                    return market_data.get_adr_percent(symbol, period)
                except Exception as e:
                    logger.warning(f"[EOD] Could not get ADR% for {symbol}: {e}")
            return None
        
        # Callback: Get price history (for affinity analysis)
        async def get_price_history(symbol: str, days: int):
            if market_data:
                try:
                    # Get historical bars for affinity analysis
                    bars = market_data.get_historical_bars(symbol, days)
                    if bars:
                        return [
                            {
                                "close": float(bar.close),
                                "high": float(bar.high),
                                "low": float(bar.low),
                                "date": bar.timestamp.isoformat() if hasattr(bar, 'timestamp') else str(bar.date),
                            }
                            for bar in bars
                        ]
                except Exception as e:
                    logger.warning(f"[EOD] Could not get price history for {symbol}: {e}")
            return None
        
        # Callback: Execute exit (use broker if available)
        async def execute_exit(position_id: str, shares: int, reason: str):
            db = SessionLocal()
            try:
                position_repo = PositionRepository(db)
                exit_repo = PositionExitRepository(db)
                
                position = position_repo.get_by_id(position_id)
                if not position:
                    return
                
                # Get current price for exit record
                current_price = None
                if market_data:
                    quote = market_data.get_quote(position.symbol)
                    current_price = quote.price if quote else None
                
                if not current_price:
                    current_price = position.entry_price  # Fallback
                
                # Submit sell order through broker if available
                if broker:
                    try:
                        broker.submit_order(
                            client_order_id=uuid4(),
                            symbol=position.symbol,
                            quantity=shares,
                            side="sell",
                            order_type="market",
                        )
                        logger.info(f"[EOD] Submitted sell order for {position.symbol} x {shares}")
                    except Exception as e:
                        logger.error(f"[EOD] Failed to submit sell order: {e}")
                
                # Record exit
                exit_repo.create({
                    "id": str(uuid4()),
                    "position_id": position_id,
                    "shares": shares,
                    "exit_price": str(current_price),
                    "reason": reason,
                    "exited_at": datetime.utcnow(),
                })
                
                # Update position
                new_remaining = position.remaining_shares - shares
                position_repo.update(position_id, {
                    "remaining_shares": new_remaining,
                    "status": "closed" if new_remaining <= 0 else "open",
                })
                
                logger.info(f"[EOD] Exited {position.symbol}: {shares} shares ({reason})")
            finally:
                db.close()
        
        # Set callbacks and run (including affinity callbacks)
        job.set_callbacks(
            get_positions=get_positions,
            get_daily_close=get_daily_close,
            get_ema=get_ema,
            get_sma=get_sma,
            get_adr_percent=get_adr_percent,
            get_price_history=get_price_history,
            execute_exit=execute_exit,
        )
        
        result = await job.run(dry_run=False)  # Execute real exits
        
        return {
            "positions_checked": result.positions_checked,
            "exit_signals": len(result.exit_signals),
            "errors": len(result.errors),
        }
    
    return eod_callback


# ==================== EXECUTE CALLBACK FACTORY ====================

def create_execute_callback(engine, broker, get_app_fn):
    """
    Create the execute callback function for auto-executing trades.
    
    Args:
        engine: AutomationEngine instance
        broker: Broker for order submission
        get_app_fn: Function to get FastAPI app reference
    
    Returns:
        Async callback function for trade execution, or None if no broker
    """
    if not broker:
        return None
    
    async def execute_callback():
        """Auto-execute trades from signals using broker."""
        print(f"🤖 [AutoExec] Starting auto-execute cycle...")
        
        # Get signals from engine's last scan
        if not hasattr(engine, '_last_signals') or not engine._last_signals:
            print("[AutoExec] No signals to execute")
            return {"status": "no_signals"}
        
        signals = engine._last_signals
        executed = []
        skipped = []
        errors = []
        
        for signal in signals:  # Execute all valid signals
            try:
                # Get fresh settings each cycle
                db = SessionLocal()
                try:
                    settings_repo = SchedulerSettingsRepository(db)
                    sched_settings = settings_repo.get()
                    
                    # Position limit check
                    position_repo = PositionRepository(db)
                    open_positions = position_repo.get_open()
                    max_positions = int(sched_settings.max_positions) if sched_settings.max_positions else 5
                    
                    if len(open_positions) >= max_positions:
                        skipped.append({"symbol": signal.symbol, "reason": "max_positions_reached"})
                        continue
                    
                    # Calculate position size based on risk
                    risk_amount = float(sched_settings.risk_per_trade) if sched_settings.risk_per_trade else 250.0
                    stop_distance = abs(float(signal.entry_price) - float(signal.stop_price))
                    if stop_distance <= 0:
                        skipped.append({"symbol": signal.symbol, "reason": "invalid_stop"})
                        continue
                    
                    shares = int(risk_amount / stop_distance)
                    if shares < 1:
                        skipped.append({"symbol": signal.symbol, "reason": "position_too_small"})
                        continue
                    
                    # Apply max position value cap (if set)
                    entry_price = float(signal.entry_price)
                    max_position_value = float(sched_settings.max_position_value) if sched_settings.max_position_value else None
                    if max_position_value:
                        max_shares_by_value = int(max_position_value / entry_price)
                        if shares > max_shares_by_value:
                            logger.info(f"[AutoExec] Capping {signal.symbol} shares from {shares} to {max_shares_by_value} (max_position_value=${max_position_value})")
                            shares = max_shares_by_value
                            if shares < 1:
                                skipped.append({"symbol": signal.symbol, "reason": "max_position_value_too_small"})
                                continue
                    
                    # Check if in simulation mode
                    sim_mode = getattr(sched_settings, 'sim_mode', 'false') == 'true'
                    
                    if sim_mode:
                        # Use MockBroker for simulation
                        from nexus2.api.routes.automation import get_simulation_status
                        if hasattr(get_simulation_status, '_mock_broker'):
                            mock_broker = get_simulation_status._mock_broker
                            # Set current price for the symbol (use signal entry price)
                            mock_broker.set_price(signal.symbol, float(signal.entry_price))
                            
                            result = mock_broker.submit_bracket_order(
                                symbol=signal.symbol,
                                side="buy",
                                qty=shares,
                                stop_price=float(signal.stop_price),
                            )
                            logger.info(f"[SIM] Submitted mock order for {signal.symbol}: {result}")
                        else:
                            skipped.append({"symbol": signal.symbol, "reason": "simulation_not_initialized"})
                            continue
                    else:
                        # Submit bracket order to real broker
                        from nexus2.domain.orders.models import OrderSide
                        result = broker.submit_bracket_order(
                            symbol=signal.symbol,
                            side=OrderSide.BUY,
                            qty=shares,
                            stop_price=float(signal.stop_price),
                            take_profit_price=None,  # No TP for KK style
                        )
                    
                    if result and result.is_accepted:
                        # Get NAC-specific broker/account for position tagging
                        nac_broker = getattr(sched_settings, 'nac_broker_type', 'alpaca_paper') or 'alpaca_paper'
                        nac_account = getattr(sched_settings, 'nac_account', 'A') or 'A'
                        
                        # Create position record with NAC account
                        position_repo.create({
                            "id": str(uuid4()),
                            "symbol": signal.symbol,
                            "setup_type": signal.setup_type.value,
                            "status": "open",
                            "entry_price": str(result.avg_fill_price or signal.entry_price),
                            "shares": shares,
                            "remaining_shares": shares,
                            "initial_stop": str(signal.stop_price),
                            "current_stop": str(signal.stop_price),
                            "realized_pnl": "0",
                            "opened_at": datetime.utcnow(),
                            "broker_type": nac_broker,
                            "account": nac_account,
                        })
                        executed.append({"symbol": signal.symbol, "shares": shares})
                        print(f"✅ [AutoExec] Executed: {signal.symbol} x {shares}")
                        
                        # Send Discord notification for executed trade
                        try:
                            from nexus2.adapters.notifications.discord import DiscordNotifier
                            notifier = DiscordNotifier()
                            if notifier.config.enabled:
                                fill_price = float(result.avg_fill_price or signal.entry_price)
                                stop_price = float(signal.stop_price)
                                risk_per_share = abs(fill_price - stop_price)
                                total_risk = risk_per_share * shares
                                position_value = fill_price * shares
                                
                                notifier.send_system_alert(
                                    f"📈 **TRADE EXECUTED**\n"
                                    f"**{signal.symbol}** ({signal.setup_type.value})\n"
                                    f"• Shares: {shares} @ ${fill_price:.2f}\n"
                                    f"• Stop: ${stop_price:.2f}\n"
                                    f"• Risk: ${total_risk:.2f} (${risk_per_share:.2f}/share)\n"
                                    f"• Position: ${position_value:.2f}",
                                    level="success"
                                )
                        except Exception as discord_err:
                            logger.warning(f"[AutoExec] Discord notification failed: {discord_err}")
                    else:
                        errors.append({"symbol": signal.symbol, "error": "order_rejected"})
                finally:
                    db.close()
            except Exception as e:
                errors.append({"symbol": signal.symbol, "error": str(e)})
                logger.error(f"[AutoExec] Error executing {signal.symbol}: {e}")
        
        print(f"🤖 [AutoExec] Cycle complete: {len(executed)} executed, {len(skipped)} skipped, {len(errors)} errors")
        return {"executed": executed, "skipped": skipped, "errors": errors}
    
    return execute_callback


# ==================== SCHEDULER STARTUP HELPER ====================

async def configure_and_start_scheduler(engine, scheduler, get_app_fn):
    """
    Configure scheduler with scan callback and start it.
    
    Used by auto-start for full autonomous mode.
    
    Returns:
        dict with scheduler start result
    """
    # Configure scanner from settings (shared logic)
    settings = await configure_scanner_from_settings(engine, scheduler)
    
    # Get broker from app state for execute callback
    app = get_app_fn()
    broker = getattr(app.state, 'broker', None) if app else None
    market_data = getattr(app.state, 'market_data', None) if app else None
    
    # Use auto_execute from settings (for full autonomous operation)
    auto_execute = settings.get("auto_execute", False)
    scheduler.auto_execute = auto_execute if broker else False
    
    # Set up scan callback
    async def scan_callback():
        return await engine.run_scan_cycle()
    
    # Set up execute callback if broker is available and auto_execute is True
    execute_callback = None
    if broker and auto_execute:
        execute_callback = create_execute_callback(engine, broker, get_app_fn)
        logger.info("[Scheduler] Auto-start: FULL AUTONOMOUS MODE (execute callback enabled)")
    else:
        logger.info("[Scheduler] Auto-start: scan-only mode (no broker or auto_execute disabled)")
    
    # Create EOD callback using shared helper (for 3:45 PM MA trailing stop check)
    eod_callback = create_eod_callback(market_data, broker)
    
    # Set callbacks (scan + optional execute + EOD)
    scheduler.set_callbacks(scan_callback, execute_callback, eod_callback)
    
    # Start scheduler
    result = await scheduler.start()
    
    return result
