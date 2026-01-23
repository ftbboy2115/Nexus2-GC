"""
Pending Approvals Queue

Tracks quote divergence decisions awaiting human approval via Discord.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
from enum import Enum

from nexus2.utils.time_utils import now_utc


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED_FMP = "approved_fmp"
    APPROVED_ALPACA = "approved_alpaca"
    SKIPPED = "skipped"  # Skipped for duration
    AUTO_APPROVED = "auto_approved"  # Timeout, used FMP default


@dataclass
class PendingApproval:
    """A quote divergence decision awaiting human approval."""
    symbol: str
    time_window: str
    alpaca_price: float
    fmp_price: float
    divergence_pct: float
    message_id: Optional[int] = None  # Discord message ID
    created_at: datetime = field(default_factory=now_utc)
    expires_at: datetime = field(default_factory=lambda: now_utc() + timedelta(seconds=30))
    status: ApprovalStatus = ApprovalStatus.PENDING
    selected_source: Optional[str] = None  # "FMP" or "Alpaca"
    
    def is_expired(self) -> bool:
        """Check if approval has timed out."""
        return now_utc() >= self.expires_at


class PendingApprovalQueue:
    """
    Thread-safe queue for pending quote approvals.
    
    Symbols are keyed by uppercase symbol name.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._pending: Dict[str, PendingApproval] = {}
        self._callbacks: list[Callable[[PendingApproval], None]] = []
    
    def add(self, approval: PendingApproval) -> None:
        """Add a pending approval."""
        with self._lock:
            self._pending[approval.symbol.upper()] = approval
    
    def get(self, symbol: str) -> Optional[PendingApproval]:
        """Get pending approval for symbol."""
        with self._lock:
            return self._pending.get(symbol.upper())
    
    def resolve(
        self,
        symbol: str,
        status: ApprovalStatus,
        selected_source: Optional[str] = None,
    ) -> Optional[PendingApproval]:
        """
        Resolve a pending approval.
        
        Returns the resolved approval or None if not found.
        """
        with self._lock:
            approval = self._pending.get(symbol.upper())
            if approval:
                approval.status = status
                approval.selected_source = selected_source
                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(approval)
                    except Exception:
                        pass
                return approval
            return None
    
    def remove(self, symbol: str) -> None:
        """Remove a pending approval."""
        with self._lock:
            self._pending.pop(symbol.upper(), None)
    
    def get_all_pending(self) -> list[PendingApproval]:
        """Get all pending approvals that haven't expired."""
        with self._lock:
            return [a for a in self._pending.values() if a.status == ApprovalStatus.PENDING]
    
    def cleanup_expired(self) -> list[PendingApproval]:
        """
        Auto-approve expired pending approvals with FMP default.
        
        Returns list of auto-approved items.
        """
        auto_approved = []
        with self._lock:
            for symbol, approval in list(self._pending.items()):
                if approval.status == ApprovalStatus.PENDING and approval.is_expired():
                    approval.status = ApprovalStatus.AUTO_APPROVED
                    approval.selected_source = "FMP"
                    auto_approved.append(approval)
        return auto_approved
    
    def register_callback(self, callback: Callable[[PendingApproval], None]) -> None:
        """Register callback to be notified when approvals are resolved."""
        self._callbacks.append(callback)
    
    def set_message_id(self, symbol: str, message_id: int) -> None:
        """Set Discord message ID for a pending approval."""
        with self._lock:
            approval = self._pending.get(symbol.upper())
            if approval:
                approval.message_id = message_id


# Singleton
_queue: Optional[PendingApprovalQueue] = None


def get_pending_queue() -> PendingApprovalQueue:
    """Get singleton pending approval queue."""
    global _queue
    if _queue is None:
        _queue = PendingApprovalQueue()
    return _queue
