"""
Position Routes
"""

from uuid import UUID, uuid4
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from decimal import Decimal

from nexus2.api.schemas import (
    PositionResponse,
    PositionListResponse,
    PartialExitRequest,
    ClosePositionRequest,
    PositionPerformance,
)
from nexus2.api.dependencies import get_position_service, get_trade_service, get_position_repo, get_position_exit_repo
from nexus2.domain.positions import (
    PositionService,
    TradeManagementService,
    PositionNotFoundError,
    ExitReason,
)
from nexus2.db import PositionRepository
from nexus2.api.routes.settings import get_settings
from nexus2.utils.time_utils import now_utc


router = APIRouter(prefix="/positions", tags=["positions"])


class ClosedPositionResponse(BaseModel):
    """Closed position with P&L stats."""
    id: str
    symbol: str
    setup_type: str | None
    entry_price: str
    shares: int
    initial_stop: str | None
    avg_exit_price: str | None  # Weighted average of all exits
    realized_pnl: str
    opened_at: str | None
    closed_at: str | None
    days_held: int = 0


class LivePositionResponse(BaseModel):
    """Position with live P&L (from broker)."""
    id: str
    symbol: str
    setup_type: str | None = None
    entry_date: str | None = None
    entry_price: Decimal
    shares: int
    remaining_shares: int
    initial_stop: Decimal | None = None
    current_stop: Decimal | None = None
    stop_type: str | None = None
    status: str
    realized_pnl: Decimal = Decimal("0")
    days_held: int = 0
    # Live P&L from broker
    current_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    market_value: Decimal | None = None
    source: str = "local"  # "local" or "alpaca"


def _position_to_response(trade) -> PositionResponse:
    """Convert ManagedTrade to response."""
    return PositionResponse(
        id=trade.id,
        symbol=trade.symbol,
        setup_type=trade.setup_type,
        entry_date=str(trade.entry_date),
        entry_price=trade.entry_price,
        shares=trade.shares,
        remaining_shares=trade.remaining_shares,
        initial_stop=trade.initial_stop,
        current_stop=trade.current_stop,
        stop_type=trade.stop_type,
        status=trade.status.value,
        realized_pnl=trade.realized_pnl,
        days_held=trade.days_held,
    )


@router.get("", response_model=PositionListResponse)
async def list_positions(
    request: Request,
    include_closed: bool = False,
    position_service: PositionService = Depends(get_position_service),
):
    """List positions for current broker/account."""
    settings = get_settings()
    
    # Get local positions
    if include_closed:
        local_positions = position_service.get_all_positions()
        local_positions = [
            p for p in local_positions 
            if p.broker_type == settings.broker_type and p.account == settings.active_account
        ]
    else:
        local_positions = position_service.get_open_positions(
            broker_type=settings.broker_type,
            account=settings.active_account,
        )
    
    # For Alpaca brokers, fetch live positions from broker
    if settings.broker_type.startswith("alpaca"):
        try:
            broker = request.app.state.broker
            broker_positions = broker.get_positions()
            
            # Convert broker positions to responses
            responses = []
            local_symbols = {p.symbol for p in local_positions}
            
            for symbol, bp in broker_positions.items():
                # Check if we have local position for this symbol
                local_match = next((p for p in local_positions if p.symbol == symbol), None)
                
                if local_match:
                    # Merge local position with live P&L
                    resp = _position_to_response(local_match)
                else:
                    # Broker-only position (opened outside Nexus)
                    resp = PositionResponse(
                        id=uuid4(),  # Generate temp ID
                        symbol=symbol,
                        setup_type="external",
                        entry_date=None,
                        entry_price=bp.avg_price,
                        shares=bp.quantity,
                        remaining_shares=bp.quantity,
                        initial_stop=None,
                        current_stop=None,
                        stop_type=None,
                        status="open",
                        realized_pnl=Decimal("0"),
                        days_held=0,
                    )
                
                responses.append(resp)
            
            # Add local positions not in broker (shouldn't happen normally)
            for lp in local_positions:
                if lp.symbol not in broker_positions:
                    responses.append(_position_to_response(lp))
            
            return PositionListResponse(
                positions=responses,
                total=len(responses),
            )
            
        except Exception as e:
            print(f"[Positions] Failed to fetch from broker: {e}")
            # Fall through to local positions
    
    return PositionListResponse(
        positions=[_position_to_response(p) for p in local_positions],
        total=len(local_positions),
    )


