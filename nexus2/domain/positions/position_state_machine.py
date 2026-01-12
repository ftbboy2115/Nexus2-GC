"""
Position State Machine

Defines valid state transitions for positions through their lifecycle.
Enforces invariants to prevent invalid state changes.

States:
    PENDING_FILL -> OPEN -> PARTIAL -> CLOSED
         |           |
         v           v
      REJECTED    SCALING (Warrior adds)
"""

from enum import Enum
from typing import Dict, Set


class PositionStatus(Enum):
    """Status of a position in its lifecycle."""
    PENDING_FILL = "pending_fill"  # Order submitted, awaiting fill
    OPEN = "open"                   # Order filled, position active
    SCALING = "scaling"             # Add order pending (Warrior)
    PARTIAL = "partial"             # Some shares exited
    CLOSED = "closed"               # All shares exited
    REJECTED = "rejected"           # Order rejected by broker


# Valid transitions: from_status -> set of allowed to_statuses
VALID_TRANSITIONS: Dict[PositionStatus, Set[PositionStatus]] = {
    PositionStatus.PENDING_FILL: {
        PositionStatus.OPEN,      # Fill confirmed
        PositionStatus.REJECTED,  # Order rejected
    },
    PositionStatus.OPEN: {
        PositionStatus.SCALING,   # Add order submitted (Warrior)
        PositionStatus.PARTIAL,   # Partial exit
        PositionStatus.CLOSED,    # Full exit
    },
    PositionStatus.SCALING: {
        PositionStatus.OPEN,      # Add fills or is rejected
    },
    PositionStatus.PARTIAL: {
        PositionStatus.CLOSED,    # Remaining shares exited
    },
    # Terminal states - no transitions out
    PositionStatus.CLOSED: set(),
    PositionStatus.REJECTED: set(),
}


class InvalidPositionTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid position transition: {from_status} -> {to_status}"
        )


def can_transition(from_status: PositionStatus, to_status: PositionStatus) -> bool:
    """Check if a state transition is valid."""
    allowed = VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def validate_transition(from_status: PositionStatus, to_status: PositionStatus) -> None:
    """
    Validate a state transition.
    
    Raises:
        InvalidPositionTransitionError: If transition is not allowed
    """
    if not can_transition(from_status, to_status):
        raise InvalidPositionTransitionError(from_status.value, to_status.value)


def transition_position(current_status: str, to_status: PositionStatus) -> str:
    """
    Transition a position to a new status.
    
    Args:
        current_status: Current status string (from DB)
        to_status: Target status enum
        
    Returns:
        New status string
        
    Raises:
        InvalidPositionTransitionError: If transition is not allowed
    """
    # Handle legacy "open" status gracefully
    try:
        from_status = PositionStatus(current_status)
    except ValueError:
        # Unknown status - allow transition to any valid state
        return to_status.value
    
    validate_transition(from_status, to_status)
    return to_status.value


def is_terminal(status: str) -> bool:
    """Check if a status is terminal (no further transitions allowed)."""
    try:
        pos_status = PositionStatus(status)
        return len(VALID_TRANSITIONS.get(pos_status, set())) == 0
    except ValueError:
        return False


def is_active(status: str) -> bool:
    """Check if a position is actively held (not closed/rejected)."""
    return status in (
        PositionStatus.OPEN.value,
        PositionStatus.SCALING.value,
        PositionStatus.PARTIAL.value,
    )


def is_pending(status: str) -> bool:
    """Check if a position is awaiting fill confirmation."""
    return status == PositionStatus.PENDING_FILL.value
