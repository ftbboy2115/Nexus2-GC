"""
Order Models

Core entities and value objects for the Orders domain.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4


class OrderStatus(Enum):
    """Order lifecycle status."""
    DRAFT = "draft"                    # Created, not submitted
    PENDING = "pending"                # Submitted, awaiting fill
    PARTIALLY_FILLED = "partially_filled"  # Some shares filled
    FILLED = "filled"                  # Fully executed
    CANCELLED = "cancelled"            # Cancelled by user
    REJECTED = "rejected"              # Rejected by broker
    EXPIRED = "expired"                # Time-in-force expired


class OrderType(Enum):
    """Order execution type."""
    MARKET = "market"          # Execute at market price
    LIMIT = "limit"            # Execute at limit or better
    STOP = "stop"              # Becomes market when stop hit
    STOP_LIMIT = "stop_limit"  # Becomes limit when stop hit


class OrderSide(Enum):
    """Order direction."""
    BUY = "buy"    # Long entry or add
    SELL = "sell"  # Exit or partial exit


@dataclass(frozen=True)
class Fill:
    """Record of a partial or full order fill."""
    quantity: int
    price: Decimal
    timestamp: datetime
    fee: Decimal = Decimal("0")
    
    @property
    def value(self) -> Decimal:
        """Total value of this fill."""
        return self.price * self.quantity


@dataclass
class Order:
    """
    Order entity.
    
    Represents a single order through its lifecycle.
    """
    id: UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    status: OrderStatus = OrderStatus.DRAFT
    
    # Price levels
    limit_price: Optional[Decimal] = None   # For LIMIT/STOP_LIMIT
    stop_price: Optional[Decimal] = None    # For STOP/STOP_LIMIT
    
    # Fill tracking
    filled_quantity: int = 0
    avg_fill_price: Optional[Decimal] = None
    fills: List[Fill] = field(default_factory=list)
    
    # KK-style risk context
    tactical_stop: Optional[Decimal] = None     # Opening range low (LOD)
    risk_dollars: Optional[Decimal] = None      # Fixed risk per trade
    setup_id: Optional[UUID] = None             # Reference to EPSetup
    atr: Optional[Decimal] = None               # ATR at order creation
    
    # Add tracking
    is_add: bool = False
    parent_order_id: Optional[UUID] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Metadata
    notes: Optional[str] = None
    
    @property
    def remaining_quantity(self) -> int:
        """Shares remaining to be filled."""
        return self.quantity - self.filled_quantity
    
    @property
    def is_complete(self) -> bool:
        """True if order is in a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )
    
    @property
    def stop_distance(self) -> Optional[Decimal]:
        """Distance from entry to tactical stop."""
        if self.avg_fill_price and self.tactical_stop:
            return abs(self.avg_fill_price - self.tactical_stop)
        if self.limit_price and self.tactical_stop:
            return abs(self.limit_price - self.tactical_stop)
        return None
    
    @property
    def stop_atr_ratio(self) -> Optional[Decimal]:
        """Stop distance as multiple of ATR."""
        if self.stop_distance and self.atr and self.atr > 0:
            return self.stop_distance / self.atr
        return None
    
    def record_fill(self, fill: Fill) -> None:
        """Record a fill and update tracking."""
        self.fills.append(fill)
        self.filled_quantity += fill.quantity
        
        # Recalculate average fill price
        total_value = sum(f.price * f.quantity for f in self.fills)
        total_qty = sum(f.quantity for f in self.fills)
        self.avg_fill_price = total_value / total_qty if total_qty > 0 else None
        
        # Update status
        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
            self.filled_at = fill.timestamp
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED


@dataclass
class OrderRequest:
    """
    Request to create an order.
    
    Validated before Order creation.
    """
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    tactical_stop: Optional[Decimal] = None
    risk_dollars: Optional[Decimal] = None
    setup_id: Optional[UUID] = None
    atr: Optional[Decimal] = None
    is_add: bool = False
    parent_order_id: Optional[UUID] = None
    notes: Optional[str] = None
