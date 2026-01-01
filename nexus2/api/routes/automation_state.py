"""
Automation State Management

Global instances and accessors for automation components.
Extracted from automation.py for cleaner separation of concerns.
"""

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
