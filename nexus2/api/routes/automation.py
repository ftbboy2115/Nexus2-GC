"""
Automation Routes

API endpoints for controlling the automation engine.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal

from nexus2.domain.automation.engine import AutomationEngine, EngineConfig, EngineState
from nexus2.domain.automation.scheduler import AutomationScheduler
from nexus2.db import SessionLocal
from nexus2.db.repository import PositionRepository

import logging
logger = logging.getLogger(__name__)



router = APIRouter(prefix="/automation", tags=["automation"])


# Global instances (initialized in lifespan)
_engine: Optional[AutomationEngine] = None
_scheduler: Optional[AutomationScheduler] = None


def get_engine() -> AutomationEngine:
    """Get the automation engine instance."""
    if _engine is None:
        raise HTTPException(status_code=503, detail="Automation engine not initialized")
    return _engine


def set_engine(engine: AutomationEngine):
    """Set the automation engine instance."""
    global _engine
    _engine = engine


def get_scheduler() -> AutomationScheduler:
    """Get the automation scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutomationScheduler()
    return _scheduler


# Position monitor instance
_monitor: Optional["PositionMonitor"] = None


def get_monitor():
    """Get the position monitor instance."""
    global _monitor
    from nexus2.domain.automation.monitor import PositionMonitor
    if _monitor is None:
        _monitor = PositionMonitor()
    return _monitor


# App reference for accessing broker/market_data in background tasks
_app = None


def set_app(app):
    """Set the FastAPI app reference for background tasks."""
    global _app
    _app = app


def get_app():
    """Get the FastAPI app reference."""
    return _app


# Auto-start checker state
_auto_start_task = None
_auto_start_triggered_today = False


async def auto_start_checker():
    """
    Background task that checks if scheduler should auto-start.
    
    Runs every 60 seconds and checks:
    1. Is auto-start enabled?
    2. Is current time (ET) matching the configured start time?
    3. Is scheduler not already running?
    
    If all conditions met, starts the scheduler and sends Discord notification.
    """
    import asyncio
    from datetime import datetime
    import pytz
    
    global _auto_start_triggered_today
    
    et_tz = pytz.timezone('America/New_York')
    
    while True:
        try:
            # Get current ET time
            now_et = datetime.now(et_tz)
            current_time = now_et.strftime("%H:%M")
            
            
            # Reset trigger flag at midnight
            if current_time == "00:00":
                _auto_start_triggered_today = False
            
            # Skip if already triggered today
            if _auto_start_triggered_today:
                await asyncio.sleep(60)
                continue
            
            # Check scheduler settings
            from nexus2.db import SessionLocal
            from nexus2.db.repository import SchedulerSettingsRepository
            
            db = SessionLocal()
            try:
                repo = SchedulerSettingsRepository(db)
                settings = repo.get()
                
                
                # Check if auto-start is enabled and time matches
                if (settings.auto_start_enabled == "true" and 
                    settings.auto_start_time and
                    settings.auto_start_time == current_time):
                    
                    # Check if scheduler is not already running
                    scheduler = get_scheduler()
                    if not scheduler.is_running:
                        logger.info(f"[AutoStart] Time matched ({current_time} ET) - starting full automation")
                        print(f"🚀 [AutoStart] Starting full automation at {current_time} ET")
                        
                        # Start Engine first (sync method)
                        engine = get_engine()
                        if engine.state.name != "RUNNING":
                            engine.start()  # Sync, returns dict
                            print("[AutoStart] Engine started")
                        
                        # Start Monitor (async method)
                        monitor = get_monitor()
                        if not monitor._running:
                            await monitor.start()  # Async, returns dict
                            print("[AutoStart] Monitor started")
                        
                        # Configure scheduler with callbacks (same as manual UI start)
                        await _configure_and_start_scheduler(engine, scheduler)
                        print("[AutoStart] Scheduler started with full callbacks")
                        
                        _auto_start_triggered_today = True
                        
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
                        _auto_start_triggered_today = True
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[AutoStart] Checker error: {e}")
        
        await asyncio.sleep(60)


def start_auto_start_checker():
    """Start the auto-start checker background task."""
    global _auto_start_task
    import asyncio
    
    if _auto_start_task is None:
        _auto_start_task = asyncio.create_task(auto_start_checker())
        logger.info("[AutoStart] Checker started")
    return _auto_start_task


async def _configure_scanner_from_settings(engine, scheduler):
    """
    Configure engine scanner and scheduler settings from database.
    
    This is the shared scanner configuration logic used by both manual start
    and auto-start. Returns settings dict for logging/reference.
    
    Returns:
        dict with settings applied
    """
    from nexus2.domain.automation.services import create_unified_scanner_callback
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    
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
        
        # Set scheduler auto_execute flag
        scheduler.auto_execute = auto_execute
        
        # Configure engine scanner
        engine._scanner_func = await create_unified_scanner_callback(
            min_quality=min_quality,
            max_stop_percent=max_stop_percent,
            stop_mode=stop_mode,
            max_stop_atr=max_stop_atr,
            scan_modes=scan_modes,
            htf_frequency=htf_frequency,
        )
        
        settings_used = {
            "min_quality": min_quality,
            "stop_mode": stop_mode,
            "max_stop_atr": max_stop_atr,
            "max_stop_percent": max_stop_percent,
            "scan_modes": scan_modes,
            "htf_frequency": htf_frequency,
            "auto_execute": auto_execute,
        }
        
        logger.info(f"[Scheduler] Scanner configured: {settings_used}")
        
        return settings_used
    finally:
        db.close()


def _create_eod_callback(market_data, broker):
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
        from nexus2.db import SessionLocal, PositionRepository, PositionExitRepository
        from uuid import uuid4
        from datetime import datetime
        
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
        
        # Set callbacks and run
        job.set_callbacks(
            get_positions=get_positions,
            get_daily_close=get_daily_close,
            get_ema=get_ema,
            get_sma=get_sma,
            execute_exit=execute_exit,
        )
        
        result = await job.run(dry_run=False)  # Execute real exits
        
        return {
            "positions_checked": result.positions_checked,
            "exit_signals": len(result.exit_signals),
            "errors": len(result.errors),
        }
    
    return eod_callback


