"""
Strategy Schema - Pydantic models for R&D Lab strategies.

Defines the structure for experiment strategies following the 3-tier architecture:
- Scanner: Signal discovery
- Engine: Entry detection  
- Monitor: Position management
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from nexus2.utils.time_utils import now_utc_factory


class StrategyStatus(str, Enum):
    """Status of a strategy in the lab."""
    DRAFT = "draft"           # Being developed
    TESTING = "testing"       # Running in backtest
    PAPER = "paper"           # Running in paper trading
    PRODUCTION = "production" # Promoted to live (locked)
    ARCHIVED = "archived"     # No longer active


class ScannerConfig(BaseModel):
    """Configuration for signal discovery (scanner)."""
    
    # Price filters
    min_price: Decimal = Field(default=Decimal("2.00"), description="Minimum stock price")
    max_price: Optional[Decimal] = Field(default=Decimal("20.00"), description="Maximum stock price")
    
    # Volume filters
    min_volume: int = Field(default=500_000, description="Minimum average daily volume")
    min_rvol: float = Field(default=2.0, description="Minimum relative volume")
    
    # Gap filters
    min_gap_percent: float = Field(default=5.0, description="Minimum gap percentage")
    max_gap_percent: Optional[float] = Field(default=None, description="Maximum gap percentage")
    
    # Float filters
    min_float: Optional[int] = Field(default=None, description="Minimum shares float")
    max_float: Optional[int] = Field(default=50_000_000, description="Maximum shares float")
    
    # Catalyst requirements
    require_catalyst: bool = Field(default=True, description="Require news catalyst")
    catalyst_boost: bool = Field(default=True, description="Apply catalyst score boost")
    
    # Custom filters (extensible)
    custom_filters: Dict[str, Any] = Field(default_factory=dict)


class EngineConfig(BaseModel):
    """Configuration for entry detection (engine)."""
    
    # Entry triggers
    entry_triggers: List[str] = Field(
        default=["ORB", "PMH_BREAK"],
        description="Entry trigger types"
    )
    
    # Trading window
    trading_start: str = Field(default="09:30", description="Trading window start (ET)")
    trading_end: str = Field(default="11:30", description="Trading window end (ET)")
    
    # Position limits
    max_positions: int = Field(default=3, description="Maximum concurrent positions")
    max_daily_trades: int = Field(default=6, description="Maximum trades per day")
    
    # Risk per trade
    risk_per_trade: Decimal = Field(default=Decimal("100.00"), description="Fixed dollar risk")
    max_position_size: Decimal = Field(default=Decimal("5000.00"), description="Max position value")
    
    # Entry timing
    min_consolidation_bars: int = Field(default=3, description="Min bars before entry")
    confirmation_threshold: float = Field(default=0.02, description="Price above trigger %")
    
    # Custom settings
    custom_settings: Dict[str, Any] = Field(default_factory=dict)


class MonitorConfig(BaseModel):
    """Configuration for position management (monitor)."""
    
    # Stop loss
    stop_mode: str = Field(default="mental", description="Stop type: mental, technical, hard")
    stop_cents: Optional[int] = Field(default=15, description="Mental stop in cents (optional)")
    stop_atr_multiplier: Optional[float] = Field(default=None, description="ATR-based stop")
    
    # Profit targets
    target_r: float = Field(default=2.0, description="Target in R multiples")
    partial_at_target: float = Field(default=0.5, description="Portion to sell at target")
    
    # Trailing stop
    trailing_stop_enabled: bool = Field(default=True, description="Enable trailing stop")
    trailing_stop_activation_r: float = Field(default=1.5, description="R to activate trail")
    
    # Scaling
    scaling_enabled: bool = Field(default=True, description="Enable scale-in")
    max_scales: int = Field(default=2, description="Maximum scale-ins")
    scale_confirmation: str = Field(default="above_vwap", description="Scale confirmation")
    
    # Time-based exits
    eod_exit: bool = Field(default=True, description="Exit at end of day")
    max_hold_minutes: Optional[int] = Field(default=None, description="Max hold time")
    
    # Custom settings
    custom_settings: Dict[str, Any] = Field(default_factory=dict)


class StrategySpec(BaseModel):
    """Complete strategy specification for the R&D Lab.
    
    Follows 3-tier architecture:
    - Scanner: Signal discovery
    - Engine: Entry detection
    - Monitor: Position management
    """
    
    # Identity
    name: str = Field(..., description="Strategy name (e.g., 'lab_warrior')")
    version: str = Field(..., description="Semantic version (e.g., '1.0.0')")
    description: str = Field(default="", description="Strategy description")
    
    # Metadata
    author: str = Field(default="Nexus Lab", description="Strategy author")
    created_at: datetime = Field(default_factory=now_utc_factory)
    updated_at: datetime = Field(default_factory=now_utc_factory)
    status: StrategyStatus = Field(default=StrategyStatus.DRAFT)
    
    # Based on (for experiments derived from existing strategies)
    based_on: Optional[str] = Field(default=None, description="Parent strategy name")
    based_on_version: Optional[str] = Field(default=None, description="Parent version")
    
    # Components
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    
    # Performance (populated after testing)
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Performance metrics")
    
    # Notes
    hypothesis: Optional[str] = Field(default=None, description="Research hypothesis")
    changelog: List[str] = Field(default_factory=list, description="Version changelog")

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
        }
