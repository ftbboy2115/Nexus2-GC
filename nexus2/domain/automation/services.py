"""
Automation Services

Service functions that connect the automation engine to other Nexus components.
"""

import logging
from typing import List, Optional
from decimal import Decimal

from nexus2.domain.automation.signals import Signal, SignalGenerator
from nexus2.domain.automation.engine import AutomationEngine


logger = logging.getLogger(__name__)


async def create_scanner_callback(demo: bool = False):
    """
    Create a scanner callback function for the automation engine.
    
    This wraps the scanner API logic so the engine can call it.
    
    DEPRECATED: Use create_unified_scanner_callback for production.
    """
    from nexus2.api.routes.scanner import run_scanner, ScannerRunRequest
    
    async def scanner_func(mode: str = "gainers", limit: int = 20) -> List[dict]:
        """Run the scanner and return results as dicts."""
        request = ScannerRunRequest(mode=mode, limit=limit, demo=demo)
        response = await run_scanner(request)
        
        # Convert ScanResultResponse to dicts for SignalGenerator
        return [
            {
                "symbol": r.symbol,
                "name": r.name,
                "price": r.price,
                "quality_score": r.quality_score,
                "passes_filter": r.passes_filter,
                "tier": r.tier.upper(),
                "rs_percentile": r.rs_percentile,
                "adr_percent": r.adr_percent,
            }
            for r in response.results
        ]
    
    return scanner_func


async def create_unified_scanner_callback(
    min_quality: int = 7,
    max_stop_percent: float = 5.0,
    stop_mode: str = "atr",
    max_stop_atr: float = 1.0,
    scan_modes: List[str] = None,
    htf_frequency: str = "every_cycle",
    sim_mode: bool = False,  # NEW: Use MockMarketData when True
):
    """
    Create a scanner callback that uses the UnifiedScannerService.
    
    This runs EP, Breakout, and HTF scanners and returns unified signals.
    This is the recommended callback for production automation.
    
    Args:
        min_quality: Minimum quality score to include signals
        max_stop_percent: Maximum stop distance as percentage
        stop_mode: "atr" (KK-style) or "percent"
        max_stop_atr: Maximum stop distance as ATR multiple (used when stop_mode="atr")
        scan_modes: List of scanner modes to run, e.g. ["ep", "breakout", "htf"]
        htf_frequency: "every_cycle" or "market_open" (HTF only runs on first scan)
        sim_mode: When True, use MockMarketData instead of live FMP data
    """
    from nexus2.domain.automation.unified_scanner import (
        UnifiedScannerService,
        UnifiedScanSettings,
        ScanMode,
    )
    from datetime import date
    
    # Default to all scanners if not specified
    if scan_modes is None:
        scan_modes = ["ep", "breakout", "htf"]
    
    # State tracking for HTF "market_open" mode
    # Tracks when HTF last ran (needs to be after 9am today to skip)
    htf_state = {"last_htf_run": None}  # datetime of last HTF run
    
    # Convert scan_modes list to ScanMode enums
    def modes_from_list(mode_list: List[str]) -> List[ScanMode]:
        mode_map = {
            "all": ScanMode.ALL,
            "ep": ScanMode.EP_ONLY,
            "breakout": ScanMode.BREAKOUT_ONLY,
            "htf": ScanMode.HTF_ONLY,
        }
        modes = []
        for m in mode_list:
            m_lower = m.lower().strip()
            if m_lower in mode_map:
                modes.append(mode_map[m_lower])
        # If no valid modes, default to ALL
        return modes if modes else [ScanMode.ALL]
    
    # Pre-compute the enabled modes from settings
    base_scan_modes = scan_modes.copy()
    
    # Get market data provider (MockMarketData for sim, live for production)
    market_data = None
    if sim_mode:
        from nexus2.adapters.simulation import get_mock_market_data
        market_data = get_mock_market_data()
        logger.info(f"Scanner configured: modes={scan_modes}, SIMULATION MODE (using MockMarketData)")
    else:
        logger.info(f"Scanner configured: modes={scan_modes}, stop_mode={stop_mode}, min_quality={min_quality}, htf_frequency={htf_frequency}")
    
    async def unified_scanner_func(mode: str = "all", limit: int = 20) -> List[dict]:
        """
        Run unified scanner and return results as dicts.
        
        Args:
            mode: Scanner mode override - "all", "ep", "breakout", "htf"
                  (Note: this is overridden by scan_modes from settings)
            limit: Max results per scanner (not total)
        """
        from datetime import datetime, time as dt_time
        import pytz
        
        now = datetime.now(pytz.timezone('US/Eastern'))
        today = now.date()
        nine_am_today = datetime.combine(today, dt_time(9, 0), tzinfo=pytz.timezone('US/Eastern'))
        
        # Determine which scan modes to run this cycle
        current_scan_modes = base_scan_modes.copy()
        
        # HTF frequency logic: if "market_open", only include HTF once since 9am today
        if htf_frequency == "market_open" and "htf" in current_scan_modes:
            last_run = htf_state["last_htf_run"]
            
            if last_run is not None and last_run >= nine_am_today:
                # Already ran HTF since 9am today, skip it
                current_scan_modes = [m for m in current_scan_modes if m.lower() != "htf"]
                logger.info(f"HTF skipped (market_open mode, ran at {last_run.strftime('%H:%M')})")
            else:
                # Haven't run HTF since 9am today - include it and mark as run
                htf_state["last_htf_run"] = now
                logger.info(f"HTF running (market_open mode, first run since 9am)")
        
        # Convert to ScanMode enums
        enabled_modes = modes_from_list(current_scan_modes)
        
        # Create service with settings
        settings = UnifiedScanSettings(
            modes=enabled_modes,
            min_quality_score=min_quality,
            stop_mode=stop_mode,
            max_stop_atr=max_stop_atr,
            max_stop_percent=max_stop_percent,
            ep_limit=limit,
            breakout_limit=limit,
            htf_limit=limit,
        )
        
        # Create scanner with optional market_data override for simulation
        if market_data is not None:
            # SIM MODE: Create scanners with MockMarketData
            from nexus2.domain.scanner.ep_scanner_service import EPScannerService, EPScanSettings
            from nexus2.domain.scanner.breakout_scanner_service import BreakoutScannerService
            from nexus2.domain.scanner.htf_scanner_service import HTFScannerService
            
            # Use relaxed settings for simulation (limited data may not show 8%+ gaps)
            sim_ep_settings = EPScanSettings(
                min_gap=3.0,    # Lower from 8% - sim data may not have big gaps
                min_rvol=0.5,   # Lower from 2.0 - volume calculation may vary
                min_price=5.0,  # Keep minimum price
            )
            
            ep_scanner = EPScannerService(settings=sim_ep_settings, market_data=market_data)
            breakout_scanner = BreakoutScannerService(market_data=market_data)
            htf_scanner = HTFScannerService(market_data=market_data)
            
            scanner = UnifiedScannerService(
                settings=settings,
                ep_scanner=ep_scanner,
                breakout_scanner=breakout_scanner,
                htf_scanner=htf_scanner,
            )
            logger.info(f"[SIM] Using MockMarketData for scan")
        else:
            # LIVE MODE: Use default singletons
            scanner = UnifiedScannerService(settings=settings)
        
        # Run scan (sync call wrapped for async)
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: scanner.scan(verbose=False)
        )
        
        logger.info(f"Unified scan: {result.total_signals} signals (EP:{result.ep_count}, BO:{result.breakout_count}, HTF:{result.htf_count})")
        
        # Return the full UnifiedScanResult
        # This has both .signals (list of Signal objects) and .diagnostics (list of ScanDiagnostics)
        # The scheduler stores this for the diagnostics API endpoint
        return result
    
    return unified_scanner_func


