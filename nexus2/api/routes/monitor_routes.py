"""
Monitor Routes Module

Extracted from automation.py for better maintainability.
Contains position monitoring endpoints for stop-loss and trailing stop management.
"""

import logging
from fastapi import APIRouter, Depends

from nexus2.domain.automation.engine import AutomationEngine
from nexus2.api.routes.automation_state import get_engine, get_monitor
from nexus2.api.routes.automation_models import MonitorStartRequest
from nexus2.db.database import get_session
from nexus2.db.repository import PositionRepository
from nexus2.utils.time_utils import now_utc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


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
    
    # Get positions callback (must be async for monitor.py)
    async def get_positions():
        with get_session() as db:
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
                    "opened_at": p.opened_at,
                    "partial_taken": p.partial_taken,
                }
                for p in positions
            ]
    
    # Get price callback (uses FMP or returns mock for demo)
    async def get_price(symbol: str):
        try:
            import asyncio
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            fmp = get_fmp_adapter()
            quote = await asyncio.to_thread(fmp.get_quote, symbol)
            if quote:
                return quote.price
        except Exception as e:
            pass
        # Fallback - return None (monitor will skip)
        return None
    
    # Execute exit callback
    async def execute_exit(signal):
        from nexus2.db import PositionRepository, PositionExitRepository
        from datetime import datetime
        from decimal import Decimal
        
        with get_session() as db:
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
                "exited_at": now_utc(),
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
                    updates["closed_at"] = now_utc()
                    updates["realized_pnl"] = str(signal.pnl_estimate)
                
                position_repo.update(signal.position_id, updates)
            
            # CRITICAL: Commit the transaction to persist changes
            db.commit()
            
            return {"status": "executed", "symbol": signal.symbol}
    
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
