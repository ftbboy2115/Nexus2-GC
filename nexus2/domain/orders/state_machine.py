"""
Order State Machine

Defines valid state transitions for orders.
"""

from typing import Dict, Set

from nexus2.domain.orders.models import Order, OrderStatus
from nexus2.domain.orders.exceptions import InvalidTransitionError


# Valid transitions: from_status -> set of allowed to_statuses
VALID_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.DRAFT: {
        OrderStatus.PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PENDING: {
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    },
    # Terminal states - no transitions out
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
}


def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    """Check if a state transition is valid."""
    allowed = VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def validate_transition(from_status: OrderStatus, to_status: OrderStatus) -> None:
    """
    Validate a state transition.
    
    Raises:
        InvalidTransitionError: If transition is not allowed
    """
    if not can_transition(from_status, to_status):
        raise InvalidTransitionError(from_status.value, to_status.value)


def transition(order: Order, to_status: OrderStatus) -> Order:
    """
    Transition an order to a new status.
    
    Args:
        order: Order to transition
        to_status: Target status
        
    Returns:
        Order with updated status
        
    Raises:
        InvalidTransitionError: If transition is not allowed
    """
    validate_transition(order.status, to_status)
    order.status = to_status
    return order
