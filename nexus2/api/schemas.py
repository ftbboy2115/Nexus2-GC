"""
API Schemas

Pydantic models for request/response.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Order Schemas
# ============================================================================

class CreateOrderRequest(BaseModel):
    """Request to create a new order."""
    symbol: str = Field(..., description="Stock symbol")
    side: str = Field(..., description="buy or sell")
    quantity: int = Field(..., gt=0, description="Number of shares")
    order_type: str = Field(default="limit", description="market, limit, stop, stop_limit")
    limit_price: Optional[Decimal] = Field(None, description="Limit price")
    stop_price: Optional[Decimal] = Field(None, description="Stop price")
    tactical_stop: Optional[Decimal] = Field(None, description="Tactical stop for risk calc")
    risk_dollars: Optional[Decimal] = Field(None, description="Fixed dollar risk")
    setup_type: Optional[str] = Field(None, description="Setup type (ep, flag, htf)")


class SubmitOrderRequest(BaseModel):
    """Request to submit order to broker."""
    execute: bool = Field(default=True, description="Also execute via broker")


class OrderResponse(BaseModel):
    """Order response."""
    id: UUID
    symbol: str
    side: str
    order_type: str
    quantity: int
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    tactical_stop: Optional[Decimal]
    status: str
    filled_quantity: int
    avg_fill_price: Optional[Decimal]
    created_at: datetime
    submitted_at: Optional[datetime]
    filled_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """List of orders."""
    orders: List[OrderResponse]
    total: int


# ============================================================================
# Position Schemas
# ============================================================================

class PositionResponse(BaseModel):
    """Position response."""
    id: UUID
    symbol: str
    setup_type: Optional[str] = None
    entry_date: Optional[str] = None
    entry_price: Decimal
    shares: int
    remaining_shares: int
    initial_stop: Optional[Decimal] = None
    current_stop: Optional[Decimal] = None
    stop_type: Optional[str] = None
    status: str
    realized_pnl: Decimal
    days_held: int = 0
    
    class Config:
        from_attributes = True


class PositionListResponse(BaseModel):
    """List of positions."""
    positions: List[PositionResponse]
    total: int


class PartialExitRequest(BaseModel):
    """Request for partial exit."""
    shares: int = Field(..., gt=0)
    price: Decimal
    reason: str = Field(default="partial_profit")


class ClosePositionRequest(BaseModel):
    """Request to close position."""
    price: Decimal
    reason: str = Field(default="manual")


class PositionPerformance(BaseModel):
    """Position performance metrics."""
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    r_multiple: Decimal
    days_held: int


# ============================================================================
# Scanner Schemas
# ============================================================================

class ScannerRunRequest(BaseModel):
    """Request to run scanner."""
    mode: str = Field(default="gainers", description="Scan mode: gainers, actives, or trend_leaders")
    demo: bool = Field(default=False, description="Use demo/mock data (for testing)")
    symbols: Optional[List[str]] = Field(None, description="Symbols to scan (or use default universe)")
    limit: int = Field(default=20, ge=5, le=100, description="Max stocks to scan")
    min_price: Decimal = Field(default=Decimal("10"))
    max_price: Decimal = Field(default=Decimal("500"))
    min_volume: int = Field(default=500000)


class ScanResultResponse(BaseModel):
    """Single scan result."""
    symbol: str
    name: str
    price: str
    quality_score: int
    passes_filter: bool
    failed_criteria: List[str]
    tier: str
    rs_percentile: int
    adr_percent: str
    price_vs_ma50: str
    
    # EP-specific fields (from unified EP scanner)
    gap_percent: Optional[str] = None
    relative_volume: Optional[str] = None
    catalyst_type: Optional[str] = None
    catalyst_description: Optional[str] = None


class ScannerResultsResponse(BaseModel):
    """Scanner results."""
    results: List[ScanResultResponse]
    total: int
    scanned_at: datetime


# ============================================================================
# Health Schemas
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    mode: str  # "alpaca_paper", "alpaca_live", "sim"
    timestamp: datetime
    eastern_time: Optional[str] = None  # For timezone debugging


# ============================================================================
# Error Schemas
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
