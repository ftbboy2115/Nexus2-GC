"""
Order Routes
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status

from nexus2.api.schemas import (
    CreateOrderRequest,
    SubmitOrderRequest,
    OrderResponse,
    OrderListResponse,
    ErrorResponse,
)
from nexus2.api.dependencies import get_order_service, get_executor, get_order_repo
from nexus2.domain.orders import (
    OrderService,
    OrderRequest,
    OrderType,
    OrderSide,
    OrderStatus,
    OrderNotFoundError,
    InvalidTransitionError,
)
from nexus2.adapters.broker import OrderExecutor
from nexus2.db import OrderRepository
from nexus2.utils.time_utils import now_utc


router = APIRouter(prefix="/orders", tags=["orders"])


def _order_to_response(order) -> OrderResponse:
    """Convert domain Order to response."""
    return OrderResponse(
        id=order.id,
        symbol=order.symbol,
        side=order.side.value if hasattr(order.side, 'value') else order.side,
        order_type=order.order_type.value if hasattr(order.order_type, 'value') else order.order_type,
        quantity=order.quantity,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        tactical_stop=order.tactical_stop if hasattr(order, 'tactical_stop') else None,
        status=order.status.value if hasattr(order.status, 'value') else order.status,
        filled_quantity=order.filled_quantity,
        avg_fill_price=order.avg_fill_price,
        created_at=order.created_at,
        submitted_at=order.submitted_at if hasattr(order, 'submitted_at') else None,
        filled_at=order.filled_at if hasattr(order, 'filled_at') else None,
    )


def _db_order_to_response(order) -> OrderResponse:
    """Convert DB OrderModel to response."""
    return OrderResponse(
        id=UUID(order.id),
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        tactical_stop=order.tactical_stop,
        status=order.status,
        filled_quantity=order.filled_quantity,
        avg_fill_price=order.avg_fill_price,
        created_at=order.created_at,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
    )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    order_service: OrderService = Depends(get_order_service),
    order_repo: OrderRepository = Depends(get_order_repo),
):
    """Create a new order (DRAFT status)."""
    try:
        order_type = OrderType(request.order_type)
        side = OrderSide(request.side)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    domain_request = OrderRequest(
        symbol=request.symbol.upper(),
        side=side,
        quantity=request.quantity,
        order_type=order_type,
        limit_price=request.limit_price,
        stop_price=request.stop_price,
        tactical_stop=request.tactical_stop,
        risk_dollars=request.risk_dollars,
    )
    
    try:
        order = order_service.create_order(domain_request)
        
        # Persist to database
        order_repo.create({
            "id": str(order.id),
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "status": order.status.value,
            "quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "limit_price": str(order.limit_price) if order.limit_price else None,
            "stop_price": str(order.stop_price) if order.stop_price else None,
            "tactical_stop": str(order.tactical_stop) if order.tactical_stop else None,
            "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
            "created_at": order.created_at,
        })
        
        return _order_to_response(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=OrderListResponse)
async def list_orders(
    symbol: Optional[str] = None,
    status_filter: Optional[str] = None,
    order_service: OrderService = Depends(get_order_service),
    order_repo: OrderRepository = Depends(get_order_repo),
):
    """List orders with optional filters (fetches from database for persistence)."""
    # Fetch from database for persisted orders
    db_orders = order_repo.get_all(status=status_filter, limit=200)
    
    # Filter by symbol if provided
    if symbol:
        db_orders = [o for o in db_orders if o.symbol == symbol.upper()]
    
    return OrderListResponse(
        orders=[_db_order_to_response(o) for o in db_orders],
        total=len(db_orders),
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    order_service: OrderService = Depends(get_order_service),
):
    """Get order by ID."""
    order = order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return _order_to_response(order)


@router.post("/{order_id}/submit", response_model=OrderResponse)
async def submit_order(
    order_id: UUID,
    request: SubmitOrderRequest = SubmitOrderRequest(),
    order_service: OrderService = Depends(get_order_service),
    executor: OrderExecutor = Depends(get_executor),
    order_repo: OrderRepository = Depends(get_order_repo),
):
    """Submit order (and optionally execute via broker)."""
    try:
        order = order_service.submit_order(order_id)
        
        if request.execute:
            result = executor.execute_order(order_id)
            if not result.success:
                raise HTTPException(status_code=500, detail=result.error)
            # Refresh order state
            order = order_service.get_order(order_id)
        
        # Sync to database
        order_repo.update(str(order_id), {
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
            "submitted_at": order.submitted_at,
            "filled_at": order.filled_at,
        })
        
        return _order_to_response(order)
        
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    order_service: OrderService = Depends(get_order_service),
    executor: OrderExecutor = Depends(get_executor),
    order_repo: OrderRepository = Depends(get_order_repo),
):
    """Cancel an order."""
    from datetime import datetime
    
    # First check if order exists in database
    db_order = order_repo.get_by_id(str(order_id))
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if already cancelled or filled
    if db_order.status in ('cancelled', 'filled'):
        raise HTTPException(status_code=400, detail=f"Cannot cancel order with status: {db_order.status}")
    
    try:
        # Try to cancel via executor (for broker orders)
        order = executor.cancel_order(order_id)
        
        # Update database
        order_repo.update(str(order_id), {
            "status": "cancelled",
            "cancelled_at": now_utc(),
        })
        
        return _order_to_response(order)
        
    except OrderNotFoundError:
        # Order not in memory but exists in DB - just update DB directly
        order_repo.update(str(order_id), {
            "status": "cancelled",
            "cancelled_at": now_utc(),
        })
        
        # Return updated order from DB
        updated = order_repo.get_by_id(str(order_id))
        return _db_order_to_response(updated)
        
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