async def _configure_and_start_scheduler(engine, scheduler):
    """
    Configure scheduler with scan callback and start it.
    
    Used by auto-start for scan-only mode (no execute callback).
    For full functionality with execute/EOD callbacks, use manual start via UI.
    
    Returns:
        dict with scheduler start result
    """
    # Configure scanner from settings (shared logic)
    settings = await _configure_scanner_from_settings(engine, scheduler)
    
    # Get broker from app state for execute callback
    app = get_app()
    broker = getattr(app.state, 'broker', None) if app else None
    market_data = getattr(app.state, 'market_data', None) if app else None
    
    # Use auto_execute from settings (for full autonomous operation)
    auto_execute = settings.get("auto_execute", False)
    scheduler.auto_execute = auto_execute if broker else False
    
    # Set up scan callback
    async def scan_callback():
        return await engine.run_scan_cycle()
    
    # Set up execute callback if broker is available
    execute_callback = None
    if broker and auto_execute:
        from nexus2.db import SessionLocal, PositionRepository, SchedulerSettingsRepository
        from uuid import uuid4
        from datetime import datetime
        from decimal import Decimal
        
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
                        
                        # Submit bracket order
                        from nexus2.domain.orders.models import OrderSide
                        result = broker.submit_bracket_order(
                            symbol=signal.symbol,
                            side=OrderSide.BUY,
                            qty=shares,
                            stop_price=float(signal.stop_price),
                            take_profit_price=None,  # No TP for KK style
                        )
                        
                        if result and result.is_accepted:
                            # Create position record
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
                            })
                            executed.append({"symbol": signal.symbol, "shares": shares})
                            print(f"✅ [AutoExec] Executed: {signal.symbol} x {shares}")
                        else:
                            errors.append({"symbol": signal.symbol, "error": "order_rejected"})
                    finally:
                        db.close()
                except Exception as e:
                    errors.append({"symbol": signal.symbol, "error": str(e)})
                    logger.error(f"[AutoExec] Error executing {signal.symbol}: {e}")
            
            print(f"🤖 [AutoExec] Cycle complete: {len(executed)} executed, {len(skipped)} skipped, {len(errors)} errors")
            return {"executed": executed, "skipped": skipped, "errors": errors}
        
        logger.info("[Scheduler] Auto-start: FULL AUTONOMOUS MODE (execute callback enabled)")
    else:
        logger.info("[Scheduler] Auto-start: scan-only mode (no broker or auto_execute disabled)")
    
    # Create EOD callback using shared helper (for 3:45 PM MA trailing stop check)
    eod_callback = _create_eod_callback(market_data, broker)
    
    # Set callbacks (scan + optional execute + EOD)
    scheduler.set_callbacks(scan_callback, execute_callback, eod_callback)
    
    # Start scheduler
    result = await scheduler.start()
    
    return result


# Request/Response models
class StartRequest(BaseModel):
    sim_only: bool = True  # Default to SIM mode
    scanner_interval: int = 15  # minutes
    min_quality: int = 7
    max_positions: int = 5
    risk_per_trade: Optional[float] = None  # If None, reads from main settings
    daily_loss_limit: float = 1000.0
    max_capital: float = 10000.0  # Maximum capital for automation


class EngineStatusResponse(BaseModel):
    state: str
    sim_only: bool
    is_market_hours: bool
    config: dict
    stats: dict


class ActionResponse(BaseModel):
    status: str
    message: Optional[str] = None


@router.get("/status", response_model=dict)
async def get_status(
    request: Request,
    engine: AutomationEngine = Depends(get_engine),
):
    """Get current automation engine status including trading mode."""
    from nexus2.api.routes.settings import get_settings
    
    status = engine.get_status()
    settings = get_settings()
    
    # Add broker and trading mode info
    broker = getattr(request.app.state, 'broker', None)
    
    # Use Dashboard naming convention
    broker_display_map = {
        "paper": "📄 Paper (Local)",
        "alpaca_paper": "🅰️ Alpaca Paper",
        "alpaca_live": "🔥 Alpaca Live",
    }
    broker_display = broker_display_map.get(settings.broker_type, settings.broker_type)
    
    # Add account if using Alpaca
    if settings.broker_type.startswith("alpaca"):
        broker_display = f"{broker_display} [{settings.active_account}]"
    
    # Determine trading mode
    if engine.config.sim_only:
        trading_mode = "SIM"
        mode_description = "Simulation - No real orders"
    elif broker:
        trading_mode = "LIVE"
        mode_description = f"Live trading via {broker_display}"
    else:
        trading_mode = "SIM"
        mode_description = "No broker configured"
    
    return {
        **status,
        "trading_mode": trading_mode,
        "mode_description": mode_description,
        "broker_available": broker is not None,
        "broker_type": settings.broker_type,
        "broker_display": broker_display,
        "active_account": settings.active_account,
        "settings_risk_per_trade": settings.risk_per_trade,
        "settings_max_per_symbol": settings.max_per_symbol,
        "settings_max_positions": settings.max_positions,
    }


@router.post("/start", response_model=ActionResponse)
async def start_engine(
    request: StartRequest = StartRequest(),
    engine: AutomationEngine = Depends(get_engine),
):
    """Start the automation engine."""
    from nexus2.domain.automation.services import create_unified_scanner_callback
    from nexus2.api.routes.settings import get_settings
    
    # Get main settings
    main_settings = get_settings()
    
    # Update config from request
    engine.config.sim_only = request.sim_only
    engine.config.scanner_interval_minutes = request.scanner_interval
    engine.config.min_quality_score = request.min_quality
    engine.config.max_positions = request.max_positions
    engine.config.daily_loss_limit = Decimal(str(request.daily_loss_limit))
    engine.config.max_capital = Decimal(str(request.max_capital))
    
    # Risk per trade: use request value if provided, otherwise read from main settings
    if request.risk_per_trade is not None:
        engine.config.risk_per_trade = Decimal(str(request.risk_per_trade))
    else:
        engine.config.risk_per_trade = Decimal(str(main_settings.risk_per_trade))
    
    # Set up scanner callback - use unified scanner for real EP/Breakout/HTF scans
    engine._scanner_func = await create_unified_scanner_callback(
        min_quality=engine.config.min_quality_score,
        max_stop_percent=engine.config.max_stop_percent,
    )
    
    result = engine.start()
    
    return ActionResponse(
        status=result["status"],
        message=f"Engine started in {'SIM' if request.sim_only else 'LIVE'} mode (risk: ${engine.config.risk_per_trade})"
    )


