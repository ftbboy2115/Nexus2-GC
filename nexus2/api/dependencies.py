"""
API Dependencies

Shared dependencies for FastAPI routes.
"""

from typing import Generator
from fastapi import Request, Depends
from sqlalchemy.orm import Session

from nexus2.domain.orders import OrderService
from nexus2.domain.positions import PositionService, TradeManagementService
from nexus2.adapters.broker import PaperBroker, OrderExecutor
from nexus2.settings.risk_settings import PartialExitSettings
from nexus2.db import SessionLocal, OrderRepository, PositionRepository, PositionExitRepository, SettingsRepository


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_order_repo(db: Session = Depends(get_db)) -> OrderRepository:
    """Get OrderRepository with database session."""
    return OrderRepository(db)


def get_position_repo(db: Session = Depends(get_db)) -> PositionRepository:
    """Get PositionRepository with database session."""
    return PositionRepository(db)


def get_position_exit_repo(db: Session = Depends(get_db)) -> PositionExitRepository:
    """Get PositionExitRepository with database session."""
    return PositionExitRepository(db)


def get_settings_repo(db: Session = Depends(get_db)) -> SettingsRepository:
    """Get SettingsRepository with database session."""
    return SettingsRepository(db)


def get_order_service(request: Request) -> OrderService:
    """Get OrderService from app state."""
    return request.app.state.order_service


def get_position_service(request: Request) -> PositionService:
    """Get PositionService from app state."""
    return request.app.state.position_service


def get_trade_service(request: Request) -> TradeManagementService:
    """Get TradeManagementService from app state."""
    return request.app.state.trade_service


def get_executor(request: Request) -> OrderExecutor:
    """Get OrderExecutor from app state."""
    return request.app.state.executor


def get_broker(request: Request) -> PaperBroker:
    """Get broker from app state."""
    return request.app.state.broker
