"""
Trade Routes

Quick trade execution (combines order + execution + position).
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus2.api.schemas import PositionResponse
from nexus2.api.dependencies import (
    get_order_service,
    get_executor,
    get_position_service,
    get_order_repo,
    get_position_repo,
)
from nexus2.domain.orders import (
    OrderService,
    OrderRequest,
    OrderType,
    OrderSide,
)
from nexus2.adapters.broker import OrderExecutor
from nexus2.domain.positions import PositionService
from nexus2.db import OrderRepository, PositionRepository
from nexus2.api.routes.websocket import broadcast_order_update
from nexus2.api.routes.settings import get_settings


router = APIRouter(prefix="/trade", tags=["trade"])


class QuickTradeRequest(BaseModel):
    """Quick trade request."""
    symbol: str
    shares: int = Field(..., gt=0)
    limit_price: Optional[Decimal] = None  # Required for limit orders
    stop_price: Decimal
    setup_type: str = "manual"
    order_type: str = "market"  # "market" or "limit"


class QuickTradeResponse(BaseModel):
    """Quick trade response."""
    order_id: UUID
    position_id: Optional[UUID] = None  # None if order not yet filled
    symbol: str
    shares: int
    fill_price: Optional[Decimal] = None  # None if pending
    stop_price: Decimal
    status: str  # "filled", "pending", "rejected"


@router.post("", response_model=QuickTradeResponse)
async def quick_trade(
    request: QuickTradeRequest,
    order_service: OrderService = Depends(get_order_service),
    executor: OrderExecutor = Depends(get_executor),
    position_service: PositionService = Depends(get_position_service),
    order_repo: OrderRepository = Depends(get_order_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
):
    """
    Execute a quick trade.
    
    Creates order, submits to broker, and creates position if filled.
    - Market orders: Fill immediately
    - Limit orders: May remain pending
    """
    # Determine order type
    order_type = OrderType.MARKET if request.order_type.upper() == "MARKET" else OrderType.LIMIT
    
    if order_type == OrderType.LIMIT and not request.limit_price:
        raise HTTPException(status_code=400, detail="limit_price required for limit orders")
    
    # 1. Create order
    order_req = OrderRequest(
        symbol=request.symbol.upper(),
        side=OrderSide.BUY,
        quantity=request.shares,
        order_type=order_type,
        limit_price=request.limit_price,
        tactical_stop=request.stop_price,
    )
    
    order = order_service.create_order(order_req)
    order = order_service.submit_order(order.id)
    
    # 2. Execute via broker
    result = executor.execute_order(order.id)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    # Refresh order to get fill status
    order = order_service.get_order(order.id)
    
    # 3. Persist order to database
    order_repo.create({
        "id": str(order.id),
        "symbol": order.symbol,
        "side": order.side.value,
        "order_type": order.order_type.value,
        "status": order.status.value,
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "limit_price": str(order.limit_price) if order.limit_price else None,
        "stop_price": str(request.stop_price),
        "tactical_stop": str(request.stop_price),
        "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
        "setup_type": request.setup_type,
        "created_at": order.created_at,
        "submitted_at": order.submitted_at,
        "filled_at": order.filled_at,
    })
    
    # 4. Create position only if order is filled
    position_id = None
    if order.filled_quantity > 0 and order.avg_fill_price:
        try:
            # Get current settings for broker/account tagging
            settings = get_settings()
            position = position_service.create_from_order(
                order, 
                setup_type=request.setup_type,
                broker_type=settings.broker_type,
                account=settings.active_account,
            )
            position_id = position.id
            
            # Persist position
            position_repo.create({
                "id": str(position.id),
                "symbol": position.symbol,
                "setup_type": request.setup_type,
                "status": "open",
                "entry_price": str(position.entry_price),
                "shares": position.shares,
                "remaining_shares": position.remaining_shares,
                "initial_stop": str(position.current_stop),
                "current_stop": str(position.current_stop),
                "realized_pnl": "0",
                "opened_at": position.entry_date,
                "broker_type": settings.broker_type,
                "account": settings.active_account,
                "entry_order_id": str(order.id),
            })
        except Exception as e:
            # Log but don't fail - order is still valid
            print(f"[Trade] Warning: Could not create position: {e}")
    
    # Determine response status
    if order.filled_quantity >= order.quantity:
        status = "filled"
    elif order.filled_quantity > 0:
        status = "partial"
    else:
        status = "pending"
    
    # Broadcast order update via WebSocket
    try:
        await broadcast_order_update(
            order_id=str(order.id),
            symbol=order.symbol,
            status=status,
            shares=order.quantity,
            fill_price=float(order.avg_fill_price) if order.avg_fill_price else None,
            message=f"{status.upper()}: {order.quantity} {order.symbol}",
        )
    except Exception as e:
        print(f"[Trade] WebSocket broadcast failed: {e}")
    
    return QuickTradeResponse(
        order_id=order.id,
        position_id=position_id,
        symbol=order.symbol,
        shares=order.quantity,
        fill_price=order.avg_fill_price,
        stop_price=request.stop_price,
        status=status,
    )

