"""
Open Heat Service

Portfolio risk tracking and dashboard display.
Based on: risk_engine_architecture.md
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Protocol

from nexus2.domain.risk.models import (
    OpenHeat,
    PositionRisk,
    HeatStatus,
    HeatIndicator,
    PositionSize,
)
from nexus2.settings.risk_settings import RiskSettings


class Position(Protocol):
    """Protocol for position data."""
    symbol: str
    shares: int
    entry_price: Decimal
    current_stop: Decimal


class OpenHeatService:
    """
    Portfolio risk tracking and dashboard display.
    
    Responsibilities:
    - Calculate total portfolio risk (open heat)
    - Track risk per position
    - Provide dashboard indicator
    - Check if new positions can be added
    """
    
    def __init__(self, risk_settings: RiskSettings):
        self.risk_settings = risk_settings
    
    def calculate_open_heat(
        self,
        positions: List[Position],
        account_value: Decimal,
    ) -> OpenHeat:
        """
        Calculate total portfolio risk.
        
        Open Heat = Sum of (shares × (entry - stop)) for all positions
        
        Args:
            positions: List of open positions
            account_value: Total account value
            
        Returns:
            OpenHeat with total risk and per-position breakdown
        """
        position_risks = []
        total_heat_dollars = Decimal("0")
        
        for pos in positions:
            risk_per_share = pos.entry_price - pos.current_stop
            risk_dollars = Decimal(pos.shares) * risk_per_share
            risk_pct = (risk_dollars / account_value) * 100 if account_value > 0 else Decimal("0")
            
            position_risks.append(PositionRisk(
                symbol=pos.symbol,
                shares=pos.shares,
                entry_price=pos.entry_price,
                current_stop=pos.current_stop,
                risk_dollars=risk_dollars,
                risk_pct=risk_pct,
            ))
            
            total_heat_dollars += risk_dollars
        
        total_heat_pct = (total_heat_dollars / account_value) * 100 if account_value > 0 else Decimal("0")
        status = OpenHeat.calculate_status(total_heat_pct)
        
        return OpenHeat(
            total_heat_dollars=total_heat_dollars,
            total_heat_pct=total_heat_pct,
            positions=position_risks,
            status=status,
            updated_at=datetime.now(),
        )
    
    def get_heat_status(self, heat_pct: Decimal) -> HeatStatus:
        """
        Return status based on heat percentage.
        
        - <5%: GREEN
        - 5-8%: YELLOW
        - >8%: RED
        """
        return OpenHeat.calculate_status(heat_pct)
    
    def can_add_position(
        self,
        new_position: PositionSize,
        current_heat: OpenHeat,
        account_value: Decimal,
    ) -> bool:
        """
        Check if adding position would exceed max heat.
        
        Args:
            new_position: Proposed new position
            current_heat: Current portfolio heat
            account_value: Total account value
            
        Returns:
            True if position can be added without exceeding max heat
        """
        new_risk_pct = (new_position.risk_dollars / account_value) * 100
        projected_heat = current_heat.total_heat_pct + new_risk_pct
        
        return projected_heat <= self.risk_settings.max_heat_pct
    
    def get_heat_indicator(
        self,
        positions: List[Position],
        account_value: Decimal,
    ) -> HeatIndicator:
        """
        Get dashboard-ready heat indicator.
        
        Returns:
            HeatIndicator for UI display
        """
        heat = self.calculate_open_heat(positions, account_value)
        return HeatIndicator.from_open_heat(heat, self.risk_settings.max_heat_pct)
    
    def get_room_for_new_trade(
        self,
        current_heat: OpenHeat,
        account_value: Decimal,
    ) -> Decimal:
        """
        Calculate remaining room for new risk.
        
        Returns:
            Available risk in dollars
        """
        room_pct = self.risk_settings.max_heat_pct - current_heat.total_heat_pct
        room_dollars = (room_pct / 100) * account_value
        return max(Decimal("0"), room_dollars)
