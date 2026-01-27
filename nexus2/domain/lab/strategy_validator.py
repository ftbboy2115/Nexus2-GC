"""
Strategy Validator

Validates generated strategies against configurable guardrails to prevent
dangerous or unrealistic configurations. The guardrails are user-editable
via the Lab UI.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field


class GuardrailConfig(BaseModel):
    """User-configurable guardrails for strategy generation."""
    
    # Risk limits
    max_risk_per_trade: float = Field(
        default=500.0,
        ge=50.0,
        le=5000.0,
        description="Maximum dollar risk per trade"
    )
    
    max_positions: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent positions"
    )
    
    max_daily_trades: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum trades per day"
    )
    
    # Safety requirements
    require_stop: bool = Field(
        default=True,
        description="Strategy must have a stop loss"
    )
    
    require_target: bool = Field(
        default=False,
        description="Strategy must have a profit target"
    )
    
    # Parameter bounds
    max_target_r: float = Field(
        default=10.0,
        ge=1.0,
        le=20.0,
        description="Maximum R-multiple for targets"
    )
    
    min_consolidation_bars: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Minimum consolidation bars for pattern entries"
    )
    
    max_stop_percent: float = Field(
        default=5.0,
        ge=0.5,
        le=15.0,
        description="Maximum stop distance as percentage"
    )
    
    # Price constraints
    min_price: float = Field(
        default=1.0,
        ge=0.5,
        le=50.0,
        description="Minimum stock price"
    )
    
    max_price: Optional[float] = Field(
        default=None,
        description="Maximum stock price (None = no limit)"
    )
    
    # Time constraints
    allow_overnight: bool = Field(
        default=True,
        description="Allow holding positions overnight"
    )
    
    trading_start_time: str = Field(
        default="09:30",
        description="Earliest entry time (HH:MM ET)"
    )
    
    trading_end_time: str = Field(
        default="15:50",
        description="Latest entry time (HH:MM ET)"
    )


class ValidationError(BaseModel):
    """A single validation error."""
    field: str
    message: str
    severity: str = "error"  # "error" or "warning"


def validate_strategy(
    strategy_spec: Any,
    config: GuardrailConfig
) -> List[ValidationError]:
    """
    Validate a generated strategy against guardrails.
    
    Args:
        strategy_spec: The generated strategy specification (dict or StrategySpec)
        config: The guardrails configuration
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors: List[ValidationError] = []
    
    # Handle both dict and object
    if isinstance(strategy_spec, dict):
        spec = strategy_spec
        engine = spec.get("engine", {})
        monitor = spec.get("monitor", {})
        scanner = spec.get("scanner", {})
    else:
        spec = strategy_spec
        engine = getattr(spec, "engine", {})
        monitor = getattr(spec, "monitor", {})
        scanner = getattr(spec, "scanner", {})
        
        # Convert to dict if needed
        if hasattr(engine, "dict"):
            engine = engine.dict() if hasattr(engine, "dict") else vars(engine)
        if hasattr(monitor, "dict"):
            monitor = monitor.dict() if hasattr(monitor, "dict") else vars(monitor)
        if hasattr(scanner, "dict"):
            scanner = scanner.dict() if hasattr(scanner, "dict") else vars(scanner)
    
    # ----- RISK VALIDATION -----
    risk_per_trade = engine.get("risk_per_trade", 0)
    if risk_per_trade > config.max_risk_per_trade:
        errors.append(ValidationError(
            field="engine.risk_per_trade",
            message=f"Risk ${risk_per_trade:.0f} exceeds max ${config.max_risk_per_trade:.0f}",
            severity="error"
        ))
    
    max_positions = engine.get("max_positions", 0)
    if max_positions > config.max_positions:
        errors.append(ValidationError(
            field="engine.max_positions",
            message=f"Max positions {max_positions} exceeds limit {config.max_positions}",
            severity="error"
        ))
    
    # ----- STOP VALIDATION -----
    stop_mode = monitor.get("stop_mode")
    if config.require_stop and not stop_mode:
        errors.append(ValidationError(
            field="monitor.stop_mode",
            message="Strategy must have a stop loss defined",
            severity="error"
        ))
    
    stop_percent = monitor.get("stop_percent", 0)
    if stop_percent > config.max_stop_percent:
        errors.append(ValidationError(
            field="monitor.stop_percent",
            message=f"Stop {stop_percent:.1f}% exceeds max {config.max_stop_percent:.1f}%",
            severity="error"
        ))
    
    # ----- TARGET VALIDATION -----
    target_r = monitor.get("target_r")
    if config.require_target and not target_r:
        errors.append(ValidationError(
            field="monitor.target_r",
            message="Strategy must have a profit target defined",
            severity="error"
        ))
    
    if target_r and target_r > config.max_target_r:
        errors.append(ValidationError(
            field="monitor.target_r",
            message=f"Target R={target_r:.1f} exceeds max {config.max_target_r:.1f}",
            severity="warning"
        ))
    
    # ----- PRICE VALIDATION -----
    min_price = scanner.get("min_price", 0)
    if min_price < config.min_price:
        errors.append(ValidationError(
            field="scanner.min_price",
            message=f"Min price ${min_price:.2f} below guardrail ${config.min_price:.2f}",
            severity="warning"
        ))
    
    max_price = scanner.get("max_price")
    if config.max_price and max_price and max_price > config.max_price:
        errors.append(ValidationError(
            field="scanner.max_price",
            message=f"Max price ${max_price:.2f} exceeds guardrail ${config.max_price:.2f}",
            severity="warning"
        ))
    
    # ----- TIME VALIDATION -----
    hold_overnight = monitor.get("hold_overnight", False)
    if hold_overnight and not config.allow_overnight:
        errors.append(ValidationError(
            field="monitor.hold_overnight",
            message="Overnight holding disabled by guardrails",
            severity="error"
        ))
    
    return errors


def is_valid(errors: List[ValidationError]) -> bool:
    """Check if validation passed (no errors, warnings OK)."""
    return not any(e.severity == "error" for e in errors)


def format_errors(errors: List[ValidationError]) -> str:
    """Format validation errors for display."""
    if not errors:
        return "✓ Strategy passed all guardrails"
    
    lines = []
    for e in errors:
        icon = "❌" if e.severity == "error" else "⚠️"
        lines.append(f"{icon} {e.field}: {e.message}")
    return "\n".join(lines)


# Default guardrails instance
DEFAULT_GUARDRAILS = GuardrailConfig()
