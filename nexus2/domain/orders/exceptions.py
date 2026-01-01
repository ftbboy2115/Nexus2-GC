# Orders Domain Exceptions


class OrderError(Exception):
    """Base exception for order-related errors."""
    pass


class InvalidTransitionError(OrderError):
    """Raised when attempting an invalid state transition."""
    
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition: {from_status} → {to_status}")


class KKRuleViolationError(OrderError):
    """Base exception for KK-style rule violations."""
    pass


class AddOnWeaknessError(KKRuleViolationError):
    """Raised when attempting to add to a losing position."""
    
    def __init__(self, current_price, avg_price):
        self.current_price = current_price
        self.avg_price = avg_price
        super().__init__(
            f"Cannot add on weakness: current ${current_price} < avg ${avg_price}"
        )


class StopLooseningError(KKRuleViolationError):
    """Raised when attempting to loosen a stop."""
    
    def __init__(self, current_stop, new_stop):
        self.current_stop = current_stop
        self.new_stop = new_stop
        super().__init__(
            f"Cannot loosen stop: ${current_stop} → ${new_stop}"
        )


class ATRConstraintError(KKRuleViolationError):
    """Raised when stop distance exceeds ATR constraint."""
    
    def __init__(self, stop_distance, atr, ratio):
        self.stop_distance = stop_distance
        self.atr = atr
        self.ratio = ratio
        super().__init__(
            f"Stop distance ${stop_distance} exceeds 1x ATR ${atr} (ratio: {ratio:.2f})"
        )


class OrderNotFoundError(OrderError):
    """Raised when order ID not found."""
    
    def __init__(self, order_id):
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")