@router.get("/count")
async def get_positions_count(
    request: Request,
    position_service: PositionService = Depends(get_position_service),
):
    """Get count of open positions (NAC strategy)."""
    settings = get_settings()
    
    open_positions = position_service.get_open_positions(
        broker_type=settings.broker_type,
        account=settings.active_account,
    )
    
    return {"count": len(open_positions), "strategy": "NAC"}


class ClosedPositionsListResponse(BaseModel):
    """Response with closed positions list."""
    positions: List[ClosedPositionResponse]
    total: int
    total_pnl: str


@router.get("/closed", response_model=ClosedPositionsListResponse)
async def list_closed_positions(
    position_repo: PositionRepository = Depends(get_position_repo),
    position_exit_repo = Depends(get_position_exit_repo),
):
    """List closed positions with P&L stats from database."""
    from datetime import datetime
    from nexus2.db import PositionExitRepository
    
    db_positions = position_repo.get_all(status="closed", limit=100)
    
    results = []
    total_pnl = Decimal("0")
    
    for p in db_positions:
        pnl = Decimal(p.realized_pnl or "0")
        total_pnl += pnl
        
        days = 0
        if p.opened_at and p.closed_at:
            days = (p.closed_at - p.opened_at).days
        
        # Calculate average exit price from exits
        avg_exit = position_exit_repo.get_avg_exit_price(p.id)
        
        results.append(ClosedPositionResponse(
            id=p.id,
            symbol=p.symbol,
            setup_type=p.setup_type,
            entry_price=p.entry_price,
            shares=p.shares,
            initial_stop=p.initial_stop,
            avg_exit_price=avg_exit,
            realized_pnl=p.realized_pnl or "0",
            opened_at=p.opened_at.isoformat() if p.opened_at else None,
            closed_at=p.closed_at.isoformat() if p.closed_at else None,
            days_held=days,
        ))
    
    return ClosedPositionsListResponse(
        positions=results,
        total=len(results),
        total_pnl=str(total_pnl),
    )


class SyncResult(BaseModel):
    """Result of position sync operation."""
    synced: int  # External positions added
    closed: int  # Local positions closed (not at broker)
    unchanged: int  # Already in sync
    errors: List[str] = []


@router.post("/sync", response_model=SyncResult)
async def sync_positions(
    request: Request,
    position_service: PositionService = Depends(get_position_service),
    position_repo: PositionRepository = Depends(get_position_repo),
):
    """
    Sync positions with broker.
    
    - Fetches positions from broker
    - Creates local entries for external positions (opened outside Nexus)
    - Closes local positions no longer at broker
    """
    from datetime import datetime
    
    settings = get_settings()
    
    # Only sync for Alpaca brokers
    if not settings.broker_type.startswith("alpaca"):
        raise HTTPException(
            status_code=400,
            detail="Sync only available for Alpaca brokers"
        )
    
    broker = request.app.state.broker
    errors = []
    synced = 0
    closed = 0
    unchanged = 0
    
    try:
        broker_positions = broker.get_positions()
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch broker positions: {e}"
        )
    
    # Get local open positions for this broker/account
    local_positions = position_repo.get_all(status="open", limit=500)
    local_positions = [
        p for p in local_positions
        if getattr(p, 'broker_type', 'paper') == settings.broker_type
        and getattr(p, 'account', 'A') == settings.active_account
    ]
    local_symbols = {p.symbol for p in local_positions}
    broker_symbols = set(broker_positions.keys())
    
    # Get actual entry dates from Alpaca orders API
    external_symbols = broker_symbols - local_symbols
    entry_dates = {}
    if external_symbols:
        try:
            entry_dates = broker.get_position_entry_dates(list(external_symbols))
        except Exception as e:
            errors.append(f"Failed to fetch entry dates: {e}")
    
    # 1. Add external positions (at broker but not local)
    for symbol, bp in broker_positions.items():
        if symbol not in local_symbols:
            try:
                # Use actual fill date from Alpaca, fallback to now if not found
                opened_at = entry_dates.get(symbol, now_utc())
                
                position_repo.create({
                    "id": str(uuid4()),
                    "symbol": symbol,
                    "setup_type": "external",
                    "status": "open",
                    "entry_price": str(bp.avg_price),
                    "shares": bp.quantity,
                    "remaining_shares": bp.quantity,
                    "initial_stop": None,
                    "current_stop": None,
                    "realized_pnl": "0",
                    "opened_at": opened_at,
                    "broker_type": settings.broker_type,
                    "account": settings.active_account,
                })
                synced += 1
            except Exception as e:
                errors.append(f"Failed to create {symbol}: {e}")
        else:
            unchanged += 1
    
    # 2. Close local positions not at broker (likely sold outside Nexus)
    for lp in local_positions:
        if lp.symbol not in broker_symbols:
            try:
                position_repo.close(lp.id, "0")  # Mark as closed, P&L unknown
                position_service.close_position(UUID(lp.id))
                closed += 1
            except Exception as e:
                errors.append(f"Failed to close {lp.symbol}: {e}")
    
    return SyncResult(
        synced=synced,
        closed=closed,
        unchanged=unchanged,
        errors=errors,
    )


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: UUID,
    position_service: PositionService = Depends(get_position_service),
):
    """Get position by ID."""
    position = position_service.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    return _position_to_response(position)


