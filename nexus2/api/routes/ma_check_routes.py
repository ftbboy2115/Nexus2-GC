"""
MA Check Routes Module

Extracted from automation.py for better maintainability.
Contains EOD MA trailing stop check endpoints for KK-style trade management.
"""

import logging
from fastapi import APIRouter, Request

from nexus2.api.routes.automation_models import MACheckRequest
from nexus2.db.database import get_session
from nexus2.db.repository import PositionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


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
    from nexus2.domain.automation.ema_check_job import (
        MACheckJob,
        TrailingMAType,
    )
    
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
    
    # Get broker for submitting exit orders
    broker = getattr(request.app.state, 'broker', None)
    
    # Load saved settings for defaults
    from nexus2.api.routes.settings import get_settings
    saved_settings = get_settings()
    
    # Use request values, falling back to saved settings
    effective_min_days = req.min_days if req.min_days != 5 else saved_settings.min_days_for_trailing
    
    # If request explicitly specifies a MA type, use it
    # Only fall back to saved settings if no specific type requested
    # Note: "auto" is a valid explicit choice that uses ADR-based selection
    effective_ma_type = ma_type  # Respect the request (including "auto")
    
    # Create job with callbacks
    job = MACheckJob(
        min_days_for_trailing=effective_min_days,
        default_ma_type=effective_ma_type,
        require_timing_window=req.require_timing_window,
    )
    job.adr_threshold = saved_settings.adr_threshold  # Use saved threshold
    
    # Callback: Get open positions
    async def get_positions():
        with get_session() as db:
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
        
        with get_session() as db:
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
                    logger.info(f"[MACheck] Submitted sell order for {position.symbol} x {shares}")
                except Exception as e:
                    logger.error(f"[MACheck] Failed to submit sell order for {position.symbol}: {e}")
                    # Don't update DB if broker order failed
                    return
            
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
            update_data = {
                "remaining_shares": new_remaining,
                "status": "closed" if new_remaining <= 0 else "open",
            }
            if new_remaining <= 0:
                update_data["closed_at"] = datetime.utcnow()
            position_repo.update(position_id, update_data)
            
            logger.info(f"[MACheck] Exited {position.symbol}: {shares} shares")
    
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
    
    # =============================
    # DISCORD NOTIFICATIONS
    # =============================
    try:
        from nexus2.adapters.notifications.discord import DiscordNotifier
        from nexus2.db import SchedulerSettingsRepository
        
        # Check if Discord alerts are enabled
        with get_session() as db:
            settings_repo = SchedulerSettingsRepository(db)
            sched_settings = settings_repo.get()
            discord_enabled = getattr(sched_settings, 'discord_alerts_enabled', 'true')
            discord_enabled = discord_enabled == 'true' if isinstance(discord_enabled, str) else bool(discord_enabled)
        
        if discord_enabled:
            notifier = DiscordNotifier()
            
            if notifier.config.enabled:
                # Build completion summary message
                exit_count = len(result.exit_signals)
                
                if req.dry_run:
                    summary = f"🔍 **[DRY RUN] EOD MA Check Complete**\n"
                else:
                    summary = f"🌅 **EOD MA Check Complete**\n"
                
                summary += f"• Positions checked: **{result.positions_checked}**\n"
                summary += f"• Exit signals: **{exit_count}**\n"
                
                if result.is_within_timing_window:
                    summary += "• Timing: ✅ Within 3:45-4:00 PM ET window\n"
                else:
                    summary += "• Timing: ⚠️ Outside standard window (manual run)\n"
                
                # Add exit signal details if any
                if exit_count > 0:
                    summary += "\n**📉 Trend Failures:**\n"
                    for sig in result.exit_signals[:5]:  # Limit to 5
                        summary += f"• **{sig.symbol}** - Day {sig.days_held}: ${sig.daily_close} < {sig.ma_type.value} ${sig.ma_value}\n"
                    
                    if exit_count > 5:
                        summary += f"... and {exit_count - 5} more\n"
                    
                    if req.dry_run:
                        summary += "\n_⚠️ DRY RUN - No orders submitted_"
                    else:
                        summary += "\n_✅ Exit orders submitted_"
                else:
                    summary += "\n✅ All positions holding trend - no exits needed"
                
                # Send the notification
                level = "success" if exit_count == 0 else "warning"
                notifier.send_system_alert(summary, level=level)
                logger.info(f"[MACheck] Discord notification sent: {exit_count} exit signals")
                
    except Exception as e:
        logger.warning(f"[MACheck] Discord notification failed: {e}")
    
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
