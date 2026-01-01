"""
Position Sizing Service

Core position sizing logic (KK style).
Based on: risk_engine_architecture.md
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import List

from nexus2.domain.risk.models import (
    RiskContext,
    PositionSize,
    OpenHeat,
    SizingMode,
)
from nexus2.settings.risk_settings import RiskSettings, PerformanceSettings


class PositionSizingService:
    """
    Core position sizing logic (KK style).
    
    Responsibilities:
    - Calculate shares from fixed-dollar risk and stop distance
    - Validate position against constraints
    - Adjust sizing based on performance (RRR)
    """
    
    def __init__(
        self,
        risk_settings: RiskSettings,
        performance_settings: PerformanceSettings,
    ):
        self.risk_settings = risk_settings
        self.performance_settings = performance_settings
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_price: Decimal,
        risk_context: RiskContext,
        atr: Decimal,
    ) -> PositionSize:
        """
        Calculate shares based on fixed-dollar risk.
        
        Formula: shares = risk_dollars / (entry - stop)
        
        Args:
            symbol: Stock symbol
            entry_price: Planned entry price
            stop_price: Tactical stop price (LOD or flag low)
            risk_context: Current account/risk state
            atr: Average True Range for validation
            
        Returns:
            PositionSize with shares and validation status
        """
        # Calculate stop distance
        stop_distance = entry_price - stop_price
        if stop_distance <= 0:
            return PositionSize(
                symbol=symbol,
                entry_price=entry_price,
                stop_price=stop_price,
                stop_distance=Decimal("0"),
                stop_distance_pct=Decimal("0"),
                risk_dollars=Decimal("0"),
                shares=0,
                position_value=Decimal("0"),
                position_pct=Decimal("0"),
                is_valid=False,
                validation_errors=["Stop price must be below entry price"],
            )
        
        stop_distance_pct = (stop_distance / entry_price) * 100
        
        # Adjust risk for performance
        adjusted_risk = self.adjust_for_performance(
            risk_context.risk_per_trade_dollars,
            risk_context.rrr_last_20,
        )
        
        # Calculate shares
        shares = int((adjusted_risk / stop_distance).to_integral_value(rounding=ROUND_DOWN))
        
        # Calculate position value and percentage
        position_value = Decimal(shares) * entry_price
        position_pct = (position_value / risk_context.account_value) * 100
        
        # Validate
        errors = self.validate_position(
            entry_price=entry_price,
            stop_price=stop_price,
            stop_distance=stop_distance,
            position_pct=position_pct,
            risk_context=risk_context,
            atr=atr,
        )
        
        return PositionSize(
            symbol=symbol,
            entry_price=entry_price,
            stop_price=stop_price,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            risk_dollars=adjusted_risk,
            shares=shares,
            position_value=position_value,
            position_pct=position_pct,
            is_valid=len(errors) == 0,
            validation_errors=errors,
        )
    
    def validate_position(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        stop_distance: Decimal,
        position_pct: Decimal,
        risk_context: RiskContext,
        atr: Decimal,
    ) -> List[str]:
        """
        Validate position against constraints.
        
        Checks:
        - Stop ≤ 1x ATR
        - Position ≤ max position %
        - Heat + new position ≤ max heat
        """
        errors = []
        rs = self.risk_settings
        
        # ATR constraint
        stop_atr_ratio = stop_distance / atr if atr > 0 else Decimal("999")
        if stop_atr_ratio > rs.max_atr_ratio:
            errors.append(
                f"Stop distance {stop_distance:.2f} ({stop_atr_ratio:.2f}x ATR) "
                f"exceeds max {rs.max_atr_ratio}x ATR"
            )
        
        # Position size constraint
        if position_pct > rs.max_position_pct:
            errors.append(
                f"Position {position_pct:.1f}% exceeds max {rs.max_position_pct}%"
            )
        
        # Open heat constraint
        new_heat = risk_context.current_open_heat + (
            (risk_context.risk_per_trade_dollars / risk_context.account_value) * 100
        )
        if new_heat > rs.max_heat_pct:
            errors.append(
                f"New heat {new_heat:.1f}% would exceed max {rs.max_heat_pct}%"
            )
        
        return errors
    
    def adjust_for_performance(
        self,
        base_risk: Decimal,
        rrr: Decimal,
    ) -> Decimal:
        """
        Adjust risk based on RRR (KK style).
        
        - RRR > 2: full risk
        - RRR 1-2: standard (no adjustment)
        - RRR < 1: reduced (50-75%)
        """
        ps = self.performance_settings
        
        if rrr >= ps.full_sizing_rrr:
            return base_risk
        elif rrr >= ps.reduced_sizing_rrr:
            return base_risk
        else:
            return base_risk * ps.reduced_multiplier
    
    def get_sizing_mode(self, rrr: Decimal) -> SizingMode:
        """Get sizing mode from RRR."""
        ps = self.performance_settings
        
        if rrr >= ps.full_sizing_rrr:
            return SizingMode.FULL
        elif rrr >= ps.reduced_sizing_rrr:
            return SizingMode.STANDARD
        return SizingMode.REDUCED
    
    def get_sizing_multiplier(self, mode: SizingMode) -> Decimal:
        """Get multiplier for sizing mode."""
        multipliers = {
            SizingMode.FULL: Decimal("1.0"),
            SizingMode.STANDARD: Decimal("1.0"),
            SizingMode.REDUCED: self.performance_settings.reduced_multiplier,
        }
        return multipliers[mode]