async def create_order_callback(app_state):
    """
    Create an order callback function for the automation engine.
    
    This wraps the trade API logic so the engine can submit orders.
    Uses bracket orders so stops are enforced by the broker.
    """
    async def order_func(
        symbol: str,
        shares: int,
        stop_price: float,
        setup_type: str,
    ) -> dict:
        """Submit a bracket order (entry + broker-side stop-loss)."""
        from nexus2.db import SessionLocal, PositionRepository
        from uuid import uuid4
        from datetime import datetime
        from decimal import Decimal
        
        # Get broker from app state
        broker = app_state.broker
        
        # Generate order ID
        client_order_id = uuid4()
        
        # Submit bracket order: market entry + attached stop-loss
        # The stop is held by the broker, not the app
        try:
            result = broker.submit_bracket_order(
                client_order_id=client_order_id,
                symbol=symbol,
                quantity=shares,
                stop_loss_price=Decimal(str(stop_price)),
            )
        except Exception as e:
            logger.error(f"Bracket order failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
        
        if result and result.status.value in ("accepted", "filled", "pending"):
            # Create position record
            db = SessionLocal()
            try:
                position_repo = PositionRepository(db)
                position = position_repo.create({
                    "id": str(uuid4()),
                    "symbol": symbol,
                    "setup_type": setup_type,
                    "status": "open",
                    "entry_price": str(result.avg_fill_price or result.limit_price or stop_price * 1.03),
                    "shares": shares,
                    "remaining_shares": shares,
                    "initial_stop": str(stop_price),
                    "current_stop": str(stop_price),
                    "realized_pnl": "0",
                    "opened_at": datetime.utcnow(),
                })
                
                logger.info(f"Bracket order placed: {symbol} x {shares} @ stop ${stop_price}")
                
                return {
                    "status": "success",
                    "order_id": str(result.broker_order_id),
                    "position_id": position.id,
                    "symbol": symbol,
                    "shares": shares,
                    "stop_price": stop_price,
                    "broker_stop": True,  # Indicates broker holds the stop
                }
            finally:
                db.close()
        
        return {
            "status": "failed",
            "error": "Order not accepted",
        }
    
    return order_func


def create_position_callback(app_state):
    """
    Create a position callback function for the automation engine.
    
    Returns list of open positions.
    """
    def position_func() -> List[dict]:
        """Get current open positions."""
        from nexus2.db import SessionLocal, PositionRepository
        
        db = SessionLocal()
        try:
            position_repo = PositionRepository(db)
            positions = position_repo.get_open()
            return [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "shares": p.remaining_shares,
                    "entry_price": p.entry_price,
                }
                for p in positions
            ]
        finally:
            db.close()
    
    return position_func


def initialize_engine(app_state, demo: bool = True) -> AutomationEngine:
    """
    Initialize the automation engine with all callbacks.
    
    Args:
        app_state: FastAPI app.state with broker, position_service, etc.
        demo: Whether to use demo mode for scanner
        
    Returns:
        Configured AutomationEngine
    """
    engine = AutomationEngine()
    
    # We'll set the scanner callback later (async)
    engine._position_func = create_position_callback(app_state)
    
    logger.info("Automation engine initialized with callbacks")
    
    return engine
