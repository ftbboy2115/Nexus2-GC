"""
Nexus 2 API

FastAPI application for the Nexus trading platform.
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus2.domain.orders import OrderService
from nexus2.domain.positions import PositionService, TradeManagementService
from nexus2.adapters.broker import OrderExecutor
from nexus2.settings.risk_settings import PartialExitSettings
from nexus2.api.broker_factory import create_broker_by_type

from nexus2.api.routes import health, orders, positions, scanner, trade, settings, websocket, automation, watchlist, analytics, automation_simulation, ma_check_routes, monitor_routes, scheduler_routes, docs_routes, preferences, warrior_routes, trade_event_routes  # v3
from nexus2.api.routes.settings import get_settings
from nexus2.db import init_db

# Configure logging with timestamps
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%H:%M:%S'
)
# Suppress httpx INFO logs to prevent API key exposure in URLs
logging.getLogger("httpx").setLevel(logging.WARNING)

# Track Ctrl+C presses for reliable shutdown on Windows
_ctrl_c_count = 0

def _shutdown_fmp_handler(signum, frame):
    """Signal handler for graceful shutdown on Ctrl+C.
    
    First Ctrl+C: Set FMP shutdown flag, warn user
    Second Ctrl+C: Force exit immediately
    """
    global _ctrl_c_count
    _ctrl_c_count += 1
    
    if _ctrl_c_count == 1:
        print("\n[Shutdown] Ctrl+C received - setting shutdown flag...")
        try:
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            fmp = get_fmp_adapter()
            fmp._shutdown = True
            print("[Shutdown] FMP shutdown flag set - scan will abort shortly")
            print("[Shutdown] Press Ctrl+C again to force exit")
        except Exception as e:
            print(f"[Shutdown] FMP flag error: {e}")
    else:
        # Second+ Ctrl+C: Force exit
        print("\n[Shutdown] Force exit - goodbye!")
        sys.exit(0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan.
    
    Initialize services on startup, cleanup on shutdown.
    """
    # Initialize database
    init_db()
    
    # Register signal handler for graceful shutdown
    # Only works in main thread (skip in TestClient which runs in threads)
    import threading
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _shutdown_fmp_handler)
        print("[Startup] Graceful shutdown signal handler registered")
    else:
        print("[Startup] Skipping signal handler (not main thread)")
    
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
    
    # Auto-enable Warrior Alpaca broker (Account B) and wire callbacks
    # Can be disabled via: 1) GUI toggle, 2) WARRIOR_AUTO_ENABLE=false in .env
    import os
    from nexus2.db.warrior_settings import get_auto_enable
    
    # Env var takes precedence (for emergency override), otherwise use persisted setting
    env_override = os.getenv("WARRIOR_AUTO_ENABLE", "").lower()
    if env_override == "false":
        warrior_auto_enable = False
        print("[Startup] Warrior auto-enable disabled via WARRIOR_AUTO_ENABLE=false env var")
    else:
        warrior_auto_enable = get_auto_enable()
        if not warrior_auto_enable:
            print("[Startup] Warrior auto-enable disabled via settings")
    
    if warrior_auto_enable:
        try:
            from nexus2.api.routes.warrior_broker_routes import create_warrior_alpaca_broker, set_warrior_alpaca_broker, wire_warrior_callbacks
            warrior_broker = create_warrior_alpaca_broker()
            if warrior_broker:
                set_warrior_alpaca_broker(warrior_broker)
                print("[Startup] Warrior Alpaca broker (Account B) auto-enabled")
                # Wire callbacks and sync positions automatically
                try:
                    result = await wire_warrior_callbacks(warrior_broker)
                    print(f"[Startup] Warrior callbacks wired, account value: ${result.get('account_value', 0):.2f}")
                    
                    # Auto-start engine (scan loop) when toggle is ON
                    from nexus2.api.routes.warrior_routes import get_engine
                    engine = get_engine()
                    await engine.start()
                    print("[Startup] Warrior engine auto-started")
                except Exception as wire_err:
                    print(f"[Startup] Warrior callback wiring failed (will need manual enable): {wire_err}")
            else:
                print("[Startup] Warrior Alpaca broker not available (missing credentials)")
        except Exception as e:
            print(f"[Startup] Warrior broker auto-enable failed: {e}")
    
    # Create shared FMP adapter singleton first
    from nexus2.adapters.market_data.fmp_adapter import FMPAdapter, set_fmp_adapter
    fmp_adapter = FMPAdapter()
    set_fmp_adapter(fmp_adapter)  # Set global singleton for all get_fmp_adapter calls
    print("[Startup] FMP adapter singleton initialized")
    
    # Create UnifiedMarketData (wraps FMP singleton + adds get_adr_percent, get_historical_bars)
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    app.state.market_data = UnifiedMarketData()  # Uses FMP singleton internally
    print("[Startup] Unified market data adapter initialized")
    
    # Inject shared FMP adapter into RS service (for unified rate limiting)
    from nexus2.domain.scanner.rs_service import get_rs_service
    get_rs_service().set_fmp_adapter(fmp_adapter)
    
    # Set app reference for auto-start to access broker/market_data
    set_app(app)
    
    # Start auto-start checker (for headless server operation)
    start_auto_start_checker()
    print("[Startup] Auto-start checker running")
    
    # Auto-resume NAC scheduler if it was running before restart
    # NOTE: NAC only runs during regular market hours (9:30 AM - 4:00 PM ET)
    from nexus2.db.database import get_session
    from nexus2.db import SchedulerSettingsRepository
    from nexus2.adapters.market_data.market_calendar import get_market_calendar
    
    try:
        # Check if market is actually open (NAC doesn't trade extended hours)
        calendar = get_market_calendar()
        market_status = calendar.get_market_status()
        
        if not market_status.is_open:
            print(f"[Startup] NAC scheduler not resuming - market is closed (reason: {market_status.reason})")
        else:
            with get_session() as db:
                settings = SchedulerSettingsRepository(db).get()
                if settings and settings.scheduler_running == "true":
                    print("[Startup] NAC scheduler was running before restart - auto-resuming...")
                    # Import and trigger scheduler start
                    from nexus2.api.routes.scheduler_routes import start_scheduler
                    from nexus2.api.routes.automation_state import get_engine
                    
                    # Create a mock request with app state
                    from unittest.mock import MagicMock
                    mock_request = MagicMock()
                    mock_request.app = app
                    
                    # Start in background task to not block startup
                    # Delay 60s to let Warrior scan complete first and avoid FMP rate limit overlap
                    async def resume_scheduler():
                        try:
                            print("[Startup] NAC scheduler resume delayed 60s (FMP rate limit protection)")
                            await asyncio.sleep(60)
                            # Re-check market is still open after delay
                            if not calendar.get_market_status().is_open:
                                print("[Startup] NAC scheduler resume cancelled - market closed during delay")
                                return
                            result = await start_scheduler(mock_request, engine=get_engine())
                            print(f"[Startup] NAC scheduler auto-resumed: {result.get('message', 'OK')}")
                        except Exception as e:
                            print(f"[Startup] NAC scheduler auto-resume failed: {e}")
                    
                    asyncio.create_task(resume_scheduler())
                else:
                    print("[Startup] NAC scheduler was not running - skipping auto-resume")
    except Exception as e:
        print(f"[Startup] NAC auto-resume check failed: {e}")
    
    yield
    
    # Shutdown - cleanup
    print("[Shutdown] Stopping automation services...")
    
    # Signal FMP adapter to stop waiting on rate limits
    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
    try:
        fmp = get_fmp_adapter()
        fmp._shutdown = True
        print("[Shutdown] FMP adapter shutdown flag set")
    except Exception as e:
        print(f"[Shutdown] FMP shutdown flag error: {e}")
    
    # Stop scheduler
    from nexus2.api.routes.automation_state import get_scheduler, get_monitor
    try:
        scheduler = get_scheduler()
        if scheduler.is_running:
            await scheduler.stop()
            print("[Shutdown] Scheduler stopped")
    except Exception as e:
        print(f"[Shutdown] Scheduler stop error: {e}")
    
    # Stop monitor
    try:
        monitor = get_monitor()
        if monitor._running:
            await monitor.stop()
            print("[Shutdown] Monitor stopped")
    except Exception as e:
        print(f"[Shutdown] Monitor stop error: {e}")
    
    # Cancel auto-start checker
    from nexus2.api.routes.automation_state import get_auto_start_task
    auto_start_task = get_auto_start_task()
    if auto_start_task and not auto_start_task.done():
        auto_start_task.cancel()
        try:
            await auto_start_task
        except asyncio.CancelledError:
            pass
        print("[Shutdown] Auto-start checker cancelled")
    
    print("[Shutdown] Cleanup complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Nexus 2 API",
        description="KK-style trading platform API",
        version="0.2.9",
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
    app.include_router(automation_simulation.router)
    app.include_router(watchlist.router)
    app.include_router(analytics.router)
    app.include_router(ma_check_routes.router)
    app.include_router(monitor_routes.router)
    app.include_router(scheduler_routes.router)
    app.include_router(docs_routes.router)
    app.include_router(preferences.router)
    app.include_router(warrior_routes.router)
    app.include_router(trade_event_routes.router)
    
    return app


# Default app instance
app = create_app()
