"""
Warrior Trading Routes

API endpoints for controlling the Warrior Trading automation engine.
Separate from KK-style automation routes.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal

from nexus2.domain.automation.warrior_engine import (
    WarriorEngine,
    WarriorEngineConfig,
    get_warrior_engine,
)
from nexus2.domain.scanner.warrior_scanner_service import (
    WarriorScannerService,
    WarriorScanSettings,
    get_warrior_scanner_service,
)


router = APIRouter(prefix="/warrior", tags=["warrior"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class WarriorStartRequest(BaseModel):
    """Request to start Warrior engine.
    
    All fields are Optional to preserve persisted settings.
    Only explicitly provided values will override current config.
    """
    sim_only: Optional[bool] = None
    risk_per_trade: Optional[float] = None
    max_positions: Optional[int] = None
    max_candidates: Optional[int] = None


class WarriorScannerSettingsRequest(BaseModel):
    """Request to update scanner settings."""
    max_float: Optional[int] = Field(None, description="Max float shares (default 100M)")
    min_rvol: Optional[float] = Field(None, description="Min relative volume (default 2.0)")
    min_gap: Optional[float] = Field(None, description="Min gap % (default 4.0)")
    min_price: Optional[float] = Field(None, description="Min price (default $1.50)")
    max_price: Optional[float] = Field(None, description="Max price (default $20)")
    require_catalyst: Optional[bool] = Field(None, description="Require news/earnings")


class WarriorMonitorSettingsRequest(BaseModel):
    """Request to update monitor settings."""
    mental_stop_cents: Optional[float] = Field(None, description="Mental stop in cents (default 15)")
    profit_target_r: Optional[float] = Field(None, description="Profit target R multiple (default 2.0)")
    profit_target_cents: Optional[float] = Field(None, description="Fixed cents target (0 = use R-based)")
    partial_exit_fraction: Optional[float] = Field(None, description="Partial exit % (default 0.5)")
    # Scaling settings (Ross Cameron methodology)
    enable_scaling: Optional[bool] = Field(None, description="Enable scaling into winners")
    max_scale_count: Optional[int] = Field(None, description="Max adds (1-5)")
    scale_size_pct: Optional[int] = Field(None, description="Add size as % of original")
    min_rvol_for_scale: Optional[float] = Field(None, description="Min RVOL for scaling")
    allow_scale_below_entry: Optional[bool] = Field(None, description="Allow scaling below entry")
    move_stop_to_breakeven_after_scale: Optional[bool] = Field(None, description="Move stop to breakeven after add")


class WarriorEngineConfigRequest(BaseModel):
    """Request to update engine configuration."""
    max_candidates: Optional[int] = Field(None, ge=1, le=20, description="Max candidates to watch (1-20)")
    scanner_interval_minutes: Optional[int] = Field(None, ge=1, le=60, description="Scan interval in minutes")
    risk_per_trade: Optional[float] = Field(None, gt=0, description="Risk per trade in dollars")
    max_positions: Optional[int] = Field(None, ge=1, le=20, description="Max simultaneous positions")
    max_daily_loss: Optional[float] = Field(None, gt=0, description="Max daily loss before stopping")
    orb_enabled: Optional[bool] = Field(None, description="Enable ORB breakouts")
    pmh_enabled: Optional[bool] = Field(None, description="Enable PMH breakouts")
    max_shares_per_trade: Optional[int] = Field(None, ge=1, description="Max shares per trade (for testing)")
    max_value_per_trade: Optional[float] = Field(None, gt=0, description="Max $ value per trade (for testing)")


class ScalingSettingsRequest(BaseModel):
    """Request to update scaling settings (Ross Cameron methodology)."""
    enable_scaling: Optional[bool] = Field(None, description="Enable scaling into winners")
    max_scale_count: Optional[int] = Field(None, ge=1, le=5, description="Max adds (1-5)")
    scale_size_pct: Optional[int] = Field(None, ge=10, le=200, description="Add size as % of original (10-200)")
    min_rvol_for_scale: Optional[float] = Field(None, ge=1.0, le=10.0, description="Min RVOL for scaling (1-10)")
    allow_scale_below_entry: Optional[bool] = Field(None, description="Allow scaling on pullback below entry")
    move_stop_to_breakeven_after_scale: Optional[bool] = Field(None, description="Move stop to breakeven after add")


class WarriorCandidateResponse(BaseModel):
    """A Warrior Trading candidate."""
    symbol: str
    name: str
    price: float
    gap_percent: float
    relative_volume: float
    float_shares: Optional[int]
    catalyst_type: str
    catalyst_description: str
    quality_score: int
    is_ideal_float: bool
    is_ideal_rvol: bool
    is_ideal_gap: bool
    # Quality indicators for traffic light display
    indicators: Optional[dict] = None  # {"float": {"status": "green", "tooltip": "Float: 8.2M"}, ...}


class WarriorScanResponse(BaseModel):
    """Response from Warrior scan."""
    candidates: List[WarriorCandidateResponse]
    processed_count: int
    filtered_count: int
    avg_rvol: float
    avg_gap: float


# =============================================================================
# ENGINE STATE (Singleton)
# =============================================================================

# Use the singleton from warrior_engine
def get_engine() -> WarriorEngine:
    return get_warrior_engine()


# =============================================================================
# ENGINE CONTROL ROUTES
# =============================================================================


# =============================================================================
# SCHWAB OAUTH ROUTES
# =============================================================================

@router.get("/schwab/auth-url")
async def get_schwab_auth_url():
    """
    Get Schwab OAuth authorization URL.
    
    Open this URL in a browser to log in to Schwab.
    After login, copy the 'code' from the callback URL and POST to /schwab/callback.
    """
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    
    if not schwab.client_id:
        raise HTTPException(400, "SCHWAB_CLIENT_ID not configured in .env")
    
    return {
        "auth_url": schwab.get_auth_url(),
        "instructions": "Open auth_url in browser, login, then POST the 'code' param to /warrior/schwab/callback",
    }


@router.post("/schwab/callback")
async def schwab_oauth_callback(code: str):
    """
    Exchange Schwab OAuth code for access tokens.
    
    After logging in via the auth_url, Schwab redirects to 127.0.0.1 with a code.
    Copy that code and POST here to complete authentication.
    """
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    
    success = schwab.exchange_code_for_tokens(code)
    
    if success:
        return {"status": "authenticated", "message": "Schwab tokens saved successfully"}
    else:
        raise HTTPException(400, "Failed to exchange code for tokens - check logs")


@router.get("/schwab/status")
async def get_schwab_status():
    """Check Schwab authentication status."""
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    
    return {
        "authenticated": schwab.is_authenticated(),
        "has_refresh_token": schwab._refresh_token is not None,
        "token_expiry": schwab._token_expiry.isoformat() if schwab._token_expiry else None,
    }


# =============================================================================
# ENGINE STATUS ROUTES
# =============================================================================

@router.get("/status")
async def get_warrior_status():
    """
    Get current Warrior engine status.
    
    Returns engine state, watchlist, and statistics.
    """
    engine = get_engine()
    status = engine.get_status()
    
    # Add auto_enable setting to status
    from nexus2.db.warrior_settings import get_auto_enable
    status["auto_enable"] = get_auto_enable()
    
    return status


class AutoEnableRequest(BaseModel):
    """Request to toggle auto-enable on startup."""
    enabled: bool = Field(..., description="True to auto-enable on startup, False to disable")


@router.patch("/auto-enable")
async def set_warrior_auto_enable(request: AutoEnableRequest):
    """
    Toggle Warrior auto-enable on server startup.
    
    When enabled, Warrior broker callbacks and position sync happen automatically
    when the server starts. Takes effect on next restart.
    """
    from nexus2.db.warrior_settings import set_auto_enable
    success = set_auto_enable(request.enabled)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save setting")
    
    return {
        "auto_enable": request.enabled,
        "message": f"Warrior auto-enable {'enabled' if request.enabled else 'disabled'}. Takes effect on next restart."
    }


@router.post("/start")
async def start_warrior_engine(request: WarriorStartRequest = WarriorStartRequest()):
    """
    Start the Warrior automation engine.
    
    Begins pre-market scanning and entry monitoring.
    """
    engine = get_engine()
    
    # Only update config for explicitly provided values (preserve loaded settings)
    if request.sim_only is not None:
        engine.config.sim_only = request.sim_only
    if request.risk_per_trade is not None:
        engine.config.risk_per_trade = Decimal(str(request.risk_per_trade))
    if request.max_positions is not None:
        engine.config.max_positions = request.max_positions
    if request.max_candidates is not None:
        engine.config.max_candidates = request.max_candidates
    
    # Wire up default callbacks if none are set
    # These use real market data for quotes but don't submit real orders (sim_only)
    if engine._get_quote is None:
        from nexus2.adapters.market_data.unified import UnifiedMarketData
        umd = UnifiedMarketData()
        
        async def default_get_quote(symbol: str):
            """Get quote from real market data (Alpaca for pre-market)."""
            quote = umd.get_quote(symbol)
            return float(quote.price) if quote else None
        
        engine.set_callbacks(
            get_quote=default_get_quote,
            # submit_order stays None in sim_only mode (no real orders)
        )
    
    result = await engine.start()
    return result


@router.post("/stop")
async def stop_warrior_engine():
    """
    Stop the Warrior automation engine.
    
    Stops all scanning and monitoring. Does NOT close positions.
    """
    engine = get_engine()
    result = await engine.stop()
    return result


@router.post("/pause")
async def pause_warrior_engine():
    """Pause the Warrior engine (continue monitoring, stop new entries)."""
    engine = get_engine()
    return await engine.pause()


@router.post("/resume")
async def resume_warrior_engine():
    """Resume the Warrior engine."""
    engine = get_engine()
    return await engine.resume()


@router.put("/config")
async def update_warrior_config(request: WarriorEngineConfigRequest):
    """
    Update Warrior engine configuration.
    
    Allows runtime updates to:
    - max_candidates: How many stocks to watch
    - scanner_interval_minutes: How often to scan
    - risk_per_trade: Risk per trade in dollars
    - max_positions: Max concurrent positions
    - max_daily_loss: Stop trading limit
    - orb_enabled/pmh_enabled: Entry triggers
    """
    engine = get_engine()
    updated = {}
    
    if request.max_candidates is not None:
        engine.config.max_candidates = request.max_candidates
        updated["max_candidates"] = request.max_candidates
    
    if request.scanner_interval_minutes is not None:
        old_interval = engine.config.scanner_interval_minutes
        engine.config.scanner_interval_minutes = request.scanner_interval_minutes
        updated["scanner_interval_minutes"] = request.scanner_interval_minutes
        # Interrupt sleep if new interval is shorter
        if request.scanner_interval_minutes < old_interval:
            engine.interrupt_scan_sleep()
    
    if request.risk_per_trade is not None:
        engine.config.risk_per_trade = Decimal(str(request.risk_per_trade))
        updated["risk_per_trade"] = request.risk_per_trade
    
    if request.max_positions is not None:
        engine.config.max_positions = request.max_positions
        updated["max_positions"] = request.max_positions
    
    if request.max_daily_loss is not None:
        engine.config.max_daily_loss = Decimal(str(request.max_daily_loss))
        updated["max_daily_loss"] = request.max_daily_loss
    
    if request.orb_enabled is not None:
        engine.config.orb_enabled = request.orb_enabled
        updated["orb_enabled"] = request.orb_enabled
    
    if request.pmh_enabled is not None:
        engine.config.pmh_enabled = request.pmh_enabled
        updated["pmh_enabled"] = request.pmh_enabled
    
    if request.max_shares_per_trade is not None:
        engine.config.max_shares_per_trade = request.max_shares_per_trade
        updated["max_shares_per_trade"] = request.max_shares_per_trade
    
    if request.max_value_per_trade is not None:
        engine.config.max_value_per_trade = Decimal(str(request.max_value_per_trade))
        updated["max_value_per_trade"] = request.max_value_per_trade
    
    # Save settings to persist across restarts
    try:
        from nexus2.db.warrior_settings import save_warrior_settings, get_config_dict
        save_warrior_settings(get_config_dict(engine.config))
    except Exception as e:
        print(f"[Warrior] Failed to save settings: {e}")
    
    return {
        "status": "updated",
        "updated_fields": updated,
        "current_config": {
            "max_candidates": engine.config.max_candidates,
            "scanner_interval_minutes": engine.config.scanner_interval_minutes,
            "risk_per_trade": float(engine.config.risk_per_trade),
            "max_positions": engine.config.max_positions,
            "max_daily_loss": float(engine.config.max_daily_loss),
            "orb_enabled": engine.config.orb_enabled,
            "pmh_enabled": engine.config.pmh_enabled,
            "max_shares_per_trade": engine.config.max_shares_per_trade,
            "max_value_per_trade": float(engine.config.max_value_per_trade) if engine.config.max_value_per_trade else None,
        }
    }


# =============================================================================
# SCANNER ROUTES
# =============================================================================

@router.post("/scanner/run", response_model=WarriorScanResponse)
async def run_warrior_scan():
    """
    Run a Warrior Trading scan.
    
    Scans for low-float momentum stocks matching Ross Cameron's 5 Pillars:
    1. Float < 100M (ideal < 20M)
    2. RVOL > 2x (ideal 3-5x)
    3. Catalyst (news/earnings/former runner)
    4. Price $1.50 - $20
    5. Gap > 4%
    """
    from nexus2.domain.automation.indicator_service import get_indicator_service
    
    scanner = get_warrior_scanner_service()
    result = scanner.scan(verbose=False)
    indicator_service = get_indicator_service()
    
    candidates = []
    for c in result.candidates:
        # Compute quality indicators for each candidate
        indicators = indicator_service.compute_watchlist_indicators(
            float_shares=c.float_shares,
            rvol=float(c.relative_volume),
            gap_percent=float(c.gap_percent),
            catalyst_type=c.catalyst_type,
            catalyst_desc=c.catalyst_description,
            current_price=float(c.price),
            vwap=None,  # TODO: Get VWAP from monitor if available
            entry_status="pending" if c.quality_score >= 80 else "not_ready",
            entry_price=float(c.pmh) if hasattr(c, 'pmh') and c.pmh else None,
        )
        
        candidates.append(WarriorCandidateResponse(
            symbol=c.symbol,
            name=c.name,
            price=float(c.price),
            gap_percent=float(c.gap_percent),
            relative_volume=float(c.relative_volume),
            float_shares=c.float_shares,
            catalyst_type=c.catalyst_type,
            catalyst_description=c.catalyst_description,
            quality_score=c.quality_score,
            is_ideal_float=c.is_ideal_float,
            is_ideal_rvol=c.is_ideal_rvol,
            is_ideal_gap=c.is_ideal_gap,
            indicators=indicators.to_dict(),
        ))
    
    return WarriorScanResponse(
        candidates=candidates,
        processed_count=result.processed_count,
        filtered_count=result.filtered_count,
        avg_rvol=float(result.avg_rvol),
        avg_gap=float(result.avg_gap),
    )


@router.get("/scanner/logs")
async def get_warrior_scanner_logs(limit: int = 20):
    """
    Get recent Warrior scanner log entries.
    
    Returns parsed scan history including PASS/FAIL symbols with rejection reasons.
    
    Args:
        limit: Number of scan entries to return (default 20, max 500)
    """
    from pathlib import Path
    import re
    
    # Clamp limit to 1-500 (covers ~4 days at 5-min intervals)
    limit = max(1, min(limit, 500))
    
    log_path = Path("data") / "warrior_scan.log"
    if not log_path.exists():
        return {"entries": [], "count": 0, "message": "No scan log file found"}
    
    # Read last N lines efficiently (read in reverse)
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        raise HTTPException(500, f"Failed to read scan log: {e}")
    
    # Parse log entries (most recent first)
    entries = []
    scans = []
    current_scan = None
    
    # Pattern matching for log lines
    pass_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| PASS \| (\w+) \| Gap:([0-9.]+)% \| RVOL:([0-9.]+)x \| Score:(\d+)")
    fail_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| FAIL \| (\w+) \| Reason: (\w+)")
    scan_start_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| SCAN START \| Total: (\d+) \| Pre-filtered: (\d+)")
    scan_end_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| SCAN END \| Processed: (\d+) \| Passed: (\d+)")
    
    # Process lines in reverse to get most recent first
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        
        # Check for SCAN END (marks start of a scan block when reading in reverse)
        match = scan_end_pattern.match(line)
        if match:
            current_scan = {
                "timestamp": match.group(1),
                "processed": int(match.group(2)),
                "passed": int(match.group(3)),
                "pass_entries": [],
                "fail_entries": [],
            }
            continue
        
        # Check for SCAN START (marks end of a scan block when reading in reverse)
        match = scan_start_pattern.match(line)
        if match and current_scan:
            current_scan["total_movers"] = int(match.group(2))
            current_scan["pre_filtered"] = int(match.group(3))
            scans.append(current_scan)
            current_scan = None
            if len(scans) >= limit:
                break
            continue
        
        # Check for PASS entry
        match = pass_pattern.match(line)
        if match and current_scan:
            current_scan["pass_entries"].append({
                "symbol": match.group(2),
                "gap_pct": float(match.group(3)),
                "rvol": float(match.group(4)),
                "score": int(match.group(5)),
            })
            continue
        
        # Check for FAIL entry
        match = fail_pattern.match(line)
        if match and current_scan:
            current_scan["fail_entries"].append({
                "symbol": match.group(2),
                "reason": match.group(3),
            })
            continue
    
    # If we have an incomplete scan at the end, include it
    if current_scan and len(scans) < limit:
        scans.append(current_scan)
    
    return {
        "scans": scans,
        "count": len(scans),
        "limit": limit,
    }


@router.get("/scanner/catalyst-audit")
async def get_catalyst_audit_entries(limit: int = 50):
    """
    Get recent catalyst audit entries for regex training.
    
    Returns headlines that were evaluated during catalyst classification,
    allowing review of false negatives where regex may be missing patterns.
    
    Args:
        limit: Number of symbol evaluations to return (default 50, max 200)
    """
    from pathlib import Path
    import re
    
    limit = max(1, min(limit, 200))
    
    # Read from dedicated catalyst_audit.log
    log_path = Path("data") / "catalyst_audit.log"
    if not log_path.exists():
        # Fallback for VPS
        log_path = Path.home() / "Nexus2" / "data" / "catalyst_audit.log"
    if not log_path.exists():
        return {"entries": [], "count": 0, "message": "No catalyst audit log found"}
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(500, f"Failed to read log: {e}")
    
    # Pattern for header: === SYMBOL | Result: PASS/FAIL | Type: xxx ===
    header_pattern = re.compile(
        r"=== (\w+) \| Result: (\w+) \| Type: (\w+|none) ==="
    )
    # Pattern for headline: [N] ✓/✗ type (conf=X.XX): headline text
    headline_pattern = re.compile(
        r"\[(\d+)\] ([✓✗]) (\w+) \(conf=([0-9.]+)\): (.+)$"
    )
    
    entries = []
    current_entry = None
    
    for line in reversed(lines):
        header_match = header_pattern.search(line)
        if header_match:
            if current_entry:
                entries.append(current_entry)
                if len(entries) >= limit:
                    break
            current_entry = {
                "symbol": header_match.group(1),
                "result": header_match.group(2),
                "catalyst_type": header_match.group(3) if header_match.group(3) != "none" else None,
                "headlines": [],
                "timestamp": line.split("|")[0].strip() if "|" in line else None,
            }
            continue
        
        headline_match = headline_pattern.search(line)
        if headline_match and current_entry:
            current_entry["headlines"].append({
                "index": int(headline_match.group(1)),
                "matched": headline_match.group(2) == "✓",
                "type": headline_match.group(3),
                "confidence": float(headline_match.group(4)),
                "text": headline_match.group(5).strip(),
            })
    
    # Add last entry
    if current_entry and len(entries) < limit:
        entries.append(current_entry)
    
    return {
        "entries": entries,
        "count": len(entries),
        "limit": limit,
        "description": "Headlines evaluated by catalyst classifier with match/no-match status",
    }


@router.get("/scanner/settings")
async def get_warrior_scanner_settings():
    """Get current Warrior scanner settings."""
    scanner = get_warrior_scanner_service()
    s = scanner.settings
    
    return {
        "max_float": s.max_float,
        "ideal_float": s.ideal_float,
        "min_rvol": float(s.min_rvol),
        "ideal_rvol": float(s.ideal_rvol),
        "min_gap": float(s.min_gap),
        "ideal_gap": float(s.ideal_gap),
        "min_price": float(s.min_price),
        "max_price": float(s.max_price),
        "require_catalyst": s.require_catalyst,
        "exclude_chinese_stocks": s.exclude_chinese_stocks,
        "min_dollar_volume": float(s.min_dollar_volume),
    }


@router.put("/scanner/settings")
async def update_warrior_scanner_settings(request: WarriorScannerSettingsRequest):
    """Update Warrior scanner settings."""
    scanner = get_warrior_scanner_service()
    
    if request.max_float is not None:
        scanner.settings.max_float = request.max_float
    if request.min_rvol is not None:
        scanner.settings.min_rvol = Decimal(str(request.min_rvol))
    if request.min_gap is not None:
        scanner.settings.min_gap = Decimal(str(request.min_gap))
    if request.min_price is not None:
        scanner.settings.min_price = Decimal(str(request.min_price))
    if request.max_price is not None:
        scanner.settings.max_price = Decimal(str(request.max_price))
    if request.require_catalyst is not None:
        scanner.settings.require_catalyst = request.require_catalyst
    
    return {"status": "updated", "settings": await get_warrior_scanner_settings()}


# =============================================================================
# MONITOR ROUTES
# =============================================================================

@router.get("/monitor/status")
async def get_warrior_monitor_status():
    """Get Warrior position monitor status."""
    engine = get_engine()
    return engine.monitor.get_status()


@router.get("/monitor/settings")
async def get_warrior_monitor_settings():
    """Get current Warrior monitor settings."""
    engine = get_engine()
    s = engine.monitor.settings
    
    return {
        "mental_stop_cents": float(s.mental_stop_cents),
        "use_technical_stop": s.use_technical_stop,
        "profit_target_r": s.profit_target_r,
        "partial_exit_fraction": s.partial_exit_fraction,
        "move_stop_to_breakeven": s.move_stop_to_breakeven,
        "enable_candle_under_candle": s.enable_candle_under_candle,
        "enable_topping_tail": s.enable_topping_tail,
        "topping_tail_threshold": s.topping_tail_threshold,
        "check_interval_seconds": s.check_interval_seconds,
        # Scaling settings (Ross Cameron methodology)
        "enable_scaling": s.enable_scaling,
        "max_scale_count": s.max_scale_count,
        "scale_size_pct": s.scale_size_pct,
        "min_rvol_for_scale": s.min_rvol_for_scale,
        "allow_scale_below_entry": s.allow_scale_below_entry,
        "move_stop_to_breakeven_after_scale": s.move_stop_to_breakeven_after_scale,
        # Exit mode (base_hit vs home_run)
        "session_exit_mode": s.session_exit_mode,
    }


@router.put("/monitor/settings")
async def update_warrior_monitor_settings(request: WarriorMonitorSettingsRequest):
    """Update Warrior monitor settings."""
    engine = get_engine()
    
    if request.mental_stop_cents is not None:
        engine.monitor.settings.mental_stop_cents = Decimal(str(request.mental_stop_cents))
    if request.profit_target_r is not None:
        engine.monitor.settings.profit_target_r = request.profit_target_r
    if request.partial_exit_fraction is not None:
        engine.monitor.settings.partial_exit_fraction = request.partial_exit_fraction
    
    # Scaling settings (Ross Cameron methodology)
    if hasattr(request, 'enable_scaling') and request.enable_scaling is not None:
        engine.monitor.settings.enable_scaling = request.enable_scaling
    if hasattr(request, 'max_scale_count') and request.max_scale_count is not None:
        engine.monitor.settings.max_scale_count = request.max_scale_count
    if hasattr(request, 'scale_size_pct') and request.scale_size_pct is not None:
        engine.monitor.settings.scale_size_pct = request.scale_size_pct
    if hasattr(request, 'min_rvol_for_scale') and request.min_rvol_for_scale is not None:
        engine.monitor.settings.min_rvol_for_scale = request.min_rvol_for_scale
    if hasattr(request, 'allow_scale_below_entry') and request.allow_scale_below_entry is not None:
        engine.monitor.settings.allow_scale_below_entry = request.allow_scale_below_entry
    if hasattr(request, 'move_stop_to_breakeven_after_scale') and request.move_stop_to_breakeven_after_scale is not None:
        engine.monitor.settings.move_stop_to_breakeven_after_scale = request.move_stop_to_breakeven_after_scale
    
    # Persist settings to disk
    try:
        from nexus2.db.warrior_monitor_settings import save_monitor_settings, get_monitor_settings_dict
        save_monitor_settings(get_monitor_settings_dict(engine.monitor.settings))
    except Exception as e:
        print(f"[Warrior] Failed to persist monitor settings: {e}")
    
    return {"status": "updated", "settings": await get_warrior_monitor_settings()}


# =============================================================================
# TRADE LOG
# =============================================================================

@router.get("/trades")
async def get_warrior_trades(limit: int = 50, status: str = None):
    """
    Get trade management log with summary statistics.
    
    Args:
        limit: Maximum trades to return (default 50)
        status: Optional filter - 'open', 'closed', or None for all
    
    Returns:
        trades: List of trades ordered by entry time (newest first)
        summary: Win rate, total P&L, trade counts
    """
    from nexus2.db.warrior_db import get_all_warrior_trades
    return get_all_warrior_trades(limit=limit, status_filter=status)


@router.get("/trades/analytics")
async def get_trade_analytics():
    """
    Get trade analytics breakdown by exit reason.
    
    Returns P&L and count grouped by exit_reason for understanding
    which exit types are profitable vs losing.
    """
    from nexus2.db.warrior_db import get_warrior_session, WarriorTradeModel
    from nexus2.domain.positions.position_state_machine import PositionStatus
    from sqlalchemy import func
    
    with get_warrior_session() as db:
        # Group by exit reason
        results = db.query(
            WarriorTradeModel.exit_reason,
            func.count().label('count'),
        ).filter(
            WarriorTradeModel.status == PositionStatus.CLOSED.value
        ).group_by(
            WarriorTradeModel.exit_reason
        ).all()
        
        # Calculate P&L per exit reason manually (SQLite cast is tricky)
        all_trades = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.status == PositionStatus.CLOSED.value
        ).all()
        
        pnl_by_reason = {}
        for t in all_trades:
            reason = t.exit_reason or "unknown"
            pnl = float(t.realized_pnl or 0)
            pnl_by_reason[reason] = pnl_by_reason.get(reason, 0) + pnl
        
        breakdown = [
            {
                "exit_reason": r.exit_reason or "unknown",
                "count": r.count,
                "total_pnl": round(pnl_by_reason.get(r.exit_reason or "unknown", 0), 2)
            }
            for r in results
        ]
        
        return {"breakdown": sorted(breakdown, key=lambda x: -x["count"])}


# =============================================================================
# INCLUDE SUB-ROUTERS
# =============================================================================

# Import and include sub-routers (extracted from this file)
from .warrior_sim_routes import sim_router
from .warrior_broker_routes import broker_router
from .warrior_positions import positions_router

router.include_router(sim_router)
router.include_router(broker_router)
router.include_router(positions_router)
