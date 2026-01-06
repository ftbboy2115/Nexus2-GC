"""
Automation Request/Response Models

Pydantic models for automation API endpoints.
Extracted from automation.py for cleaner separation of concerns.
"""

from pydantic import BaseModel
from typing import Optional, List


# ==================== ENGINE MODELS ====================

class StartRequest(BaseModel):
    """Request for starting the automation engine."""
    sim_only: bool = True  # Default to SIM mode
    scanner_interval: int = 15  # minutes
    min_quality: int = 7
    max_positions: int = 5
    risk_per_trade: Optional[float] = None  # If None, reads from main settings
    daily_loss_limit: float = 1000.0
    max_capital: float = 10000.0  # Maximum capital for automation


class EngineStatusResponse(BaseModel):
    """Response for engine status endpoint."""
    state: str
    sim_only: bool
    is_market_hours: bool
    config: dict
    stats: dict


class ActionResponse(BaseModel):
    """Generic action response."""
    status: str
    message: Optional[str] = None


# ==================== SCANNER MODELS ====================

class ScanAllRequest(BaseModel):
    """Request for unified scan across all scanners."""
    modes: list[str] = ["all"]  # "all", "ep", "breakout", "htf"
    min_quality: int = 7
    stop_mode: str = "atr"  # "atr" (KK-style) or "percent"
    max_stop_atr: float = 1.0  # KK uses 1.0-1.5 ATR
    max_stop_percent: float = 5.0  # Fallback for percent mode
    include_extended_htf: bool = False  # Include extended HTF candidates (for testing)


class ExecuteRequest(BaseModel):
    """Request for executing a trade signal."""
    symbol: str
    shares: int
    stop_price: float
    setup_type: str = "ep"
    dry_run: bool = True  # Default to dry run for safety


# ==================== SCHEDULER MODELS ====================

class SchedulerStartRequest(BaseModel):
    """Request for starting the scheduler."""
    interval_minutes: int = 15
    auto_execute: bool = False  # Default to scan-only


class SchedulerToggleRequest(BaseModel):
    """Request for toggling auto-execute."""
    auto_execute: bool


class SchedulerIntervalRequest(BaseModel):
    """Request for updating scheduler interval."""
    interval_minutes: int


class SchedulerSettingsRequest(BaseModel):
    """Request model for updating scheduler settings."""
    adopt_quick_actions: Optional[bool] = None
    preset: Optional[str] = None  # strict, relaxed, custom
    min_quality: Optional[int] = None
    stop_mode: Optional[str] = None  # atr or percent
    max_stop_atr: Optional[float] = None
    max_stop_percent: Optional[float] = None
    scan_modes: Optional[List[str]] = None  # ["ep", "breakout", "htf"]
    htf_frequency: Optional[str] = None  # every_cycle or market_open
    max_position_value: Optional[float] = None  # Automation-specific capital limit per position
    nac_max_positions: Optional[int] = None  # NAC-specific max concurrent positions (None = unlimited)
    auto_start_enabled: Optional[bool] = None  # Enable auto-start for headless operation
    auto_start_time: Optional[str] = None  # HH:MM format (ET timezone)
    auto_execute: Optional[bool] = None  # Enable auto-execute for autonomous trading
    nac_broker_type: Optional[str] = None  # alpaca_paper, alpaca_live
    nac_account: Optional[str] = None  # A or B (default A for Automation)
    sim_mode: Optional[bool] = None  # Enable simulation mode (uses MockBroker)
    min_price: Optional[float] = None  # Minimum stock price filter ($2-10, default $5)
    discord_alerts_enabled: Optional[bool] = None  # Enable Discord notifications


# Preset definitions for scheduler (same as Quick Actions)
SCHEDULER_PRESETS = {
    "strict": {
        "min_quality": 7,
        "stop_mode": "atr",
        "max_stop_atr": 1.0,
        "max_stop_percent": 5.0,
    },
    "relaxed": {
        "min_quality": 5,
        "stop_mode": "percent",
        "max_stop_atr": 1.5,
        "max_stop_percent": 8.0,
    },
}


# ==================== MONITOR MODELS ====================

class MonitorStartRequest(BaseModel):
    """Request for starting position monitor."""
    check_interval_seconds: int = 60
    enable_trailing_stops: bool = True
    enable_partial_exits: bool = True


# ==================== MA CHECK MODELS ====================

class MACheckRequest(BaseModel):
    """Request for MA check job."""
    dry_run: bool = True  # Default to dry run for safety
    min_days: int = 5  # Start MA trailing after day 5
    ma_type: str = "auto"  # auto (default), ema_10, ema_20, sma_10, sma_20, lower_10, lower_20
    require_timing_window: bool = False  # If True, only run 3:45-4:00 PM ET
