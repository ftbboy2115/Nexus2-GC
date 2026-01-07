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
    get_sim_broker, set_sim_broker,  # Thread-safe sim broker
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

# NOTE: _sim_broker moved to automation_state.py for thread safety
# Use get_sim_broker() and set_sim_broker() from automation_state



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
        include_extended_htf=request.include_extended_htf,  # For testing
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


# ==================== RS SERVICE ENDPOINTS ====================

@router.post("/rs/refresh", response_model=dict)
async def refresh_rs_universe(request: Request):
    """
    Refresh the RS (Relative Strength) universe.
    
    This calculates 1M/3M/6M performance for ~2000 stocks and ranks them.
    Uses the shared FMP adapter so API usage is tracked in the dashboard.
    
    ⚠️ Warning: This makes many API calls and may take 5-10 minutes.
    """
    from nexus2.domain.scanner.rs_service import get_rs_service
    
    rs_service = get_rs_service()
    
    # Get the shared FMP adapter from app state (for usage tracking)
    fmp_adapter = getattr(request.app.state, 'market_data', None)
    if fmp_adapter:
        # Use the adapter's underlying FMP if it's a wrapper
        if hasattr(fmp_adapter, '_fmp'):
            rs_service.set_fmp_adapter(fmp_adapter._fmp)
        elif hasattr(fmp_adapter, 'fmp'):
            rs_service.set_fmp_adapter(fmp_adapter.fmp)
        else:
            rs_service.set_fmp_adapter(fmp_adapter)
    
    try:
        count = rs_service.refresh_universe(verbose=True)
        return {
            "status": "success",
            "stocks_ranked": count,
            "message": f"Refreshed RS rankings for {count} stocks with 6M performance data",
        }
    except Exception as e:
        logger.error(f"[RS] Refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rs/status", response_model=dict)
async def get_rs_status():
    """Get current RS universe status and sample data."""
    from nexus2.domain.scanner.rs_service import get_rs_service
    
    rs = get_rs_service()
    
    # Get top 5 stocks by percentile
    top_stocks = sorted(
        rs._universe.values(),
        key=lambda x: x.percentile,
        reverse=True
    )[:5]
    
    return {
        "universe_size": len(rs._universe),
        "last_refresh": rs._last_refresh.isoformat() if rs._last_refresh else None,
        "top_5": [
            {
                "symbol": s.symbol,
                "perf_1m": round(s.perf_1m, 2),
                "perf_3m": round(s.perf_3m, 2),
                "perf_6m": round(s.perf_6m, 2),
                "percentile": s.percentile,
            }
            for s in top_stocks
        ],
    }


# ==================== SCHEDULER ENDPOINTS ====================
# Scheduler endpoints have been moved to scheduler_routes.py
# See: nexus2/api/routes/scheduler_routes.py

# Monitor endpoints have been moved to monitor_routes.py
# See: nexus2/api/routes/monitor_routes.py

# ==================== POSITIONS ENDPOINTS ====================

@router.get("/positions", response_model=dict)
async def get_broker_positions(request: Request):
    """
    Get positions from the connected broker (Alpaca).
    
    Returns all open positions with current P&L.
    Merges with local Position records to provide additional metadata
    like stop_price and days_held for the expanded view.
    """
    from datetime import datetime, timezone
    
    broker = getattr(request.app.state, 'broker', None)
    
    if broker is None:
        return {
            "status": "no_broker",
            "message": "No broker configured",
            "positions": [],
        }
    
    try:
        positions_dict = broker.get_positions()
        
        # Query local Position records for correlation
        db = SessionLocal()
        try:
            position_repo = PositionRepository(db)
            # Get all open positions from local DB
            local_positions = position_repo.get_open()
            # Create lookup by symbol
            local_by_symbol = {p.symbol: p for p in local_positions}
        finally:
            db.close()
        
        # Convert to list format for frontend
        positions_list = []
        total_value = 0
        total_pnl = 0
        
        for symbol, pos in positions_dict.items():
            market_value = float(pos.market_value) if pos.market_value else 0
            unrealized_pnl = float(pos.unrealized_pnl) if pos.unrealized_pnl else 0
            avg_price = float(pos.avg_price) if pos.avg_price else 0
            qty = pos.quantity
            
            # Calculate P&L percent
            pnl_percent = 0
            if avg_price and qty:
                pnl_percent = (unrealized_pnl / (avg_price * qty) * 100)
            
            # Get current price and change_today from broker
            current_price = float(pos.current_price) if pos.current_price else (market_value / qty if qty > 0 else None)
            change_today = float(pos.change_today) if pos.change_today else None
            
            # Merge with local Position record if available
            local_pos = local_by_symbol.get(symbol)
            stop_price = None
            days_held = None
            side = "long"  # Alpaca positions are typically long
            
            if local_pos:
                # Get stop from local record
                if local_pos.current_stop:
                    stop_price = float(local_pos.current_stop)
                
                # Calculate days held from opened_at
                if local_pos.opened_at:
                    opened_dt = local_pos.opened_at
                    if opened_dt.tzinfo is None:
                        opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    days_held = (now - opened_dt).days
            
            positions_list.append({
                "symbol": pos.symbol,
                "qty": qty,
                "avg_price": avg_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "pnl_percent": pnl_percent,
                # Expanded columns (from local DB merge)
                "current_price": current_price,
                "stop_price": stop_price,
                "side": side,
                "days_held": days_held,
                "today_pnl": float(pos.today_pnl) if pos.today_pnl else None,
                "change_today": change_today,
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
        logger.error(f"[Positions] Error fetching positions: {e}")
        return {
            "status": "error",
            "message": str(e),
            "positions": [],
        }


# ==================== MA CHECK ENDPOINTS (KK TRAILING) ====================
# MA check endpoints have been moved to ma_check_routes.py
# See: nexus2/api/routes/ma_check_routes.py

# ==================== SIMULATION ENDPOINTS ====================
# Simulation endpoints have been moved to automation_simulation.py
# See: nexus2/api/routes/automation_simulation.py
