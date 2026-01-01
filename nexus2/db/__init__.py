"""
Database Package

SQLite persistence for Nexus 2.
"""

from nexus2.db.database import (
    engine,
    SessionLocal,
    Base,
    get_db,
    init_db,
)
from nexus2.db.models import (
    OrderModel,
    FillModel,
    PositionModel,
    PositionExitModel,
    SettingsModel,
    SchedulerSettingsModel,
    WatchlistCandidateModel,
)
from nexus2.db.repository import (
    OrderRepository,
    PositionRepository,
    PositionExitRepository,
    SettingsRepository,
    SchedulerSettingsRepository,
    WatchlistRepository,
)

__all__ = [
    # Database
    "engine",
    "SessionLocal",
    "Base",
    "get_db",
    "init_db",
    # Models
    "OrderModel",
    "FillModel",
    "PositionModel",
    "PositionExitModel",
    "SettingsModel",
    "SchedulerSettingsModel",
    "WatchlistCandidateModel",
    # Repositories
    "OrderRepository",
    "PositionRepository",
    "PositionExitRepository",
    "SettingsRepository",
    "SchedulerSettingsRepository",
    "WatchlistRepository",
]
