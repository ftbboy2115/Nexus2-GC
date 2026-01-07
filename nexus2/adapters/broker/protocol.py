"""
Broker Protocol

Interface and models for broker implementations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Protocol
from uuid import UUID


class BrokerOrderStatus(Enum):
    """Order status as reported by broker."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class BrokerOrder:
    """Order as seen by the broker."""
    client_order_id: UUID          # Our order ID
    broker_order_id: str           # Broker's ID
    symbol: str
    side: str                      # "buy" or "sell"
    quantity: int
    order_type: str                # "market", "limit", "stop", "stop_limit"
    status: BrokerOrderStatus
    
    # Prices
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    
    # Fill tracking
    filled_quantity: int = 0
    avg_fill_price: Optional[Decimal] = None
    
    # Timestamps
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    @property
    def is_complete(self) -> bool:
        """True if order is in terminal state."""
        return self.status in (
            BrokerOrderStatus.FILLED,
            BrokerOrderStatus.CANCELLED,
            BrokerOrderStatus.REJECTED,
            BrokerOrderStatus.EXPIRED,
        )
    
    @property
    def remaining_quantity(self) -> int:
        """Shares remaining to be filled."""
        return self.quantity - self.filled_quantity


@dataclass(frozen=True)
class BrokerFill:
    """Fill notification from broker."""
    client_order_id: UUID
    broker_order_id: str
    quantity: int
    price: Decimal
    timestamp: datetime
    fee: Decimal = Decimal("0")


@dataclass
class BrokerPosition:
    """Position as reported by broker."""
    symbol: str
    quantity: int
    avg_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    # Optional fields for expanded view
    current_price: Optional[Decimal] = None
    change_today: Optional[Decimal] = None  # Today's % change


class BrokerProtocol(Protocol):
    """
    Interface for broker implementations.
    
    All brokers (paper, Alpaca, IBKR) implement this protocol.
    """
    
    def submit_order(
        self,
        client_order_id: UUID,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
    ) -> BrokerOrder:
        """
        Submit an order to the broker.
        
        Args:
            client_order_id: Our internal order ID
            symbol: Stock symbol
            side: "buy" or "sell"
            quantity: Number of shares
            order_type: "market", "limit", "stop", "stop_limit"
            limit_price: Limit price (required for limit/stop_limit)
            stop_price: Stop price (required for stop/stop_limit)
            
        Returns:
            BrokerOrder with broker's order ID and initial status
        """
        ...
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrder:
        """
        Cancel an order.
        
        Args:
            broker_order_id: Broker's order ID
            
        Returns:
            Updated BrokerOrder
        """
        ...
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrder:
        """
        Get current order status.
        
        Args:
            broker_order_id: Broker's order ID
            
        Returns:
            Current BrokerOrder state
        """
        ...
    
    def get_positions(self) -> Dict[str, BrokerPosition]:
        """
        Get all open positions.
        
        Returns:
            Dict of symbol -> BrokerPosition
        """
        ...
    
    def get_account_value(self) -> Decimal:
        """Get total account value."""
        ...
