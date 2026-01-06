"""
Scheduler Routes Module

Extracted from automation.py for better maintainability.
Contains all scheduler-related endpoints for starting, stopping, and configuring
the automated trading scheduler, plus force scan and diagnostics.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException

from nexus2.domain.automation.engine import AutomationEngine
from nexus2.api.routes.automation_state import (
    get_engine, get_scheduler, get_monitor,
    get_sim_broker, set_sim_broker,  # Thread-safe sim broker
)
from nexus2.api.routes.automation_models import (
    SchedulerStartRequest,
    SchedulerToggleRequest,
    SchedulerIntervalRequest,
    SchedulerSettingsRequest,
    SCHEDULER_PRESETS,
)
from nexus2.api.routes.automation_helpers import (
    configure_scanner_from_settings,
    create_eod_callback,
)
from nexus2.api.routes.execution_handler import create_execute_callback as _create_execute_callback_factory
from nexus2.db import SessionLocal
from nexus2.db.repository import PositionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])

# NOTE: _sim_broker moved to automation_state.py for thread safety
# Use get_sim_broker() and set_sim_broker() instead


@router.post("/scheduler/start", response_model=dict)
async def start_scheduler(
    request: Request,
    req: SchedulerStartRequest = SchedulerStartRequest(),
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Start the background scheduler.
    
    Runs scan cycles at configured intervals during market hours.
    Set auto_execute=True to automatically execute trades (careful!).
    """
    scheduler = get_scheduler()
    
    # Configure scheduler
    scheduler.interval_minutes = req.interval_minutes
    scheduler.auto_execute = req.auto_execute
    
    # Get broker from app state for order submission
    broker = getattr(request.app.state, 'broker', None)
    market_data = getattr(request.app.state, 'market_data', None)
    
    # =============================
    # CONFIGURE ENGINE SCANNER FUNCTION
    # =============================
    # Use shared helper to configure scanner from settings (eliminates duplication)
    settings = await configure_scanner_from_settings(engine, scheduler)
    auto_execute = settings["auto_execute"]
    
    # Apply auto_execute from saved settings (override request default)
    scheduler.auto_execute = auto_execute
    
    print(f"🔧 [Scheduler] Scanner configured: {settings}")
    
    # Set up callbacks
    async def scan_callback():
        return await engine.run_scan_cycle()

    # Execute callback from modular handler (extracted for maintainability)
    execute_callback = _create_execute_callback_factory(
        engine=engine,
        scheduler=scheduler,
        broker=broker,
        get_sim_broker=get_sim_broker,  # From automation_state.py (thread-safe)
        set_sim_broker=set_sim_broker,  # From automation_state.py (thread-safe)
        req=req,
    )
    
    # EOD callback using shared helper (avoids code duplication)
    sim_mode = settings.get("sim_mode", False)
    eod_callback = create_eod_callback(market_data, broker, sim_mode=sim_mode)
    
    scheduler.set_callbacks(scan_callback, execute_callback, eod_callback)
    
    result = await scheduler.start()
    
    # =============================
    # AUTO-START ENGINE
    # =============================
    # Start the engine so it shows as RUNNING in the UI
    engine.start()
    logger.info("[Scheduler] Auto-started Engine")
    
    # =============================
    # AUTO-START POSITION MONITOR
    # =============================
    # This handles Day 3-5 partials and intraday stop checks
    from nexus2.api.routes.settings import get_settings
    
    saved_settings = get_settings()
    
    # Get the shared monitor singleton (same instance used by /monitor/status)
    _monitor = get_monitor()
    _monitor.kk_style_partials = True
    _monitor.partial_exit_days = saved_settings.partial_exit_days
    _monitor.partial_exit_fraction = saved_settings.partial_exit_fraction
    
    # Callback: Get open positions (with broker sync)
    async def get_monitor_positions():
        from nexus2.db.database import get_session
        from datetime import datetime
        
        with get_session() as db:
            position_repo = PositionRepository(db)
            positions = position_repo.get_open()
            
            # Sync with broker: close positions no longer at broker
            print(f"[DEBUG] get_monitor_positions called, broker={broker is not None}")
            if broker:
                try:
                    broker_positions = broker.get_positions()
                    broker_symbols = set(broker_positions.keys())
                    logger.info(f"[Monitor] Broker sync: {len(positions)} DB open, {len(broker_symbols)} at broker")
                    
                    for p in positions:
                        if p.symbol not in broker_symbols and p.remaining_shares > 0:
                            # Position closed at broker (stop hit or manual) - close locally
                            # Preserve metadata by only updating status, not overwriting other fields
                            logger.info(f"[Monitor] Syncing closed position: {p.symbol} (no longer at broker)")
                            position_repo.update(p.id, {
                                "status": "closed",
                                "remaining_shares": 0,
                                "closed_at": datetime.utcnow(),
                            })
                            # Add to recent exits for potential re-entry
                            from nexus2.api.routes.automation_state import add_recent_exit
                            add_recent_exit(p.symbol, getattr(p, 'setup_type', 'unknown'))
                    
                    # Commit sync changes before refresh
                    db.commit()
                    
                    # Refresh positions after sync
                    positions = position_repo.get_open()
                except Exception as e:
                    logger.warning(f"[Monitor] Broker sync failed: {e}")
            
            return [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "entry_price": p.entry_price,
                    "initial_stop": p.initial_stop,
                    "current_stop": p.current_stop,
                    "remaining_shares": p.remaining_shares,
                    "opened_at": p.opened_at,
                    "partial_taken": getattr(p, 'partial_taken', False),
                }
                for p in positions
            ]
    
    # Callback: Get current price - USE ALPACA FOR REALTIME
    # FMP quote has delays and may return previous close instead of intraday price
    async def get_monitor_price(symbol: str):
        # Try Alpaca positions first (real-time, no extra API call)
        if broker:
            try:
                positions = broker.get_positions()
                if symbol in positions:
                    pos = positions[symbol]
                    # Calculate current price from market_value / quantity
                    if pos.quantity and pos.quantity > 0 and pos.market_value:
                        price = pos.market_value / pos.quantity
                        logger.info(f"[Monitor Price] {symbol}: ${price:.2f} (Alpaca position)")
                        return float(price)
            except Exception as e:
                logger.warning(f"[Monitor Price] {symbol}: Alpaca position check failed: {e}")
        
        # Fallback to unified market data (may use FMP)
        if market_data:
            try:
                # Prefer Alpaca quotes via the unified adapter's alpaca client
                quote = market_data.alpaca.get_quote(symbol)
                if quote:
                    price = quote.price if hasattr(quote, 'price') else quote.close
                    logger.info(f"[Monitor Price] {symbol}: ${price} (Alpaca quote fallback)")
                    return price
            except Exception as e:
                logger.warning(f"[Monitor Price] {symbol}: Alpaca quote failed: {e}")
        
        # Last resort: FMP (may be stale)
        if market_data:
            try:
                quote = market_data.fmp.get_quote(symbol)
                if quote:
                    price = quote.price
                    logger.warning(f"[Monitor Price] {symbol}: ${price} (FMP FALLBACK - may be stale!)")
                    return price
            except Exception as e:
                logger.warning(f"[Monitor Price] {symbol}: FMP quote failed: {e}")
        
        logger.warning(f"[Monitor Price] {symbol}: No price available from any source")
        return None
    
    # Callback: Update stop (move to breakeven)
    async def update_stop(position_id: str, new_stop_price):
        from nexus2.db.database import get_session
        with get_session() as db:
            position_repo = PositionRepository(db)
            position_repo.update(position_id, {
                "current_stop": str(new_stop_price),
                "partial_taken": True,  # Mark partial as taken
            })
            logger.info(f"[Monitor] Updated stop for {position_id} to ${new_stop_price}")
    
    # Callback: Execute exit
    async def execute_monitor_exit(signal):
        logger.info(f"[Monitor] execute_monitor_exit called: {signal.symbol} x {signal.shares_to_exit}, reason={signal.reason}")
        logger.info(f"[Monitor] Broker: {broker}, sim_only: {engine.config.sim_only}")
        
        # SAFETY: Check market hours before submitting exit orders
        from nexus2.adapters.market_data.market_calendar import MarketCalendar
        calendar = MarketCalendar()
        if not calendar.is_market_open():
            logger.warning(f"[Monitor] BLOCKED: Exit order for {signal.symbol} blocked - market closed. Will retry next check cycle.")
            return  # Don't submit orders outside market hours
        
        if broker and not engine.config.sim_only:
            # Submit market sell order
            try:
                from uuid import uuid4
                logger.info(f"[Monitor] Submitting sell order: {signal.symbol} x {signal.shares_to_exit}")
                result = broker.submit_order(
                    client_order_id=uuid4(),
                    symbol=signal.symbol,
                    quantity=signal.shares_to_exit,
                    side="sell",
                    order_type="market",
                )
                logger.info(f"[Monitor] Exit executed: {signal.symbol} x {signal.shares_to_exit}")
                
                # Record exit data in database
                try:
                    from nexus2.db.database import get_session
                    with get_session() as db:
                        position_repo = PositionRepository(db)
                        # Find open position for this symbol
                        positions = position_repo.get_open()
                        for pos in positions:
                            if pos.symbol == signal.symbol:
                                exit_price = str(result.avg_fill_price) if result.avg_fill_price else None
                                remaining = pos.remaining_shares - signal.shares_to_exit
                                updates = {
                                    "remaining_shares": max(0, remaining),
                                    "exit_price": exit_price,
                                    "exit_date": datetime.utcnow(),
                                }
                                # If fully closed, update status
                                if remaining <= 0:
                                    updates["status"] = "closed"
                                    updates["closed_at"] = datetime.utcnow()
                                position_repo.update(pos.id, updates)
                                logger.info(f"[Monitor] Position updated: {signal.symbol} remaining={remaining}")
                                break
                        db.commit()
                except Exception as db_err:
                    logger.warning(f"[Monitor] DB update failed: {db_err}")
                    
            except Exception as e:
                logger.error(f"[Monitor] Exit failed: {e}")
                raise  # Re-raise so monitor.py knows exit failed and won't send Discord
    
    _monitor.set_callbacks(
        get_positions=get_monitor_positions,
        get_price=get_monitor_price,
        update_stop=update_stop,
        execute_exit=execute_monitor_exit,
    )
    
    await _monitor.start()
    logger.info("[Scheduler] PositionMonitor started with KK-style partials")
    
    return {
        **result,
        "message": f"Scheduler running every {req.interval_minutes} min with auto MA check at 3:45 PM",
        "auto_execute": scheduler.auto_execute,  # Use actual value from DB settings
        "broker_connected": broker is not None,
        "monitor_running": True,
    }


