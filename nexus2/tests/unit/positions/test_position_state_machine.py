"""
Tests for Position State Machine

Verifies state transitions and invariants.
"""

import pytest
from nexus2.domain.positions.position_state_machine import (
    PositionStatus,
    can_transition,
    validate_transition,
    transition_position,
    is_terminal,
    is_active,
    is_pending,
    InvalidPositionTransitionError,
)


class TestPositionStatus:
    """Test PositionStatus enum values."""
    
    def test_all_statuses_defined(self):
        """Verify all expected statuses exist."""
        assert PositionStatus.PENDING_FILL.value == "pending_fill"
        assert PositionStatus.OPEN.value == "open"
        assert PositionStatus.SCALING.value == "scaling"
        assert PositionStatus.PARTIAL.value == "partial"
        assert PositionStatus.CLOSED.value == "closed"
        assert PositionStatus.REJECTED.value == "rejected"


class TestValidTransitions:
    """Test valid state transitions."""
    
    def test_pending_fill_to_open(self):
        """Order fill confirmed -> OPEN."""
        assert can_transition(PositionStatus.PENDING_FILL, PositionStatus.OPEN)
    
    def test_pending_fill_to_rejected(self):
        """Order rejected -> REJECTED."""
        assert can_transition(PositionStatus.PENDING_FILL, PositionStatus.REJECTED)
    
    def test_open_to_scaling(self):
        """Add order submitted (Warrior) -> SCALING."""
        assert can_transition(PositionStatus.OPEN, PositionStatus.SCALING)
    
    def test_open_to_partial(self):
        """Partial exit -> PARTIAL."""
        assert can_transition(PositionStatus.OPEN, PositionStatus.PARTIAL)
    
    def test_open_to_closed(self):
        """Full exit -> CLOSED."""
        assert can_transition(PositionStatus.OPEN, PositionStatus.CLOSED)
    
    def test_scaling_to_open(self):
        """Add fills or rejected -> back to OPEN."""
        assert can_transition(PositionStatus.SCALING, PositionStatus.OPEN)
    
    def test_partial_to_closed(self):
        """Remaining shares exited -> CLOSED."""
        assert can_transition(PositionStatus.PARTIAL, PositionStatus.CLOSED)


class TestInvalidTransitions:
    """Test invalid state transitions are blocked."""
    
    def test_pending_fill_cannot_go_to_partial(self):
        """Cannot partial exit before fill."""
        assert not can_transition(PositionStatus.PENDING_FILL, PositionStatus.PARTIAL)
    
    def test_pending_fill_cannot_go_to_closed(self):
        """Cannot close before fill."""
        assert not can_transition(PositionStatus.PENDING_FILL, PositionStatus.CLOSED)
    
    def test_open_cannot_go_to_pending_fill(self):
        """Cannot go backwards to pending."""
        assert not can_transition(PositionStatus.OPEN, PositionStatus.PENDING_FILL)
    
    def test_closed_cannot_transition(self):
        """Terminal state - no transitions."""
        assert not can_transition(PositionStatus.CLOSED, PositionStatus.OPEN)
        assert not can_transition(PositionStatus.CLOSED, PositionStatus.PARTIAL)
    
    def test_rejected_cannot_transition(self):
        """Terminal state - no transitions."""
        assert not can_transition(PositionStatus.REJECTED, PositionStatus.OPEN)
        assert not can_transition(PositionStatus.REJECTED, PositionStatus.PENDING_FILL)
    
    def test_partial_cannot_go_to_open(self):
        """Cannot un-partial a position."""
        assert not can_transition(PositionStatus.PARTIAL, PositionStatus.OPEN)


class TestValidateTransition:
    """Test validate_transition raises on invalid."""
    
    def test_valid_transition_no_error(self):
        """Valid transition should not raise."""
        validate_transition(PositionStatus.PENDING_FILL, PositionStatus.OPEN)
    
    def test_invalid_transition_raises(self):
        """Invalid transition should raise InvalidPositionTransitionError."""
        with pytest.raises(InvalidPositionTransitionError) as exc:
            validate_transition(PositionStatus.CLOSED, PositionStatus.OPEN)
        
        assert exc.value.from_status == "closed"
        assert exc.value.to_status == "open"


class TestTransitionPosition:
    """Test transition_position function."""
    
    def test_transition_returns_new_status(self):
        """Successful transition returns new status string."""
        result = transition_position("pending_fill", PositionStatus.OPEN)
        assert result == "open"
    
    def test_transition_from_legacy_open(self):
        """Legacy 'open' status works for normal transitions."""
        result = transition_position("open", PositionStatus.PARTIAL)
        assert result == "partial"
    
    def test_transition_from_unknown_status(self):
        """Unknown status allows any transition (graceful handling)."""
        result = transition_position("unknown_legacy", PositionStatus.OPEN)
        assert result == "open"
    
    def test_invalid_transition_raises(self):
        """Invalid transition raises error."""
        with pytest.raises(InvalidPositionTransitionError):
            transition_position("closed", PositionStatus.OPEN)


class TestStatusHelpers:
    """Test helper functions."""
    
    def test_is_terminal_closed(self):
        """CLOSED is terminal."""
        assert is_terminal("closed")
    
    def test_is_terminal_rejected(self):
        """REJECTED is terminal."""
        assert is_terminal("rejected")
    
    def test_is_terminal_open_false(self):
        """OPEN is not terminal."""
        assert not is_terminal("open")
    
    def test_is_active_open(self):
        """OPEN is active."""
        assert is_active("open")
    
    def test_is_active_scaling(self):
        """SCALING is active."""
        assert is_active("scaling")
    
    def test_is_active_partial(self):
        """PARTIAL is active."""
        assert is_active("partial")
    
    def test_is_active_closed_false(self):
        """CLOSED is not active."""
        assert not is_active("closed")
    
    def test_is_active_pending_fill_false(self):
        """PENDING_FILL is not active (not yet filled)."""
        assert not is_active("pending_fill")
    
    def test_is_pending_pending_fill(self):
        """PENDING_FILL is pending."""
        assert is_pending("pending_fill")
    
    def test_is_pending_open_false(self):
        """OPEN is not pending."""
        assert not is_pending("open")
