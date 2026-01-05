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