@router.post("/scheduler/stop", response_model=dict)
async def stop_scheduler(
    engine: AutomationEngine = Depends(get_engine),
):
    """Stop the background scheduler, engine, and position monitor."""
    scheduler = get_scheduler()
    result = await scheduler.stop()
    
    # Also stop the engine
    engine.stop()
    logger.info("[Scheduler] Engine stopped")
    
    # Also stop the position monitor (using shared singleton)
    monitor = get_monitor()
    if monitor._running:
        await monitor.stop()
        logger.info("[Scheduler] PositionMonitor stopped")
    
    return {**result, "engine_stopped": True, "monitor_stopped": True}


@router.post("/scheduler/force_scan", response_model=dict)
async def force_scheduler_scan(
    request: Request,
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Force an immediate scan cycle regardless of market hours.
    
    This is useful for:
    - Simulation testing (when sim_clock is during market hours but real time isn't)
    - Manual testing outside market hours
    
    Returns:
        Dict with scan results, signals found, and execution results if auto_execute is on
    """
    from nexus2.db import SchedulerSettingsRepository
    from nexus2.domain.automation.services import create_unified_scanner_callback
    
    # Get fresh settings
    db = SessionLocal()
    try:
        settings_repo = SchedulerSettingsRepository(db)
        sched_settings = settings_repo.get()
        
        min_quality = sched_settings.min_quality
        stop_mode = sched_settings.stop_mode or "atr"
        max_stop_atr = float(sched_settings.max_stop_atr) if sched_settings.max_stop_atr else 1.0
        max_stop_percent = float(sched_settings.max_stop_percent) if sched_settings.max_stop_percent else 5.0
        scan_modes = sched_settings.scan_modes.split(",") if sched_settings.scan_modes else ["ep", "breakout", "htf"]
        htf_frequency = sched_settings.htf_frequency or "every_cycle"
        
        # Check sim_mode
        sim_mode_setting = getattr(sched_settings, 'sim_mode', 'false')
        sim_mode = sim_mode_setting == "true" if isinstance(sim_mode_setting, str) else bool(sim_mode_setting)
        
        # Check auto_execute
        auto_execute_setting = getattr(sched_settings, 'auto_execute', 'false')
        auto_execute = auto_execute_setting == "true" if isinstance(auto_execute_setting, str) else bool(auto_execute_setting)
        
    finally:
        db.close()
    
    logger.info(f"[ForceScan] Running with sim_mode={sim_mode}, auto_execute={auto_execute}")
    
    # =============================
    # SIM MODE: Run scanner directly (bypass engine callback issues)
    # =============================
    if sim_mode:
        from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
        from nexus2.domain.scanner.ep_scanner_service import EPScannerService, EPScanSettings
        from nexus2.domain.scanner.breakout_scanner_service import BreakoutScannerService
        from nexus2.domain.scanner.htf_scanner_service import HTFScannerService
        from nexus2.domain.automation.unified_scanner import (
            UnifiedScannerService,
            UnifiedScanSettings,
            ScanMode,
        )
        
        clock = get_simulation_clock()
        data = get_mock_market_data()
        
        # Ensure clock is connected
        if data._sim_clock is None:
            data.set_clock(clock)
        
        logger.info(f"[ForceScan SIM] Using MockMarketData (clock={clock.get_trading_day()}, symbols={data.get_symbols()})")
        
        # Use relaxed sim settings for EP
        sim_ep_settings = EPScanSettings(
            min_gap=3.0,
            min_rvol=0.5,
            min_price=5.0,
            min_dollar_vol=1_000_000,
        )
        
        # Create scanners with MockMarketData
        ep_scanner = EPScannerService(settings=sim_ep_settings, market_data=data)
        breakout_scanner = BreakoutScannerService(market_data=data)
        htf_scanner = HTFScannerService(market_data=data)
        
        # Use settings from database
        enabled_modes = []
        for mode_str in scan_modes:
            if mode_str.lower() == "ep":
                enabled_modes.append(ScanMode.EP_ONLY)
            elif mode_str.lower() == "breakout":
                enabled_modes.append(ScanMode.BREAKOUT_ONLY)
            elif mode_str.lower() == "htf":
                enabled_modes.append(ScanMode.HTF_ONLY)
        
        settings = UnifiedScanSettings(
            modes=enabled_modes if enabled_modes else [ScanMode.EP_ONLY, ScanMode.BREAKOUT_ONLY, ScanMode.HTF_ONLY],
            min_quality_score=min_quality,
            stop_mode=stop_mode,
            max_stop_atr=max_stop_atr,
            max_stop_percent=max_stop_percent,
        )
        
        scanner = UnifiedScannerService(
            settings=settings,
            ep_scanner=ep_scanner,
            breakout_scanner=breakout_scanner,
            htf_scanner=htf_scanner,
        )
        
        # Run scan directly
        scan_result = scanner.scan(verbose=False)
        signals = scan_result.signals
        
        logger.info(f"[ForceScan SIM] Found {len(signals)} signals")
    else:
        # =============================
        # LIVE MODE: Use engine callback as before
        # =============================
        engine._scanner_func = await create_unified_scanner_callback(
            min_quality=min_quality,
            max_stop_percent=max_stop_percent,
            stop_mode=stop_mode,
            max_stop_atr=max_stop_atr,
            scan_modes=scan_modes,
            htf_frequency=htf_frequency,
            sim_mode=False,
        )
        
        # Run the scan cycle
        scan_result = await engine.run_scan_cycle()
        
        # Get signals from result
        signals = []
        if hasattr(scan_result, 'signals'):
            signals = scan_result.signals if scan_result.signals else []
        elif isinstance(scan_result, list):
            signals = scan_result
    
    # Format signals for response
    formatted_signals = []
    for s in signals[:10]:
        if hasattr(s, 'symbol'):
            # Signal object - convert to dict manually
            formatted_signals.append({
                "symbol": s.symbol,
                "setup_type": s.setup_type.value if hasattr(s.setup_type, 'value') else str(s.setup_type),
                "entry_price": float(s.entry_price) if s.entry_price else None,
                "tactical_stop": float(s.tactical_stop) if s.tactical_stop else None,
                "quality_score": s.quality_score,
                "tier": s.tier,
                "scanner_mode": getattr(s, 'scanner_mode', 'unknown'),
            })
        elif isinstance(s, dict):
            formatted_signals.append(s)
        else:
            formatted_signals.append(str(s))
    
    result = {
        "status": "scan_complete",
        "sim_mode": sim_mode,
        "auto_execute": auto_execute,
        "signals_count": len(signals),
        "signals": formatted_signals,
    }
    
    # If auto_execute and we have signals, execute top signal
    if auto_execute and signals:
        result["execution_note"] = "Auto-execute would run here. Enable via scheduler start."
    
    return result


@router.get("/scheduler/status", response_model=dict)
async def get_scheduler_status():
    """Get current scheduler status."""
    scheduler = get_scheduler()
    return scheduler.get_status()


@router.get("/scheduler/signals", response_model=dict)
async def get_scheduler_signals():
    """
    Get signals from the scheduler's last scan cycle.
    
    Returns the most recent signals for UI display.
    """
    scheduler = get_scheduler()
    signals = scheduler.get_last_signals()
    return {
        "signals": signals,
        "count": len(signals),
        "scanned_at": scheduler.last_signals_at.isoformat() if scheduler.last_signals_at else None,
    }


@router.get("/scheduler/diagnostics", response_model=dict)
async def get_scheduler_diagnostics():
    """
    Get detailed diagnostics from the last scan.
    
    Shows per-scanner stats, rejection reasons, and timing.
    Used for debugging and visibility into automation.
    """
    scheduler = get_scheduler()
    
    # Get last scan result from scheduler (if it has diagnostics)
    last_result = getattr(scheduler, 'last_scan_result', None)
    
    if last_result is None:
        return {
            "available": False,
            "message": "No scan has run yet. Start the scheduler to see diagnostics.",
        }
    
    # Format diagnostics for API response
    diagnostics = []
    for diag in getattr(last_result, 'diagnostics', []):
        rejections = []
        for rej in getattr(diag, 'rejections', []):
            rejections.append({
                "symbol": rej.symbol,
                "reason": rej.reason,
                "threshold": rej.threshold,
                "actual_value": rej.actual_value,
            })
        
        diagnostics.append({
            "scanner": diag.scanner,
            "enabled": diag.enabled,
            "candidates_found": diag.candidates_found,
            "candidates_passed": diag.candidates_passed,
            "rejections": rejections,
            "error": diag.error,
        })
    
    return {
        "available": True,
        "scanned_at": last_result.scanned_at.isoformat() if last_result.scanned_at else None,
        "duration_ms": last_result.scan_duration_ms,
        "total_signals": len(last_result.signals),
        "total_processed": last_result.total_processed,
        "ep_count": last_result.ep_count,
        "breakout_count": last_result.breakout_count,
        "htf_count": last_result.htf_count,
        "diagnostics": diagnostics,
    }



@router.patch("/scheduler/auto-execute", response_model=dict)
async def toggle_auto_execute(req: SchedulerToggleRequest):
    """Toggle auto_execute on the scheduler and persist to database."""
    from nexus2.db import SchedulerSettingsRepository
    
    scheduler = get_scheduler()
    scheduler.auto_execute = req.auto_execute
    
    # Persist to database so it survives scheduler restarts
    db = SessionLocal()
    try:
        repo = SchedulerSettingsRepository(db)
        settings = repo.get()
        settings.auto_execute = "true" if req.auto_execute else "false"
        db.commit()
        logger.info(f"[Scheduler] auto_execute toggled to: {req.auto_execute} (persisted to DB)")
        print(f"🔄 [Scheduler] auto_execute toggled to: {req.auto_execute} (persisted)")
    finally:
        db.close()
    
    return {
        "status": "updated",
        "auto_execute": scheduler.auto_execute,
    }


@router.patch("/scheduler/interval", response_model=dict)
async def update_scheduler_interval(req: SchedulerIntervalRequest):
    """Update the scheduler interval (takes effect on next cycle)."""
    scheduler = get_scheduler()
    
    # Validate interval
    valid_intervals = [5, 10, 15, 30]
    if req.interval_minutes not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Valid options: {valid_intervals}"
        )
    
    old_interval = scheduler.interval_minutes
    scheduler.interval_minutes = req.interval_minutes
    
    logger.info(f"[Scheduler] interval changed: {old_interval} -> {req.interval_minutes} min")
    print(f"🔄 [Scheduler] interval changed: {old_interval} -> {req.interval_minutes} min (takes effect next cycle)")
    
    return {
        "status": "updated",
        "interval_minutes": scheduler.interval_minutes,
        "message": f"Interval updated from {old_interval} to {req.interval_minutes} min"
    }


# ==================== SCHEDULER SETTINGS ENDPOINTS ====================

@router.get("/scheduler/settings", response_model=dict)
async def get_scheduler_settings():
    """
    Get current scheduler settings.
    
    Returns the configuration used for scheduled scans (separate from Quick Actions).
    """
    from nexus2.db import SchedulerSettingsRepository
    
    db = SessionLocal()
    try:
        repo = SchedulerSettingsRepository(db)
        settings = repo.get()
        return settings.to_dict()
    finally:
        db.close()


@router.patch("/scheduler/settings", response_model=dict)
async def update_scheduler_settings(req: SchedulerSettingsRequest):
    """
    Update scheduler settings.
    
    These settings control how the scheduler runs scans, separately from Quick Actions.
    Use 'adopt_quick_actions: true' to use Quick Actions settings instead.
    """
    from nexus2.db import SchedulerSettingsRepository
    
    db = SessionLocal()
    try:
        repo = SchedulerSettingsRepository(db)
        
        # Build updates dict from request (only non-None values)
        updates = {}
        
        # Handle preset - apply preset values
        if req.preset:
            updates["preset"] = req.preset
            if req.preset in SCHEDULER_PRESETS:
                preset_values = SCHEDULER_PRESETS[req.preset]
                for key, value in preset_values.items():
                    updates[key] = value if isinstance(value, str) else str(value)
        
        # Override with any explicitly provided values
        for field in ["adopt_quick_actions", "min_quality", "stop_mode", 
                      "max_stop_atr", "max_stop_percent", "scan_modes", "htf_frequency",
                      "max_position_value", "nac_max_positions", "auto_start_enabled", "auto_start_time", "auto_execute",
                      "nac_broker_type", "nac_account", "sim_mode", "min_price", "discord_alerts_enabled"]:
            value = getattr(req, field, None)
            if value is not None:
                # Convert numeric to string for DB storage
                if field in ["max_stop_atr", "max_stop_percent", "max_position_value", "min_price", "nac_max_positions"]:
                    updates[field] = str(value)
                elif field in ["auto_start_enabled", "auto_execute", "sim_mode", "discord_alerts_enabled"]:
                    updates[field] = "true" if value else "false"
                else:
                    updates[field] = value
        
        if updates:
            settings = repo.update(updates)
            logger.info(f"[Scheduler] Settings updated: {updates}")
            return settings.to_dict()
        else:
            return repo.get().to_dict()
    finally:
        db.close()


# ==================== LIQUIDATE ALL ENDPOINT ====================

@router.post("/liquidate-all", response_model=dict)
async def liquidate_all_positions(
    request: Request,
    confirm: str = "",
):
    """
    Liquidate all open positions with market sell orders.
    
    This is a destructive action! Requires confirmation.
    Pass confirm="yes" (case-insensitive) to execute.
    
    Returns:
        Dict with results of liquidation attempt
    """
    # Require confirmation
    if confirm.lower() != "yes":
        return {
            "status": "confirmation_required",
            "message": "Pass confirm='yes' to liquidate all positions",
            "positions_to_close": 0,
        }
    
    broker = getattr(request.app.state, 'broker', None)
    if not broker:
        return {
            "status": "error",
            "message": "No broker connected",
        }
    
    try:
        # Get all positions from broker
        positions = broker.get_positions()
        
        if not positions:
            return {
                "status": "ok",
                "message": "No positions to liquidate",
                "closed": 0,
            }
        
        results = []
        closed = 0
        errors = 0
        
        for symbol, pos in positions.items():
            if pos.quantity <= 0:
                continue
                
            try:
                from uuid import uuid4
                order = broker.submit_order(
                    client_order_id=uuid4(),
                    symbol=symbol,
                    quantity=pos.quantity,
                    side="sell",
                    order_type="market",
                )
                closed += 1
                results.append({
                    "symbol": symbol,
                    "shares": pos.quantity,
                    "status": "submitted",
                    "order_id": order.broker_order_id,
                })
                logger.info(f"[Liquidate] Sold {pos.quantity} {symbol}")
            except Exception as e:
                errors += 1
                results.append({
                    "symbol": symbol,
                    "shares": pos.quantity,
                    "status": "error",
                    "error": str(e),
                })
                logger.error(f"[Liquidate] Failed to sell {symbol}: {e}")
        
        return {
            "status": "ok" if errors == 0 else "partial",
            "message": f"Liquidated {closed}/{len(positions)} positions",
            "closed": closed,
            "errors": errors,
            "results": results,
        }
        
    except Exception as e:
        logger.error(f"[Liquidate] Error: {e}")
        return {
            "status": "error",
            "message": str(e),
        }