@router.get("/{position_id}/performance", response_model=PositionPerformance)
async def get_position_performance(
    position_id: UUID,
    current_price: float,
    position_service: PositionService = Depends(get_position_service),
):
    """Get position performance metrics."""
    from decimal import Decimal
    
    position = position_service.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    perf = position.calculate_performance(Decimal(str(current_price)))
    
    return PositionPerformance(
        entry_price=perf.entry_price,
        current_price=perf.current_price,
        unrealized_pnl=perf.unrealized_pnl,
        unrealized_pnl_pct=perf.unrealized_pnl_pct,
        realized_pnl=perf.realized_pnl,
        total_pnl=perf.total_pnl,
        r_multiple=perf.r_multiple,
        days_held=perf.days_held,
    )


@router.post("/{position_id}/partial-exit", response_model=PositionResponse)
async def partial_exit(
    position_id: UUID,
    request: PartialExitRequest,
    position_service: PositionService = Depends(get_position_service),
    trade_service: TradeManagementService = Depends(get_trade_service),
    position_repo: PositionRepository = Depends(get_position_repo),
    position_exit_repo = Depends(get_position_exit_repo),
):
    """Execute partial exit on position."""
    position = position_service.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    try:
        reason = ExitReason(request.reason)
    except ValueError:
        reason = ExitReason.PARTIAL_PROFIT
    
    updated = trade_service.execute_partial_exit(
        trade=position,
        shares=request.shares,
        exit_price=request.price,
        reason=reason,
    )
    
    # Record exit for avg exit price calculation
    position_exit_repo.create({
        "id": str(uuid4()),
        "position_id": str(position_id),
        "shares": request.shares,
        "exit_price": str(request.price),
        "reason": reason.value,
    })
    
    # Persist to database
    position_repo.update(str(position_id), {
        "remaining_shares": updated.remaining_shares,
        "realized_pnl": str(updated.realized_pnl),
        "status": "closed" if updated.remaining_shares == 0 else "open",
    })
    
    return _position_to_response(updated)


@router.post("/{position_id}/close", response_model=PositionResponse)
async def close_position(
    position_id: UUID,
    request: ClosePositionRequest,
    position_service: PositionService = Depends(get_position_service),
    trade_service: TradeManagementService = Depends(get_trade_service),
    position_repo: PositionRepository = Depends(get_position_repo),
    position_exit_repo = Depends(get_position_exit_repo),
):
    """Close entire position."""
    position = position_service.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Get remaining shares before closing
    remaining_shares = position.remaining_shares
    
    try:
        reason = ExitReason(request.reason)
    except ValueError:
        reason = ExitReason.MANUAL
    
    closed = trade_service.close_trade(
        trade=position,
        exit_price=request.price,
        reason=reason,
    )
    
    # Record exit for avg exit price calculation
    position_exit_repo.create({
        "id": str(uuid4()),
        "position_id": str(position_id),
        "shares": remaining_shares,
        "exit_price": str(request.price),
        "reason": reason.value,
    })
    
    # Update position service (in-memory)
    position_service.close_position(position_id)
    
    # Persist to database
    position_repo.close(str(position_id), str(closed.realized_pnl))
    
    return _position_to_response(closed)