@router.post("/stop", response_model=ActionResponse)
async def stop_engine(engine: AutomationEngine = Depends(get_engine)):
    """Stop the automation engine."""
    result = engine.stop()
    return ActionResponse(status=result["status"], message="Engine stopped")


@router.get("/api-stats", response_model=dict)
async def get_api_stats():
    """
    Get API rate limit statistics.
    
    Returns current FMP API usage including calls/minute, remaining, and usage%.
    """
    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
    
    try:
        fmp = get_fmp_adapter()
        stats = fmp.get_rate_stats()
        return {
            "status": "ok",
            "provider": "FMP",
            **stats,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "calls_this_minute": 0,
            "limit_per_minute": 300,
            "remaining": 300,
            "usage_percent": 0,
        }


@router.post("/pause", response_model=ActionResponse)
async def pause_engine(engine: AutomationEngine = Depends(get_engine)):
    """Pause the automation engine."""
    result = engine.pause()
    return ActionResponse(status=result["status"])


@router.post("/resume", response_model=ActionResponse)
async def resume_engine(engine: AutomationEngine = Depends(get_engine)):
    """Resume the automation engine."""
    result = engine.resume()
    return ActionResponse(status=result["status"])


@router.post("/scan", response_model=dict)
async def trigger_scan(engine: AutomationEngine = Depends(get_engine)):
    """Manually trigger a scanner cycle (for testing)."""
    if engine.state != EngineState.RUNNING:
        # Allow manual scan even when stopped for testing
        pass
    
    signals = await engine.run_scan_cycle()
    
    return {
        "signals_count": len(signals),
        "signals": [
            {
                "symbol": s.symbol,
                "setup_type": s.setup_type.value,
                "quality_score": s.quality_score,
                "entry_price": str(s.entry_price),
                "tactical_stop": str(s.tactical_stop),
                "stop_percent": round(s.stop_percent, 2),
                "shares": s.calculate_shares(engine.config.risk_per_trade),
            }
            for s in signals
        ]
    }


class ScanAllRequest(BaseModel):
    """Request for unified scan across all scanners."""
    modes: list[str] = ["all"]  # "all", "ep", "breakout", "htf"
    min_quality: int = 7
    stop_mode: str = "atr"  # "atr" (KK-style) or "percent"
    max_stop_atr: float = 1.0  # KK uses 1.0-1.5 ATR
    max_stop_percent: float = 5.0  # Fallback for percent mode


