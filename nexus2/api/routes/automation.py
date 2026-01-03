"""
Automation Routes

API endpoints for controlling the automation engine.
Now uses modular structure with separate files for state, models, and helpers.
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

# Persistent file logging for scan history
from nexus2.domain.automation.automation_logger import (
    log_scan_start, log_scan_result, log_position_sizing,
    log_execution_decision, log_cycle_summary,
)

# Discord notifications
from nexus2.adapters.notifications.discord import DiscordNotifier

# Import from new modular structure
from nexus2.api.routes.automation_state import (
    get_engine, set_engine, get_scheduler, get_monitor,
    set_app, get_app,
    get_auto_start_task, set_auto_start_task,
    get_auto_start_triggered_today, set_auto_start_triggered_today,
)
from nexus2.api.routes.automation_models import (
    StartRequest, EngineStatusResponse, ActionResponse,
    ScanAllRequest, ExecuteRequest,
    SchedulerStartRequest, SchedulerToggleRequest, SchedulerIntervalRequest,
    SchedulerSettingsRequest, MonitorStartRequest, MACheckRequest,
    SCHEDULER_PRESETS,
)
from nexus2.api.routes.automation_helpers import (
    auto_start_checker as _auto_start_checker_fn,
    start_auto_start_checker as _start_auto_start_checker,
    configure_scanner_from_settings as _configure_scanner_from_settings,
    create_eod_callback as _create_eod_callback,
    configure_and_start_scheduler as _configure_and_start_scheduler,
)
from nexus2.api.routes.execution_handler import create_execute_callback as _create_execute_callback_factory

router = APIRouter(prefix="/automation", tags=["automation"])

# Module-level MockBroker reference for sim mode
_sim_broker = None

def _get_sim_broker():
    """Get the MockBroker instance used in sim_mode."""
    return _sim_broker

def _set_sim_broker(broker):
    """Set the MockBroker instance for sim_mode."""
    global _sim_broker
    _sim_broker = broker




# Wrapper functions to provide dependencies to helpers
async def auto_start_checker():
    """Background task wrapper that injects dependencies."""
    await _auto_start_checker_fn(
        get_scheduler,
        get_engine,
        get_monitor,
        lambda e, s: _configure_and_start_scheduler(e, s, get_app),
    )


def start_auto_start_checker():
    """Start the auto-start checker background task."""
    import asyncio
    task = get_auto_start_task()
    if task is None:
        task = asyncio.create_task(auto_start_checker())
        set_auto_start_task(task)
        logger.info("[AutoStart] Checker started")
    return task


# ==================== ROUTE HANDLERS ====================
# (Models imported from automation_models.py, state from automation_state.py)


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
async def get_api_stats(request: Request):
    """
    Get API rate limit statistics.
    
    Returns current FMP API usage including calls/minute, remaining, and usage%.
    """
    try:
        unified = getattr(request.app.state, 'market_data', None)
        if unified and hasattr(unified, 'fmp'):
            # UnifiedMarketData wraps FMP
            fmp = unified.fmp
        else:
            # Fallback to singleton
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
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
                max_shares_from_cap = int(max_per_symbol / float(signal.entry_price))
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
                    "source": "nac",  # Track that this is an automated trade
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
        global _sim_broker  # Declare at start to avoid syntax error
        from nexus2.db import SessionLocal, PositionRepository, SchedulerSettingsRepository
        from nexus2.domain.automation.services import create_unified_scanner_callback
        from uuid import uuid4
        from datetime import datetime
        from decimal import Decimal
        
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Starting execute_callback...")
        
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
            
            # Check sim_mode setting
            sim_mode_setting = getattr(sched_settings, 'sim_mode', False)
            sim_mode = sim_mode_setting == "true" if isinstance(sim_mode_setting, str) else bool(sim_mode_setting)
            
            # Get min_price from settings (default $5 if not set)
            min_price_setting = getattr(sched_settings, 'min_price', None)
            min_price = float(min_price_setting) if min_price_setting else 5.0
            
            # Reconfigure engine scanner with fresh settings + sim_mode
            preset = sched_settings.preset or "strict"
            engine._scanner_func = await create_unified_scanner_callback(
                min_quality=min_quality,
                max_stop_percent=max_stop_percent,
                stop_mode=stop_mode,
                max_stop_atr=max_stop_atr,
                scan_modes=scan_modes,
                htf_frequency=htf_frequency,
                sim_mode=sim_mode,  # Pass sim_mode to use MockMarketData
                preset=preset,  # Pass preset for relaxed EP settings
                min_price=min_price,  # Pass min_price to scanner
            )
            print(f"🔄 [AutoExec] Reloaded settings: min_quality={min_quality}, stop_mode={stop_mode}, sim_mode={sim_mode}, min_price=${min_price}")
            
            # Log scan start to persistent file
            log_scan_start(scan_modes, {
                "min_quality": min_quality, "stop_mode": stop_mode,
                "max_stop_atr": max_stop_atr, "min_price": min_price,
            })
        finally:
            db_settings.close()
        
        # Run scan to get signals (with timing)
        import time
        scan_start = time.time()
        signals = await engine.run_scan_cycle()
        scan_duration = time.time() - scan_start
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Scan returned {len(signals) if signals else 0} signals (took {scan_duration:.1f}s)")
        
        # Store signals in scheduler for UI display (even in auto_execute mode)
        scheduler.last_signals = signals if signals else []
        scheduler.last_signals_at = datetime.now()
        
        # Log summary of all signals received for diagnostics
        if signals:
            print(f"📋 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Signal Summary:")
            for i, sig in enumerate(signals[:10], 1):
                setup_name = sig.setup_type.value if hasattr(sig.setup_type, 'value') else str(sig.setup_type)
                print(f"   {i}. {sig.symbol:6} | Score: {sig.quality_score} | Type: {setup_name:8} | Mode: {sig.scanner_mode} | Tier: {sig.tier}")
            
            # Log scan results to persistent file
            log_scan_result(
                total_signals=len(signals),
                ep_count=sum(1 for s in signals if hasattr(s, 'setup_type') and getattr(s.setup_type, 'value', '') == 'ep'),
                breakout_count=sum(1 for s in signals if hasattr(s, 'setup_type') and getattr(s.setup_type, 'value', '') in ('breakout', 'flag')),
                htf_count=sum(1 for s in signals if hasattr(s, 'setup_type') and getattr(s.setup_type, 'value', '') == 'htf'),
                duration_ms=int(scan_duration * 1000),
                signals=signals,
            )
        
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
        
        # Get existing positions to avoid adding to existing positions
        existing_symbols = set()
        
        # In sim_mode, check MockBroker positions
        if sim_mode and _sim_broker is not None:
            try:
                sim_positions = _sim_broker.get_positions()
                # get_positions() returns list of dicts with 'symbol' key
                for pos in sim_positions:
                    existing_symbols.add(pos['symbol'].upper())
                if existing_symbols:
                    print(f"📍 [SIM] Already holding in MockBroker: {', '.join(sorted(existing_symbols))}")
            except Exception as e:
                logger.warning(f"[AutoExec] Could not fetch sim positions: {e}")
        elif broker:
            # In live mode, check Alpaca positions
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
                max_shares_from_cap = int(float(max_per_symbol) / float(signal.entry_price))
                print(f"📊 [DEBUG] {signal.symbol}: entry_price={signal.entry_price}, max_per_symbol={max_per_symbol}, max_shares={max_shares_from_cap}")
                if shares > max_shares_from_cap:
                    print(f"🔒 [AutoExec] Capping {signal.symbol} shares from {shares} to {max_shares_from_cap} (max ${max_per_symbol})")
                    log_position_sizing(
                        signal.symbol, float(signal.entry_price), shares, max_shares_from_cap,
                        float(max_per_symbol), reason="exceeds max_per_symbol cap"
                    )
                    shares = max_shares_from_cap
            
            if shares < 1:
                logger.warning(f"[AutoExec] Position too small for {signal.symbol}: {shares} shares")
                skipped.append({"symbol": signal.symbol, "reason": "Position size < 1 share"})
                log_execution_decision(signal.symbol, 0, 0, "SKIPPED", reason="Position size < 1 share")
                continue
            
            # Check if broker is available
            if broker is None and not sim_mode:
                logger.error("[AutoExec] No broker configured!")
                return {"status": "failed", "error": "No broker configured", "executed": executed}
            
            # In sim_mode, use MockBroker instead of live broker
            if sim_mode:
                from nexus2.adapters.simulation import get_mock_market_data
                from nexus2.adapters.simulation.mock_broker import MockBroker
                
                
                # Get or create global MockBroker (stored at module level)
                if _sim_broker is None:
                    _sim_broker = MockBroker(initial_cash=100_000.0)
                    logger.info("[SIM] Created new MockBroker with $100k initial cash")
                
                # Set current price from MockMarketData for each symbol
                mock_data = get_mock_market_data()
                current_price = mock_data.get_last_price(signal.symbol)
                if current_price:
                    _sim_broker.set_price(signal.symbol, float(current_price))
                else:
                    print(f"⚠️ [SIM] No price available for {signal.symbol} - skipping")
                    skipped.append({"symbol": signal.symbol, "reason": "No sim price available"})
                    continue
                
                active_broker = _sim_broker
                print(f"🧪 [SIM] Using MockBroker for {signal.symbol}")
            else:
                active_broker = broker
            
            # Submit bracket order through broker
            try:
                client_order_id = uuid4()
                stop_price = Decimal(str(signal.tactical_stop))
                
                # Log signal details for diagnostics
                setup_name = signal.setup_type.value if hasattr(signal.setup_type, 'value') else str(signal.setup_type)
                print(f"📊 [AutoExec] Signal: {signal.symbol} | Score: {signal.quality_score} | Type: {setup_name} | Mode: {signal.scanner_mode} | Tier: {signal.tier}")
                print(f"🤖 [AutoExec] Submitting bracket order: {signal.symbol} x {shares} @ stop ${stop_price}")
                
                result = active_broker.submit_bracket_order(
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
                        "source": "nac",  # Track that this is an automated trade
                        # Signal quality tracking
                        "quality_score": signal.quality_score,
                        "tier": signal.tier,
                        "rs_percentile": signal.rs_percentile,
                        "adr_percent": str(signal.adr_percent) if signal.adr_percent else None,
                    })
                    
                    # Update engine stats
                    engine.stats.orders_submitted += 1
                    engine.stats.orders_filled += 1
                    
                    logger.info(f"[AutoExec] SUCCESS: {signal.symbol} x {shares} @ stop ${stop_price}")
                    print(f"✅ [AutoExec] Executed: {signal.symbol} x {shares}")
                    
                    # Log to persistent file
                    log_execution_decision(
                        signal.symbol, shares, float(stop_price), "EXECUTED",
                        order_id=str(result.broker_order_id)
                    )
                    
                    # Send Discord notification
                    try:
                        discord = DiscordNotifier()
                        setup_name = signal.setup_type.value if hasattr(signal.setup_type, 'value') else str(signal.setup_type)
                        entry_price = float(signal.entry_price)
                        order_total = entry_price * shares
                        discord.send_trade_alert(
                            message=f"ENTRY: {signal.symbol} x {shares} @ ${entry_price:.2f} = ${order_total:.2f}\n{setup_name.upper()} | Stop ${stop_price:.2f} | Score: {signal.quality_score}",
                            trade_id=str(result.broker_order_id)
                        )
                    except Exception as e:
                        logger.warning(f"Discord notification failed: {e}")
                    
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
                log_execution_decision(signal.symbol, shares, float(stop_price), "ERROR", reason="Order not accepted by broker")
        
        # Log cycle summary to persistent file
        log_cycle_summary(
            executed_count=len(executed),
            skipped_count=len(skipped),
            error_count=len(errors),
            executed_symbols=[e["symbol"] for e in executed],
            skipped_symbols=[s["symbol"] for s in skipped],
        )
        
        print(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] [AutoExec] Cycle complete: {len(executed)} executed, {len(skipped)} skipped, {len(errors)} errors")
        
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
    from nexus2.api.routes.automation_state import get_monitor
    from nexus2.api.routes.settings import get_settings
    
    saved_settings = get_settings()
    
    # Get the shared monitor singleton (same instance used by /monitor/status)
    _monitor = get_monitor()
    _monitor.kk_style_partials = True
    _monitor.partial_exit_days = saved_settings.partial_exit_days
    _monitor.partial_exit_fraction = saved_settings.partial_exit_fraction
    
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
                from uuid import uuid4
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
                    db = SessionLocal()
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
                    db.close()
                except Exception as db_err:
                    logger.warning(f"[Monitor] DB update failed: {db_err}")
                    
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
    from nexus2.db import SessionLocal, SchedulerSettingsRepository, PositionRepository
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
                      "max_position_value", "auto_start_enabled", "auto_start_time", "auto_execute",
                      "nac_broker_type", "nac_account", "sim_mode", "min_price"]:
            value = getattr(req, field, None)
            if value is not None:
                # Convert numeric to string for DB storage
                if field in ["max_stop_atr", "max_stop_percent", "max_position_value", "min_price"]:
                    updates[field] = str(value)
                elif field in ["auto_start_enabled", "auto_execute", "sim_mode"]:
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


# ==================== SIMULATION ENDPOINTS ====================
# Simulation endpoints have been moved to automation_simulation.py
# See: nexus2/api/routes/automation_simulation.py
