"""
Settings Routes

User-configurable settings.
"""

import os
import json
from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from nexus2 import config as app_config
from nexus2.api.broker_factory import create_broker_by_type
from nexus2.adapters.broker import OrderExecutor


router = APIRouter(prefix="/settings", tags=["settings"])

# Settings file path (in nexus2 directory)
SETTINGS_FILE = Path(__file__).parent.parent.parent / "settings.json"


class TradeSettings(BaseModel):
    """Trade settings."""
    partial_exit_fraction: float
    partial_exit_days: int
    partial_exit_gain_pct: float
    risk_per_trade: float
    max_per_symbol: float = 2000.0  # Max capital allocation per ticker
    max_positions: int = 5  # Max concurrent positions
    dual_stop_enabled: bool = False  # NOT KK-style: enable invalidation level alerts
    trading_mode: str  # SIMULATION, PAPER, LIVE
    broker_type: str  # paper, alpaca_paper, alpaca_live
    active_account: str = "A"  # A or B
    # MA Trailing Settings (KK-style)
    trailing_ma_type: str = "auto"  # auto, ema_10, ema_20, sma_10, sma_20, lower_10, lower_20
    adr_threshold: float = 5.0  # ADR% threshold for fast vs slow (auto mode)
    min_days_for_trailing: int = 5  # Days before MA trailing applies
    # Automation Settings
    max_trades_per_cycle: int = 10  # Max trades to execute per scan cycle
    sim_initial_cash: float = 100_000.0  # Initial cash for simulation mode


class BrokerStatus(BaseModel):
    """Current broker status."""
    broker_type: str
    connected: bool
    account_value: Optional[str] = None
    alpaca_configured: bool
    error: Optional[str] = None


# In-memory settings (cached from file)
_runtime_settings: TradeSettings | None = None


def get_default_settings() -> TradeSettings:
    """Get default settings."""
    return TradeSettings(
        partial_exit_fraction=0.5,
        partial_exit_days=3,
        partial_exit_gain_pct=10.0,
        risk_per_trade=250.0,
        max_per_symbol=2000.0,
        max_positions=5,
        dual_stop_enabled=False,  # NOT KK-style - off by default
        trading_mode="SIMULATION",
        broker_type="paper",
        active_account="A",
        # MA Trailing defaults (KK-style)
        trailing_ma_type="auto",
        adr_threshold=5.0,
        min_days_for_trailing=5,
        # Automation defaults
        max_trades_per_cycle=10,
        sim_initial_cash=100_000.0,
    )


def _load_settings_from_file() -> TradeSettings | None:
    """Load settings from JSON file if it exists."""
    if not SETTINGS_FILE.exists():
        return None
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        return TradeSettings(**data)
    except Exception as e:
        print(f"[Settings] Warning: Failed to load settings file: {e}")
        return None


def _save_settings_to_file(settings: TradeSettings) -> None:
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings.model_dump(), f, indent=2)
        print(f"[Settings] Saved to {SETTINGS_FILE}")
    except Exception as e:
        print(f"[Settings] Warning: Failed to save settings file: {e}")


def get_settings() -> TradeSettings:
    """Get current settings (from file or defaults)."""
    global _runtime_settings
    if _runtime_settings is None:
        # Try loading from file first
        _runtime_settings = _load_settings_from_file()
        if _runtime_settings is None:
            _runtime_settings = get_default_settings()
            # Save defaults to file
            _save_settings_to_file(_runtime_settings)
    return _runtime_settings


@router.get("", response_model=TradeSettings)
async def read_settings():
    """Get current trade settings."""
    return get_settings()


class UpdateSettings(BaseModel):
    """Partial settings update."""
    partial_exit_fraction: float | None = None
    partial_exit_days: int | None = None
    partial_exit_gain_pct: float | None = None
    risk_per_trade: float | None = None
    max_per_symbol: float | None = None
    max_positions: int | None = None
    broker_type: str | None = None  # paper, alpaca_paper, alpaca_live
    active_account: str | None = None  # A or B
    # MA Trailing Settings
    trailing_ma_type: str | None = None  # auto, ema_10, lower_10, etc.
    adr_threshold: float | None = None  # ADR% threshold (5.0 = KK default)
    min_days_for_trailing: int | None = None  # Days before trailing
    # Automation Settings
    max_trades_per_cycle: int | None = None  # Max trades per scan cycle
    sim_initial_cash: float | None = None  # Initial cash for sim mode


