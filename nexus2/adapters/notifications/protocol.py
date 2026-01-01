"""
Notification Protocol

Interface for notification services.
"""

from typing import Protocol, Optional


class NotificationService(Protocol):
    """
    Protocol for notification implementations.
    
    Used by TradeManagementService for alerts.
    """
    
    def send_trade_alert(self, message: str, trade_id: str) -> None:
        """Send a trade-related alert."""
        ...
    
    def send_scanner_alert(self, message: str) -> None:
        """Send a scanner alert."""
        ...
    
    def send_system_alert(self, message: str, level: str = "info") -> None:
        """Send a system alert (info, warning, error)."""
        ...