@router.post("/scan-all", response_model=dict)
async def scan_all(
    request: ScanAllRequest = ScanAllRequest(),
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Unified scan across all scanners (EP, Breakout, HTF).
    
    Returns deduplicated signals sorted by quality score.
    This is the recommended endpoint for full automation.
    
    Args:
        modes: List of scanners to run. Options: "all", "ep", "breakout", "htf"
        min_quality: Minimum quality score (1-10) to include signals
        max_stop_percent: Maximum stop distance as percentage
    """
    from nexus2.domain.automation.unified_scanner import (
        UnifiedScannerService,
        UnifiedScanSettings,
        ScanMode,
    )
    
    # Convert mode strings to ScanMode enum
    mode_map = {
        "all": ScanMode.ALL,
        "ep": ScanMode.EP_ONLY,
        "breakout": ScanMode.BREAKOUT_ONLY,
        "htf": ScanMode.HTF_ONLY,
    }
    modes = [mode_map.get(m.lower(), ScanMode.ALL) for m in request.modes]
    
    # Create scanner with request settings
    settings = UnifiedScanSettings(
        modes=modes,
        min_quality_score=request.min_quality,
        stop_mode=request.stop_mode,
        max_stop_atr=request.max_stop_atr,
        max_stop_percent=request.max_stop_percent,
    )
    scanner = UnifiedScannerService(settings=settings)
    
    # Run unified scan
    result = scanner.scan(verbose=False)
    
    # Update engine stats
    engine.stats.scans_run += 1
    engine.stats.signals_generated += result.total_signals
    
    return {
        "status": "success",
        "total_signals": result.total_signals,
        "breakdown": {
            "ep": result.ep_count,
            "breakout": result.breakout_count,
            "htf": result.htf_count,
        },
        "total_processed": result.total_processed,
        "scan_duration_ms": result.scan_duration_ms,
        "scanned_at": result.scanned_at.isoformat(),
        "signals": [
            {
                "symbol": s.symbol,
                "setup_type": s.setup_type.value,
                "quality_score": s.quality_score,
                "tier": s.tier,
                "entry_price": str(s.entry_price),
                "tactical_stop": str(s.tactical_stop),
                "stop_percent": round(s.stop_percent, 2),
                "rs_percentile": s.rs_percentile,
                "shares": s.calculate_shares(engine.config.risk_per_trade),
                "risk_amount": str(engine.config.risk_per_trade),
            }
            for s in result.signals
        ]
    }


class ExecuteRequest(BaseModel):
    symbol: str
    shares: int
    stop_price: float
    setup_type: str = "ep"
    dry_run: bool = True  # Default to dry run for safety


@router.post("/execute", response_model=dict)
async def execute_signal(
    request: ExecuteRequest,
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Execute a trade based on a signal.
    
    If dry_run=True (default), returns what WOULD happen without executing.
    """
    from decimal import Decimal
    
    if request.dry_run:
        # Calculate position value
        position_value = request.shares * request.stop_price * 1.03  # Estimated entry
        risk = request.shares * (request.stop_price * 1.03 - request.stop_price)
        
        return {
            "status": "dry_run",
            "would_execute": {
                "symbol": request.symbol,
                "shares": request.shares,
                "estimated_entry": round(request.stop_price * 1.03, 2),
                "stop_price": request.stop_price,
                "position_value": round(position_value, 2),
                "risk_amount": round(risk, 2),
            },
            "message": "Set dry_run=false to execute for real"
        }
    
    # Real execution - check engine state
    if not engine.config.sim_only:
        return {
            "status": "blocked",
            "error": "LIVE mode not enabled. Start engine with sim_only=false for live trading."
        }
    
    # For now, just return success (actual broker integration later)
    return {
        "status": "submitted",
        "symbol": request.symbol,
        "shares": request.shares,
        "stop_price": request.stop_price,
        "message": "Order submitted (SIM mode)"
    }


@router.post("/scan_and_execute", response_model=dict)
async def scan_and_execute(
    request: Request,
    dry_run: bool = True,
    max_trades: int = 1,
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Full automation: scan for signals and execute the best ones.
    
    Args:
        dry_run: If True, shows what WOULD happen without executing
        max_trades: Maximum number of trades to execute
    """
    # Run scan
    signals = await engine.run_scan_cycle()
    
    if not signals:
        return {
            "status": "no_signals",
            "message": "No valid signals found"
        }
    
    # Read fresh settings (allows dynamic risk changes)
    from nexus2.api.routes.settings import get_settings
    settings = get_settings()
    risk_per_trade = Decimal(str(settings.risk_per_trade))
    max_per_symbol = Decimal(str(settings.max_per_symbol))
    
    # Filter to top signals that we can open
    tradeable = []
    for signal in signals[:max_trades]:
        if engine.can_open_position():
            # Calculate shares from risk
            shares = signal.calculate_shares(risk_per_trade)
            
            # Cap shares based on max_per_symbol
            if signal.entry_price > 0:
                max_shares_from_cap = int(max_per_symbol / signal.entry_price)
                if shares > max_shares_from_cap:
                    shares = max_shares_from_cap
            
            if shares >= 1:
                position_value = shares * signal.entry_price
                tradeable.append({
                    "symbol": signal.symbol,
                    "quality": signal.quality_score,
                    "shares": shares,
                    "entry_price": str(signal.entry_price),
                    "stop_price": str(signal.tactical_stop),
                    "setup_type": signal.setup_type.value,
                    "risk": str(risk_per_trade),
                    "position_value": str(position_value),
                })
    
    if dry_run:
        return {
            "status": "dry_run",
            "signals_found": len(signals),
            "would_trade": tradeable,
            "message": "Set dry_run=false to execute for real"
        }
    
    # Get broker from app state
    broker = getattr(request.app.state, 'broker', None)
    
    # Execute trades
    from nexus2.db import SessionLocal, PositionRepository, OrderRepository
    from uuid import uuid4
    from datetime import datetime
    
    executed = []
    errors = []
    skipped = []  # Candidates that failed validation
    
    # Initialize validator for pre-trade checks
    from nexus2.domain.automation.validation import validate_before_order
    
    for trade in tradeable:
        try:
            # Pre-trade validation: fresh quote + catalyst check for EP
            validation = validate_before_order(
                symbol=trade["symbol"],
                scanned_price=float(trade["entry_price"]),
                setup_type=trade["setup_type"],
            )
            
            if not validation.is_valid:
                skipped.append({
                    "symbol": trade["symbol"],
                    "reasons": validation.reasons,
                    "current_price": str(validation.current_price) if validation.current_price else None,
                })
                continue  # Skip this trade
            
            # Log any warnings even if valid
            if validation.reasons:
                print(f"[Automation] {trade['symbol']} warnings: {validation.reasons}")
            
            db = SessionLocal()
            try:
                order_repo = OrderRepository(db)
                position_repo = PositionRepository(db)
                
                order_id = str(uuid4())
                position_id = str(uuid4())
                
                # If we have a real broker and NOT in sim_only mode, submit to broker
                if broker and not engine.config.sim_only:
                    try:
                        from uuid import UUID
                        from decimal import Decimal
                        
                        # Submit market order to broker
                        broker_order = broker.submit_order(
                            client_order_id=UUID(order_id),
                            symbol=trade["symbol"],
                            side="buy",
                            quantity=trade["shares"],
                            order_type="market",
                        )
                        
                        # Create order record with broker info
                        order = order_repo.create({
                            "id": order_id,
                            "symbol": trade["symbol"],
                            "side": "buy",
                            "quantity": trade["shares"],
                            "order_type": "market",
                            "status": broker_order.status.value,
                            "limit_price": trade["entry_price"],
                            "avg_fill_price": str(broker_order.avg_fill_price) if broker_order.avg_fill_price else trade["entry_price"],
                            "filled_quantity": broker_order.filled_quantity,
                            "created_at": datetime.utcnow(),
                        })
                        
                        fill_status = broker_order.status.value
                        
                    except Exception as broker_err:
                        errors.append({"symbol": trade["symbol"], "error": f"Broker error: {broker_err}"})
                        continue
                else:
                    # SIM mode - instant fill
                    order = order_repo.create({
                        "id": order_id,
                        "symbol": trade["symbol"],
                        "side": "buy",
                        "quantity": trade["shares"],
                        "order_type": "market",
                        "status": "filled",
                        "limit_price": trade["entry_price"],
                        "avg_fill_price": trade["entry_price"],
                        "filled_quantity": trade["shares"],
                        "created_at": datetime.utcnow(),
                    })
                    fill_status = "filled"
                
                # Create position record
                position = position_repo.create({
                    "id": position_id,
                    "symbol": trade["symbol"],
                    "setup_type": trade["setup_type"],
                    "status": "open",
                    "entry_price": trade["entry_price"],
                    "shares": trade["shares"],
                    "remaining_shares": trade["shares"],
                    "initial_stop": trade["stop_price"],
                    "current_stop": trade["stop_price"],
                    "realized_pnl": "0",
                    "opened_at": datetime.utcnow(),
                })
                
                executed.append({
                    **trade,
                    "status": fill_status,
                    "order_id": order_id,
                    "position_id": position_id,
                    "mode": "LIVE" if (broker and not engine.config.sim_only) else "SIM",
                })
                engine.stats.orders_submitted += 1
                if fill_status == "filled":
                    engine.stats.orders_filled += 1
                
            finally:
                db.close()
                
        except Exception as e:
            errors.append({
                "symbol": trade["symbol"],
                "error": str(e),
            })
    
    return {
        "status": "executed",
        "trades": executed,
        "skipped": skipped if skipped else None,  # Candidates that failed validation
        "errors": errors if errors else None,
    }


# ==================== SCHEDULER ENDPOINTS ====================

class SchedulerStartRequest(BaseModel):
    interval_minutes: int = 15
    auto_execute: bool = False  # Default to scan-only


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
    import logging
    logger = logging.getLogger(__name__)
    
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
    settings = await _configure_scanner_from_settings(engine, scheduler)
    auto_execute = settings["auto_execute"]
    
    print(f"🔧 [Scheduler] Scanner configured: {settings}")
    
    # Set up callbacks
    async def scan_callback():
        return await engine.run_scan_cycle()

    
    async def execute_callback():
        """
        Execute top signal using broker bracket orders.
        
        Safety checks:
        - Position limit (max_positions)
        - Daily loss limit
        - SIM mode enforcement
        """
        from nexus2.db import SessionLocal, PositionRepository, SchedulerSettingsRepository
        from nexus2.domain.automation.services import create_unified_scanner_callback
        from uuid import uuid4
        from datetime import datetime
        from decimal import Decimal
        
        print(f"🤖 [AutoExec] Starting execute_callback...")
        
        # =============================
        # DYNAMIC SETTINGS RELOAD
        # Read fresh settings each cycle so changes take effect immediately
        # =============================
        db_settings = SessionLocal()
        try:
            settings_repo = SchedulerSettingsRepository(db_settings)
            sched_settings = settings_repo.get()
            
            min_quality = sched_settings.min_quality
            stop_mode = sched_settings.stop_mode or "atr"
            max_stop_atr = float(sched_settings.max_stop_atr) if sched_settings.max_stop_atr else 1.0
            max_stop_percent = float(sched_settings.max_stop_percent) if sched_settings.max_stop_percent else 5.0
            scan_modes = sched_settings.scan_modes.split(",") if sched_settings.scan_modes else ["ep", "breakout", "htf"]
            htf_frequency = sched_settings.htf_frequency or "every_cycle"
            
            # Reconfigure engine scanner with fresh settings
            engine._scanner_func = await create_unified_scanner_callback(
                min_quality=min_quality,
                max_stop_percent=max_stop_percent,
                stop_mode=stop_mode,
                max_stop_atr=max_stop_atr,
                scan_modes=scan_modes,
                htf_frequency=htf_frequency,
            )
            print(f"🔄 [AutoExec] Reloaded settings: min_quality={min_quality}, stop_mode={stop_mode}")
        finally:
            db_settings.close()
        
        # Run scan to get signals (with timing)
        import time
        scan_start = time.time()
        signals = await engine.run_scan_cycle()
        scan_duration = time.time() - scan_start
        print(f"🤖 [AutoExec] Scan returned {len(signals) if signals else 0} signals (took {scan_duration:.1f}s)")
        
        # Log summary of all signals received for diagnostics
        if signals:
            print("📋 [AutoExec] Signal Summary:")
            for i, sig in enumerate(signals[:10], 1):
                setup_name = sig.setup_type.value if hasattr(sig.setup_type, 'value') else str(sig.setup_type)
                print(f"   {i}. {sig.symbol:6} | Score: {sig.quality_score} | Type: {setup_name:8} | Mode: {sig.scanner_mode} | Tier: {sig.tier}")
        
        if not signals:
            logger.info("[AutoExec] No signals from scan")
            print("🤖 [AutoExec] No signals found - returning")
            return {"status": "no_signals"}
        
        # =============================
        # PROCESS ALL QUALIFIED SIGNALS
        # Execute up to max_trades_per_cycle (cap at 10 for safety)
        # =============================
        MAX_TRADES_PER_CYCLE = 10
        
        from nexus2.api.routes.settings import get_settings
        from nexus2.db import SessionLocal, SchedulerSettingsRepository
        
        settings = get_settings()
        
        # Check scheduler-specific max_position_value first, fall back to global
        scheduler_max = None
        try:
            db = SessionLocal()
            scheduler_settings = SchedulerSettingsRepository(db).get()
            if scheduler_settings.max_position_value:
                scheduler_max = Decimal(scheduler_settings.max_position_value)
                print(f"📐 [AutoExec] Using scheduler max_position_value: ${scheduler_max}")
            db.close()
        except Exception as e:
            logger.warning(f"[AutoExec] Could not read scheduler settings: {e}")
        
        max_per_symbol = scheduler_max if scheduler_max else Decimal(str(settings.max_per_symbol))
        
        # Get existing positions from Alpaca to avoid adding to existing positions
        existing_symbols = set()
        if broker:
            try:
                positions = broker.get_positions()
                # get_positions() returns Dict[str, BrokerPosition] - keys ARE the symbols
                existing_symbols = {symbol.upper() for symbol in positions.keys()}
                if existing_symbols:
                    print(f"📍 [AutoExec] Already holding: {', '.join(sorted(existing_symbols))}")
            except Exception as e:
                logger.warning(f"[AutoExec] Could not fetch positions: {e}")
        
        executed = []
        skipped = []
        errors = []
        
        for signal in signals[:MAX_TRADES_PER_CYCLE]:
            # Skip if we already hold this symbol (no adds on existing - KK-style)
            if signal.symbol.upper() in existing_symbols:
                print(f"⏭️ [AutoExec] Skipping {signal.symbol} - already holding position")
                skipped.append({"symbol": signal.symbol, "reason": "Already holding position"})
                continue
            
            # Safety check: Can we open a new position?
            if not engine.can_open_position():
                logger.warning(f"[AutoExec] Position limit reached, stopping at {len(executed)} trades")
                break
            
            # Calculate position size based on risk
            shares = signal.calculate_shares(engine.config.risk_per_trade)
            
            # Cap position size to max_per_symbol setting
            if signal.entry_price > 0:
                max_shares_from_cap = int(max_per_symbol / signal.entry_price)
                if shares > max_shares_from_cap:
                    print(f"🔒 [AutoExec] Capping {signal.symbol} shares from {shares} to {max_shares_from_cap} (max ${max_per_symbol})")
                    shares = max_shares_from_cap
            
            if shares < 1:
                logger.warning(f"[AutoExec] Position too small for {signal.symbol}: {shares} shares")
                skipped.append({"symbol": signal.symbol, "reason": "Position size < 1 share"})
                continue
            
            # Check if broker is available
            if broker is None:
                logger.error("[AutoExec] No broker configured!")
                return {"status": "failed", "error": "No broker configured", "executed": executed}
            
            # Submit bracket order through broker
            try:
                client_order_id = uuid4()
                stop_price = Decimal(str(signal.tactical_stop))
                
                # Log signal details for diagnostics
                setup_name = signal.setup_type.value if hasattr(signal.setup_type, 'value') else str(signal.setup_type)
                print(f"📊 [AutoExec] Signal: {signal.symbol} | Score: {signal.quality_score} | Type: {setup_name} | Mode: {signal.scanner_mode} | Tier: {signal.tier}")
                print(f"🤖 [AutoExec] Submitting bracket order: {signal.symbol} x {shares} @ stop ${stop_price}")
                
                result = broker.submit_bracket_order(
                    client_order_id=client_order_id,
                    symbol=signal.symbol,
                    quantity=shares,
                    stop_loss_price=stop_price,
                )
            except Exception as e:
                logger.error(f"[AutoExec] Bracket order failed for {signal.symbol}: {e}")
                errors.append({"symbol": signal.symbol, "error": str(e)})
                continue
            
            # Check if order was accepted
            if result and result.status.value in ("accepted", "filled", "pending"):
                # Create position record
                db = SessionLocal()
                try:
                    position_repo = PositionRepository(db)
                    position = position_repo.create({
                        "id": str(uuid4()),
                        "symbol": signal.symbol,
                        "setup_type": signal.setup_type.value,
                        "status": "open",
                        "entry_price": str(result.avg_fill_price or result.limit_price or signal.entry_price),
                        "shares": shares,
                        "remaining_shares": shares,
                        "initial_stop": str(stop_price),
                        "current_stop": str(stop_price),
                        "realized_pnl": "0",
                        "opened_at": datetime.utcnow(),
                    })
                    
                    # Update engine stats
                    engine.stats.orders_submitted += 1
                    engine.stats.orders_filled += 1
                    
                    logger.info(f"[AutoExec] SUCCESS: {signal.symbol} x {shares} @ stop ${stop_price}")
                    print(f"✅ [AutoExec] Executed: {signal.symbol} x {shares}")
                    
                    executed.append({
                        "symbol": signal.symbol,
                        "shares": shares,
                        "stop_price": float(stop_price),
                        "order_id": str(result.broker_order_id),
                        "position_id": position.id,
                    })
                finally:
                    db.close()
            else:
                logger.error(f"[AutoExec] Order not accepted for {signal.symbol}: {result}")
                errors.append({"symbol": signal.symbol, "error": "Order not accepted by broker"})
        
        print(f"🤖 [AutoExec] Cycle complete: {len(executed)} executed, {len(skipped)} skipped, {len(errors)} errors")
        
        return {
            "status": "executed" if executed else "no_trades",
            "executed": executed,
            "skipped": skipped if skipped else None,
            "errors": errors if errors else None,
        }
    
    # EOD callback using shared helper (avoids code duplication)
    eod_callback = _create_eod_callback(market_data, broker)
    
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
    from nexus2.domain.automation.monitor import PositionMonitor
    from nexus2.api.routes.settings import get_settings
    
    global _monitor
    saved_settings = get_settings()
    
    _monitor = PositionMonitor(
        check_interval_seconds=60,  # Check every minute
        kk_style_partials=True,
        partial_exit_days=saved_settings.partial_exit_days,
        partial_exit_fraction=saved_settings.partial_exit_fraction,
    )
    
    # Callback: Get open positions
    async def get_monitor_positions():
        db = SessionLocal()
        try:
            position_repo = PositionRepository(db)
            positions = position_repo.get_open()
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
        finally:
            db.close()
    
    # Callback: Get current price
    async def get_monitor_price(symbol: str):
        if market_data:
            try:
                quote = market_data.get_quote(symbol)
                if quote:
                    return quote.price if hasattr(quote, 'price') else quote.close
            except Exception:
                pass
        return None
    
    # Callback: Update stop (move to breakeven)
    async def update_stop(position_id: str, new_stop_price):
        db = SessionLocal()
        try:
            position_repo = PositionRepository(db)
            position_repo.update(position_id, {
                "current_stop": str(new_stop_price),
                "partial_taken": True,  # Mark partial as taken
            })
            logger.info(f"[Monitor] Updated stop for {position_id} to ${new_stop_price}")
        finally:
            db.close()
    
    # Callback: Execute exit
    async def execute_monitor_exit(signal):
        if broker and not engine.config.sim_only:
            # Submit market sell order
            try:
                result = broker.submit_order(
                    symbol=signal.symbol,
                    quantity=signal.shares_to_exit,
                    side="sell",
                    order_type="market",
                )
                logger.info(f"[Monitor] Exit executed: {signal.symbol} x {signal.shares_to_exit}")
            except Exception as e:
                logger.error(f"[Monitor] Exit failed: {e}")
    
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
        "auto_execute": req.auto_execute,
        "broker_connected": broker is not None,
        "monitor_running": True,
    }


@router.post("/scheduler/stop", response_model=dict)
async def stop_scheduler(
    engine: AutomationEngine = Depends(get_engine),
):
    """Stop the background scheduler, engine, and position monitor."""
    global _monitor
    
    scheduler = get_scheduler()
    result = await scheduler.stop()
    
    # Also stop the engine
    engine.stop()
    logger.info("[Scheduler] Engine stopped")
    
    # Also stop the position monitor
    if _monitor:
        await _monitor.stop()
        logger.info("[Scheduler] PositionMonitor stopped")
    
    return {**result, "engine_stopped": True, "monitor_stopped": True}


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
    from dataclasses import asdict
    
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



class SchedulerToggleRequest(BaseModel):
    auto_execute: bool


@router.patch("/scheduler/auto-execute", response_model=dict)
async def toggle_auto_execute(req: SchedulerToggleRequest):
    """Toggle auto_execute on the scheduler and persist to database."""
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    
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


class SchedulerIntervalRequest(BaseModel):
    interval_minutes: int


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

class SchedulerSettingsRequest(BaseModel):
    """Request model for updating scheduler settings."""
    adopt_quick_actions: Optional[bool] = None
    preset: Optional[str] = None  # strict, relaxed, custom
    min_quality: Optional[int] = None
    stop_mode: Optional[str] = None  # atr or percent
    max_stop_atr: Optional[float] = None
    max_stop_percent: Optional[float] = None
    scan_modes: Optional[List[str]] = None  # ["ep", "breakout", "htf"]
    htf_frequency: Optional[str] = None  # every_cycle or market_open
    max_position_value: Optional[float] = None  # Automation-specific capital limit per position
    auto_start_enabled: Optional[bool] = None  # Enable auto-start for headless operation
    auto_start_time: Optional[str] = None  # HH:MM format (ET timezone)
    auto_execute: Optional[bool] = None  # Enable auto-execute for autonomous trading


# Preset definitions for scheduler (same as Quick Actions)
SCHEDULER_PRESETS = {
    "strict": {
        "min_quality": 7,
        "stop_mode": "atr",
        "max_stop_atr": 1.0,
        "max_stop_percent": 5.0,
    },
    "relaxed": {
        "min_quality": 5,
        "stop_mode": "percent",
        "max_stop_atr": 1.5,
        "max_stop_percent": 8.0,
    },
}


@router.get("/scheduler/settings", response_model=dict)
async def get_scheduler_settings():
    """
    Get current scheduler settings.
    
    Returns the configuration used for scheduled scans (separate from Quick Actions).
    """
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    
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
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    
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
                      "max_position_value", "auto_start_enabled", "auto_start_time", "auto_execute"]:
            value = getattr(req, field, None)
            if value is not None:
                # Convert numeric to string for DB storage
                if field in ["max_stop_atr", "max_stop_percent", "max_position_value"]:
                    updates[field] = str(value)
                elif field in ["auto_start_enabled", "auto_execute"]:
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



class MonitorStartRequest(BaseModel):
    check_interval_seconds: int = 60
    enable_trailing_stops: bool = True
    enable_partial_exits: bool = True


@router.post("/monitor/start", response_model=dict)
async def start_monitor(
    request: MonitorStartRequest = MonitorStartRequest(),
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Start position monitoring.
    
    Monitors open positions for:
    - Stop-loss hits
    - Trailing stop adjustments (at 1R)
    - Partial exit opportunities (at 2R)
    """
    monitor = get_monitor()
    
    # Configure
    monitor.check_interval = request.check_interval_seconds
    monitor.enable_trailing_stops = request.enable_trailing_stops
    monitor.enable_partial_exits = request.enable_partial_exits
    
    # Get positions callback
    from nexus2.db import SessionLocal, PositionRepository
    
    def get_positions():
        db = SessionLocal()
        try:
            repo = PositionRepository(db)
            positions = repo.get_open()
            return [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "entry_price": p.entry_price,
                    "initial_stop": p.initial_stop,
                    "current_stop": p.current_stop,
                    "remaining_shares": p.remaining_shares,
                }
                for p in positions
            ]
        finally:
            db.close()
    
    # Get price callback (uses FMP or returns mock for demo)
    async def get_price(symbol: str):
        try:
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            fmp = get_fmp_adapter()
            quote = fmp.get_quote(symbol)
            if quote:
                return quote.price
        except Exception as e:
            pass
        # Fallback - return None (monitor will skip)
        return None
    
    # Execute exit callback
    async def execute_exit(signal):
        from nexus2.db import SessionLocal, PositionRepository, PositionExitRepository
        from datetime import datetime
        from decimal import Decimal
        
        db = SessionLocal()
        try:
            position_repo = PositionRepository(db)
            exit_repo = PositionExitRepository(db)
            
            # Record exit
            from uuid import uuid4 as gen_uuid
            exit_repo.create({
                "id": str(gen_uuid()),
                "position_id": signal.position_id,
                "shares": signal.shares_to_exit,
                "exit_price": str(signal.exit_price),
                "reason": signal.reason.value,
                "exited_at": datetime.utcnow(),
            })
            
            # Update position
            position = position_repo.get_by_id(signal.position_id)
            if position:
                new_remaining = position.remaining_shares - signal.shares_to_exit
                updates = {
                    "remaining_shares": new_remaining,
                }
                if new_remaining <= 0:
                    updates["status"] = "closed"
                    updates["closed_at"] = datetime.utcnow()
                    updates["realized_pnl"] = str(signal.pnl_estimate)
                
                position_repo.update(signal.position_id, updates)
            
            return {"status": "executed", "symbol": signal.symbol}
        finally:
            db.close()
    
    monitor.set_callbacks(get_positions, get_price, execute_exit)
    
    result = await monitor.start()
    return result


@router.post("/monitor/stop", response_model=dict)
async def stop_monitor():
    """Stop position monitoring."""
    monitor = get_monitor()
    return await monitor.stop()


@router.get("/monitor/status", response_model=dict)
async def get_monitor_status():
    """Get current monitor status."""
    monitor = get_monitor()
    return monitor.get_status()


@router.post("/monitor/check", response_model=dict)
async def manual_check():
    """Manually trigger a position check (for testing)."""
    monitor = get_monitor()
    await monitor._check_positions()
    return {
        "status": "checked",
        "checks_run": monitor.checks_run,
        "exits_triggered": monitor.exits_triggered,
    }


# ==================== POSITIONS ENDPOINTS ====================

@router.get("/positions", response_model=dict)
async def get_broker_positions(request: Request):
    """
    Get positions from the connected broker (Alpaca).
    
    Returns all open positions with current P&L.
    This shows actual positions, not session-based engine stats.
    """
    broker = getattr(request.app.state, 'broker', None)
    
    if broker is None:
        return {
            "status": "no_broker",
            "message": "No broker configured",
            "positions": [],
        }
    
    try:
        positions_dict = broker.get_positions()
        
        # Convert to list format for frontend
        positions_list = []
        total_value = 0
        total_pnl = 0
        
        for symbol, pos in positions_dict.items():
            market_value = float(pos.market_value) if pos.market_value else 0
            unrealized_pnl = float(pos.unrealized_pnl) if pos.unrealized_pnl else 0
            
            positions_list.append({
                "symbol": pos.symbol,
                "qty": pos.quantity,
                "avg_price": float(pos.avg_price),
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "pnl_percent": (unrealized_pnl / (float(pos.avg_price) * pos.quantity) * 100) 
                              if pos.avg_price and pos.quantity else 0,
            })
            
            total_value += market_value
            total_pnl += unrealized_pnl
        
        # Sort by P&L (best performers first)
        positions_list.sort(key=lambda p: p["unrealized_pnl"], reverse=True)
        
        return {
            "status": "ok",
            "positions": positions_list,
            "count": len(positions_list),
            "total_value": total_value,
            "total_pnl": total_pnl,
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "positions": [],
        }

# ==================== MA CHECK ENDPOINTS (KK TRAILING) ====================

class MACheckRequest(BaseModel):
    """Request for MA check job."""
    dry_run: bool = True  # Default to dry run for safety
    min_days: int = 5  # Start MA trailing after day 5
    ma_type: str = "auto"  # auto (default), ema_10, ema_20, sma_10, sma_20, lower_10, lower_20
    require_timing_window: bool = False  # If True, only run 3:45-4:00 PM ET


@router.post("/ma-check", response_model=dict)
async def run_ma_check(
    request: Request,
    req: MACheckRequest = MACheckRequest(),
):
    """
    Run end-of-day MA check for trailing stops (KK-style).
    
    Checks all open positions that are 5+ days old against their
    selected MA daily close. Exits positions closing below the MA.
    
    Should be run during last 15 min of market (3:45-4:00 PM ET)
    so that exits can be submitted as market orders before close.
    
    MA types:
    - auto: Auto-select based on ADR% (DEFAULT, KK-style - uses lower_10 for >5% ADR, lower_20 for <5%)
    - ema_10: 10 EMA (fast movers)
    - ema_20: 20 EMA (slower stocks)
    - sma_10: 10 SMA
    - sma_20: 20 SMA
    - lower_10: Lower of 10 EMA and 10 SMA (tight trailing)
    - lower_20: Lower of 20 EMA and 20 SMA (conservative)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from nexus2.domain.automation.ema_check_job import (
        MACheckJob,
        TrailingMAType,
    )
    from nexus2.db import SessionLocal, PositionRepository
    
    # Parse MA type
    ma_type_map = {
        "auto": TrailingMAType.AUTO,  # Auto-select based on ADR% (KK-style)
        "ema_10": TrailingMAType.EMA_10,
        "ema_20": TrailingMAType.EMA_20,
        "sma_10": TrailingMAType.SMA_10,
        "sma_20": TrailingMAType.SMA_20,
        "lower_10": TrailingMAType.LOWER_10,  # Lower of 10 EMA/SMA (tight)
        "lower_20": TrailingMAType.LOWER_20,  # Lower of 20 EMA/SMA (conservative)
    }
    ma_type = ma_type_map.get(req.ma_type, TrailingMAType.AUTO)  # Default to AUTO
    
    # Get market data adapter for MA calculations
    market_data = getattr(request.app.state, 'market_data', None)
    
    # Load saved settings for defaults
    from nexus2.api.routes.settings import get_settings
    saved_settings = get_settings()
    
    # Use request values, falling back to saved settings
    effective_min_days = req.min_days if req.min_days != 5 else saved_settings.min_days_for_trailing
    effective_ma_type = ma_type
    
    # If request uses "auto" and settings say otherwise, respect request
    # But if using defaults, pull from settings
    if req.ma_type == "auto":
        effective_ma_type = ma_type_map.get(saved_settings.trailing_ma_type, TrailingMAType.AUTO)
    
    # Create job with callbacks
    job = MACheckJob(
        min_days_for_trailing=effective_min_days,
        default_ma_type=effective_ma_type,
        require_timing_window=req.require_timing_window,
    )
    job.adr_threshold = saved_settings.adr_threshold  # Use saved threshold
    
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
    
    # Callback: Get daily close (use last price as proxy)
    async def get_daily_close(symbol: str):
        if market_data:
            try:
                quote = market_data.get_quote(symbol)
                if quote and hasattr(quote, 'close'):
                    return quote.close
                elif quote and hasattr(quote, 'price'):
                    return quote.price
            except Exception as e:
                logger.warning(f"Could not get close for {symbol}: {e}")
        return None
    
    # Callback: Get EMA value
    async def get_ema(symbol: str, period: int):
        if market_data:
            try:
                return market_data.get_ema(symbol, period)
            except Exception as e:
                logger.warning(f"Could not get EMA{period} for {symbol}: {e}")
        return None
    
    # Callback: Get SMA value
    async def get_sma(symbol: str, period: int):
        if market_data:
            try:
                return market_data.get_sma(symbol, period)
            except Exception as e:
                logger.warning(f"Could not get SMA{period} for {symbol}: {e}")
        return None
    
    # Callback: Get ADR% for auto MA selection (KK-style)
    async def get_adr_percent(symbol: str, period: int):
        if market_data:
            try:
                return market_data.get_adr_percent(symbol, period)
            except Exception as e:
                logger.warning(f"Could not get ADR% for {symbol}: {e}")
        return None
    
    # Callback: Execute exit
    async def execute_exit(position_id: str, shares: int, reason: str):
        from nexus2.db import PositionRepository, PositionExitRepository
        from datetime import datetime
        from uuid import uuid4
        
        db = SessionLocal()
        try:
            position_repo = PositionRepository(db)
            exit_repo = PositionExitRepository(db)
            
            position = position_repo.get_by_id(position_id)
            if not position:
                return
            
            # Get current price for exit
            current_price = None
            if market_data:
                quote = market_data.get_quote(position.symbol)
                current_price = quote.price if quote else None
            
            if not current_price:
                current_price = position.entry_price  # Fallback
            
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
            
            logger.info(f"[MACheck] Exited {position.symbol}: {shares} shares")
        finally:
            db.close()
    
    # Set callbacks
    job.set_callbacks(
        get_positions=get_positions,
        get_daily_close=get_daily_close,
        get_ema=get_ema,
        get_sma=get_sma,
        get_adr_percent=get_adr_percent,  # For auto MA selection
        execute_exit=execute_exit if not req.dry_run else None,
    )
    
    # Run the check
    result = await job.run(dry_run=req.dry_run)
    
    return {
        "status": "completed",
        "dry_run": req.dry_run,
        "ma_type": req.ma_type,
        "positions_checked": result.positions_checked,
        "is_within_timing_window": result.is_within_timing_window,
        "exit_signals": [
            {
                "symbol": s.symbol,
                "daily_close": float(s.daily_close),
                "ma_value": float(s.ma_value),
                "ma_type": s.ma_type.value,
                "days_held": s.days_held,
            }
            for s in result.exit_signals
        ],
        "errors": result.errors,
    }


# Keep old endpoint for backwards compatibility
@router.post("/ema-check", response_model=dict, deprecated=True)
async def run_ema_check(
    request: Request,
    req: MACheckRequest = MACheckRequest(),
):
    """Deprecated: Use /ma-check instead."""
    return await run_ma_check(request, req)


@router.get("/ma-check/status", response_model=dict)
async def get_ma_check_status():
    """Get MA check job status."""
    from nexus2.domain.automation.ema_check_job import get_ma_check_job
    job = get_ma_check_job()
    return job.get_status()