@router.put("", response_model=TradeSettings)
async def update_settings(request: Request, updates: UpdateSettings):
    """Update trade settings (persisted to file)."""
    global _runtime_settings
    current = get_settings()
    old_broker_type = current.broker_type
    old_account = current.active_account
    
    if updates.partial_exit_fraction is not None:
        current.partial_exit_fraction = updates.partial_exit_fraction
    if updates.partial_exit_days is not None:
        current.partial_exit_days = updates.partial_exit_days
    if updates.partial_exit_gain_pct is not None:
        current.partial_exit_gain_pct = updates.partial_exit_gain_pct
    if updates.risk_per_trade is not None:
        current.risk_per_trade = updates.risk_per_trade
    if updates.max_per_symbol is not None:
        current.max_per_symbol = updates.max_per_symbol
    if updates.max_positions is not None:
        current.max_positions = updates.max_positions
    if updates.broker_type is not None:
        valid_brokers = ["paper", "alpaca_paper"]
        if updates.broker_type in valid_brokers:
            current.broker_type = updates.broker_type
            # Update trading mode based on broker
            if updates.broker_type == "alpaca_paper":
                current.trading_mode = "PAPER"
            else:
                current.trading_mode = "SIMULATION"
    if updates.active_account is not None:
        if updates.active_account.upper() in ["A", "B"]:
            current.active_account = updates.active_account.upper()
    # MA Trailing Settings
    if updates.trailing_ma_type is not None:
        valid_ma_types = ["auto", "ema_10", "ema_20", "sma_10", "sma_20", "lower_10", "lower_20"]
        if updates.trailing_ma_type in valid_ma_types:
            current.trailing_ma_type = updates.trailing_ma_type
    if updates.adr_threshold is not None:
        if 0 < updates.adr_threshold <= 20:  # Reasonable range
            current.adr_threshold = updates.adr_threshold
    if updates.min_days_for_trailing is not None:
        if 1 <= updates.min_days_for_trailing <= 30:
            current.min_days_for_trailing = updates.min_days_for_trailing
    # Automation Settings
    if updates.max_trades_per_cycle is not None:
        if 1 <= updates.max_trades_per_cycle <= 50:  # Reasonable range
            current.max_trades_per_cycle = updates.max_trades_per_cycle
    if updates.sim_initial_cash is not None:
        if 1_000 <= updates.sim_initial_cash <= 10_000_000:  # $1k - $10M
            current.sim_initial_cash = updates.sim_initial_cash
    
    _runtime_settings = current
    
    # Persist settings to file
    _save_settings_to_file(current)
    
    # Recreate broker if broker_type or account changed
    if current.broker_type != old_broker_type or current.active_account != old_account:
        print(f"[Settings] Switching broker: {old_broker_type}/{old_account} -> {current.broker_type}/{current.active_account}")
        request.app.state.broker = create_broker_by_type(
            current.broker_type,
            current.active_account,
        )
        request.app.state.executor = OrderExecutor(
            order_service=request.app.state.order_service,
            broker=request.app.state.broker,
        )
    
    return current


def get_account_credentials(account: str = "A") -> tuple[str | None, str | None]:
    """
    Get Alpaca credentials for the specified account.
    
    Args:
        account: "A" or "B"
        
    Returns:
        Tuple of (api_key, api_secret)
    """
    if account.upper() == "B":
        return (app_config.ALPACA_KEY_B, app_config.ALPACA_SECRET_B)
    return (app_config.ALPACA_KEY, app_config.ALPACA_SECRET)


@router.get("/broker-status", response_model=BrokerStatus)
async def get_broker_status():
    """Get current broker connection status."""
    settings = get_settings()
    
    # Get credentials for the active account
    api_key, api_secret = get_account_credentials(settings.active_account)
    alpaca_configured = bool(api_key and api_secret)
    
    if settings.broker_type == "paper":
        return BrokerStatus(
            broker_type="paper",
            connected=True,
            alpaca_configured=alpaca_configured,
        )
    
    # Try to connect to Alpaca
    if not alpaca_configured:
        return BrokerStatus(
            broker_type=settings.broker_type,
            connected=False,
            alpaca_configured=False,
            error=f"Alpaca API keys not configured for Account {settings.active_account}",
        )
    
    try:
        from nexus2.adapters.broker import AlpacaBroker, AlpacaBrokerConfig
        
        config = AlpacaBrokerConfig(
            api_key=api_key,
            api_secret=api_secret,
            paper=(settings.broker_type == "alpaca_paper"),
        )
        broker = AlpacaBroker(config)
        account_value = broker.get_account_value()
        
        return BrokerStatus(
            broker_type=settings.broker_type,
            connected=True,
            account_value=str(account_value),
            alpaca_configured=True,
        )
    except Exception as e:
        return BrokerStatus(
            broker_type=settings.broker_type,
            connected=False,
            alpaca_configured=True,
            error=str(e),
        )

