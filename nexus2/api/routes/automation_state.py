"""
Automation State Management

Global instances and accessors for automation components.
Extracted from automation.py for cleaner separation of concerns.
"""

import threading
from typing import Optional, TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from nexus2.domain.automation.engine import AutomationEngine
    from nexus2.domain.automation.scheduler import AutomationScheduler
    from nexus2.domain.automation.monitor import PositionMonitor


# Global instances (initialized in lifespan)
_engine: Optional["AutomationEngine"] = None
_scheduler: Optional["AutomationScheduler"] = None
_monitor: Optional["PositionMonitor"] = None
_app = None

# Auto-start checker state
_auto_start_task = None
_auto_start_triggered_today = False

# Simulation broker singleton (thread-safe)
_sim_broker = None
_sim_broker_lock = threading.Lock()

# Recent exits for re-entry scanning (thread-safe)
# Format: [{"symbol": str, "closed_at": datetime, "setup_type": str}]
_recent_exits = []
_recent_exits_lock = threading.Lock()
RECENT_EXITS_MAX_DAYS = 7  # Auto-expire after 7 days


def get_engine() -> "AutomationEngine":
    """Get the automation engine instance."""
    if _engine is None:
        raise HTTPException(status_code=503, detail="Automation engine not initialized")
    return _engine


def set_engine(engine: "AutomationEngine"):
    """Set the automation engine instance."""
    global _engine
    _engine = engine


def get_scheduler() -> "AutomationScheduler":
    """Get the automation scheduler instance."""
    global _scheduler
    if _scheduler is None:
        from nexus2.domain.automation.scheduler import AutomationScheduler
        _scheduler = AutomationScheduler()
    return _scheduler


def get_monitor() -> "PositionMonitor":
    """Get the position monitor instance."""
    global _monitor
    from nexus2.domain.automation.monitor import PositionMonitor
    if _monitor is None:
        _monitor = PositionMonitor()
    return _monitor


def set_app(app):
    """Set the FastAPI app reference for background tasks."""
    global _app
    _app = app


def get_app():
    """Get the FastAPI app reference."""
    return _app


def get_auto_start_task():
    """Get the auto-start background task."""
    return _auto_start_task


def set_auto_start_task(task):
    """Set the auto-start background task."""
    global _auto_start_task
    _auto_start_task = task


def get_auto_start_triggered_today() -> bool:
    """Check if auto-start has already triggered today."""
    return _auto_start_triggered_today


def set_auto_start_triggered_today(value: bool):
    """Set whether auto-start has triggered today."""
    global _auto_start_triggered_today
    _auto_start_triggered_today = value


# ==================== SIMULATION BROKER ====================

def get_sim_broker():
    """
    Get the simulation broker instance (thread-safe).
    
    Returns None if not initialized yet.
    """
    with _sim_broker_lock:
        return _sim_broker


def set_sim_broker(broker):
    """
    Set the simulation broker instance (thread-safe).
    
    This is called when creating a new MockBroker for simulation trading.
    """
    global _sim_broker
    with _sim_broker_lock:
        _sim_broker = broker


def get_or_create_sim_broker(initial_cash: float | None = None):
    """
    Get existing sim broker or create a new one (thread-safe).
    
    Use this for lazy initialization in execute_callback.
    If initial_cash is None, uses settings.sim_initial_cash.
    """
    global _sim_broker
    with _sim_broker_lock:
        if _sim_broker is None:
            from nexus2.adapters.simulation.mock_broker import MockBroker
            # Use settings if no explicit initial_cash provided
            if initial_cash is None:
                from nexus2.api.routes.settings import get_settings
                initial_cash = get_settings().sim_initial_cash
            _sim_broker = MockBroker(initial_cash=initial_cash)
        return _sim_broker


# ==================== RECENT EXITS (Re-entry Scanning) ====================

# Cooldown settings (per docs/reentry_cooldown.md)
REENTRY_COOLDOWN_MINUTES = 30  # Time before re-entry allowed


def add_recent_exit(symbol: str, setup_type: str = "unknown", entry_price: float = None):
    """
    Add a symbol to recent exits for potential re-entry (thread-safe).
    
    Called when a position closes (stop hit, manual, or sync).
    Now tracks entry_price for cooldown price-recovery check.
    """
    from datetime import datetime
    global _recent_exits
    with _recent_exits_lock:
        # Remove if already exists (update timestamp)
        _recent_exits = [e for e in _recent_exits if e["symbol"] != symbol]
        _recent_exits.append({
            "symbol": symbol,
            "closed_at": datetime.utcnow(),
            "setup_type": setup_type,
            "entry_price": entry_price,  # For re-entry cooldown check
        })
        print(f"[ReEntry] Added {symbol} to recent exits ({len(_recent_exits)} total)")


def get_recent_exit_symbols() -> list[str]:
    """
    Get symbols from recent exits that haven't expired (thread-safe).
    
    Returns list of symbols closed within RECENT_EXITS_MAX_DAYS.
    """
    from datetime import datetime, timedelta
    with _recent_exits_lock:
        cutoff = datetime.utcnow() - timedelta(days=RECENT_EXITS_MAX_DAYS)
        valid_exits = [e for e in _recent_exits if e["closed_at"] > cutoff]
        return [e["symbol"] for e in valid_exits]


def get_recent_exit_info(symbol: str) -> dict | None:
    """
    Get detailed exit info for a symbol (thread-safe).
    
    Returns dict with closed_at, entry_price, etc. or None if not found.
    """
    with _recent_exits_lock:
        for exit in _recent_exits:
            if exit["symbol"] == symbol:
                return exit
        return None


def can_reenter(symbol: str, current_price: float) -> tuple[bool, str]:
    """
    Check if re-entry is allowed for a recently stopped symbol (thread-safe).
    
    Implements hybrid cooldown logic (per docs/reentry_cooldown.md):
    - Must wait 30 minutes after stop hit
    - Current price must exceed the stopped trade's entry price
    
    Returns:
        (allowed: bool, reason: str)
    """
    from datetime import datetime, timedelta
    
    exit_info = get_recent_exit_info(symbol)
    if not exit_info:
        return (True, "Not in recent exits")
    
    closed_at = exit_info.get("closed_at")
    entry_price = exit_info.get("entry_price")
    
    if not closed_at:
        return (True, "No closed_at timestamp")
    
    # Check 1: Time cooldown (30 min)
    now = datetime.utcnow()
    cooldown_end = closed_at + timedelta(minutes=REENTRY_COOLDOWN_MINUTES)
    if now < cooldown_end:
        minutes_left = int((cooldown_end - now).total_seconds() / 60)
        return (False, f"Cooldown active ({minutes_left} min remaining)")
    
    # Check 2: Price recovery (current price > stopped entry price)
    if entry_price and current_price < entry_price:
        return (False, f"Price ${current_price:.2f} < stopped entry ${entry_price:.2f}")
    
    # Both conditions met - allow re-entry
    return (True, "Cooldown complete and price recovered")


def clear_recent_exit(symbol: str):
    """
    Remove a symbol from recent exits (thread-safe).
    
    Called when a position is successfully re-entered.
    """
    global _recent_exits
    with _recent_exits_lock:
        _recent_exits = [e for e in _recent_exits if e["symbol"] != symbol]
        print(f"[ReEntry] Removed {symbol} from recent exits")


def get_recent_exits_count() -> int:
    """Get count of symbols in recent exits queue."""
    with _recent_exits_lock:
        return len(_recent_exits)


