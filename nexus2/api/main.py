"""
Nexus 2 API

FastAPI application for the Nexus trading platform.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus2.domain.orders import OrderService
from nexus2.domain.positions import PositionService, TradeManagementService
from nexus2.adapters.broker import OrderExecutor
from nexus2.settings.risk_settings import PartialExitSettings
from nexus2.api.broker_factory import create_broker_by_type

from nexus2.api.routes import health, orders, positions, scanner, trade, settings, websocket, automation, watchlist, analytics
from nexus2.api.routes.settings import get_settings
from nexus2.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan.
    
    Initialize services on startup, cleanup on shutdown.
    """
    # Initialize database
    init_db()
    
    # Startup
    app.state.order_service = OrderService()
    app.state.position_service = PositionService()
    app.state.trade_service = TradeManagementService(PartialExitSettings())
    
    # Load open positions from database
    from nexus2.db import SessionLocal, PositionRepository
    db = SessionLocal()
    try:
        position_repo = PositionRepository(db)
        open_positions = position_repo.get_open()
        count = app.state.position_service.load_from_database(open_positions)
        print(f"[Startup] Loaded {count} open positions from database")
    finally:
        db.close()
    
    # Load saved settings and create broker
    saved_settings = get_settings()
    print(f"[Startup] Loaded settings: broker={saved_settings.broker_type}, account={saved_settings.active_account}")
    app.state.broker = create_broker_by_type(
        saved_settings.broker_type,
        saved_settings.active_account,
    )
    app.state.executor = OrderExecutor(
        order_service=app.state.order_service,
        broker=app.state.broker,
    )
    
    # Initialize automation engine
    from nexus2.domain.automation import AutomationEngine
    from nexus2.api.routes.automation import set_engine, set_app, start_auto_start_checker
    app.state.automation_engine = AutomationEngine()
    set_engine(app.state.automation_engine)
    print("[Startup] Automation engine initialized")
    
    # Set app reference for auto-start to access broker/market_data
    set_app(app)
    
    # Start auto-start checker (for headless server operation)
    start_auto_start_checker()
    print("[Startup] Auto-start checker running")
    
    yield
    
    # Shutdown - cleanup


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Nexus 2 API",
        description="KK-style trading platform API",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # CORS - Note: allow_credentials=True cannot be used with allow_origins=["*"]
    # For development, we allow all origins without credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(health.router)
    app.include_router(orders.router)
    app.include_router(positions.router)
    app.include_router(scanner.router)
    app.include_router(trade.router)
    app.include_router(settings.router)
    app.include_router(websocket.router)
    app.include_router(automation.router)
    app.include_router(watchlist.router)
    app.include_router(analytics.router)
    
    return app


# Default app instance
app = create_app()
