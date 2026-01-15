"""
Market Regime Service

Market condition detection and regime indicator for trading recommendations.
Based on: scanner_architecture.md
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Callable, List, Optional, Protocol
from nexus2.utils.time_utils import now_et


class MarketRegime(Enum):
    """Market regime classification."""
    STRONG_BULL = "strong_bull"  # 10 > 20, both rising
    WEAK_BULL = "weak_bull"      # 10 ≈ 20, mixed
    NEUTRAL = "neutral"          # 10 ≈ 20, flat
    BEAR = "bear"                # 10 < 20, both falling


@dataclass
class RegimeIndicator:
    """Display-ready regime indicator for dashboard."""
    regime: MarketRegime
    color: str  # "green", "yellow", "orange", "red"
    label: str  # "Strong Bull", etc.
    nasdaq_price: Decimal
    nasdaq_vs_20ma: Decimal  # % distance
    ma_10_vs_20: str  # "above", "near", "below"
    trading_recommendation: str
    updated_at: datetime


@dataclass
class RegimeAction:
    """Trading recommendation based on regime."""
    regime: MarketRegime
    position_size_multiplier: Decimal  # 1.0 = full, 0.5 = half, 0 = sit out
    trading_allowed: bool
    message: str


class MarketDataProvider(Protocol):
    """Protocol for market data."""
    
    def get_nasdaq_price(self) -> Decimal:
        """Get current NASDAQ price."""
        ...
    
    def get_nasdaq_sma(self, period: int) -> Decimal:
        """Get NASDAQ SMA for period."""
        ...
    
    def get_ma_direction(self, period: int) -> str:
        """Get MA direction: 'rising', 'flat', 'falling'."""
        ...


class MarketRegimeService:
    """
    Market condition detection and indicator.
    
    Uses NASDAQ 10-day and 20-day MAs to classify market regime.
    Provides trading recommendations based on regime.
    """
    
    REGIME_COLORS = {
        MarketRegime.STRONG_BULL: "green",
        MarketRegime.WEAK_BULL: "yellow",
        MarketRegime.NEUTRAL: "orange",
        MarketRegime.BEAR: "red",
    }
    
    REGIME_LABELS = {
        MarketRegime.STRONG_BULL: "Strong Bull",
        MarketRegime.WEAK_BULL: "Weak Bull",
        MarketRegime.NEUTRAL: "Neutral",
        MarketRegime.BEAR: "Bear",
    }
    
    def __init__(self, market_data: MarketDataProvider):
        self.market_data = market_data
        self._subscribers: List[Callable[[MarketRegime], None]] = []
        self._last_regime: Optional[MarketRegime] = None
    
    def get_current_regime(self) -> MarketRegime:
        """
        Get current market regime based on NASDAQ MAs.
        
        Logic:
        - STRONG_BULL: 10 > 20, both rising
        - WEAK_BULL: 10 > 20 or near, mixed direction
        - NEUTRAL: 10 ≈ 20, flat
        - BEAR: 10 < 20, both falling
        """
        sma_10 = self.market_data.get_nasdaq_sma(10)
        sma_20 = self.market_data.get_nasdaq_sma(20)
        dir_10 = self.market_data.get_ma_direction(10)
        dir_20 = self.market_data.get_ma_direction(20)
        
        # Calculate relationship
        ma_diff_pct = ((sma_10 - sma_20) / sma_20) * 100
        
        if sma_10 > sma_20 and dir_10 == "rising" and dir_20 == "rising":
            return MarketRegime.STRONG_BULL
        elif sma_10 < sma_20 and dir_10 == "falling" and dir_20 == "falling":
            return MarketRegime.BEAR
        elif sma_10 > sma_20:
            return MarketRegime.WEAK_BULL
        else:
            return MarketRegime.NEUTRAL
    
    def get_regime_indicator(self) -> RegimeIndicator:
        """Get display-ready regime indicator."""
        regime = self.get_current_regime()
        nasdaq_price = self.market_data.get_nasdaq_price()
        sma_10 = self.market_data.get_nasdaq_sma(10)
        sma_20 = self.market_data.get_nasdaq_sma(20)
        
        # Calculate distances
        nasdaq_vs_20ma = ((nasdaq_price - sma_20) / sma_20) * 100
        
        # Determine MA relationship
        if sma_10 > sma_20 * Decimal("1.01"):
            ma_relationship = "above"
        elif sma_10 < sma_20 * Decimal("0.99"):
            ma_relationship = "below"
        else:
            ma_relationship = "near"
        
        # Get recommendation
        action = self.get_recommended_action(regime)
        
        return RegimeIndicator(
            regime=regime,
            color=self.REGIME_COLORS[regime],
            label=self.REGIME_LABELS[regime],
            nasdaq_price=nasdaq_price,
            nasdaq_vs_20ma=nasdaq_vs_20ma,
            ma_10_vs_20=ma_relationship,
            trading_recommendation=action.message,
            updated_at=now_et(),
        )
    
    def get_recommended_action(self, regime: MarketRegime) -> RegimeAction:
        """Get trading recommendation based on regime."""
        actions = {
            MarketRegime.STRONG_BULL: RegimeAction(
                regime=regime,
                position_size_multiplier=Decimal("1.0"),
                trading_allowed=True,
                message="Full trading. Breakout strategies work best.",
            ),
            MarketRegime.WEAK_BULL: RegimeAction(
                regime=regime,
                position_size_multiplier=Decimal("0.75"),
                trading_allowed=True,
                message="Selective trading. Be more choosy with setups.",
            ),
            MarketRegime.NEUTRAL: RegimeAction(
                regime=regime,
                position_size_multiplier=Decimal("0.5"),
                trading_allowed=True,
                message="Very selective. Only highest quality setups.",
            ),
            MarketRegime.BEAR: RegimeAction(
                regime=regime,
                position_size_multiplier=Decimal("0"),
                trading_allowed=False,
                message="Go to cash. Wait for market to improve.",
            ),
        }
        return actions[regime]
    
    def subscribe_regime_changes(
        self,
        callback: Callable[[MarketRegime], None]
    ) -> None:
        """Subscribe to regime change notifications."""
        self._subscribers.append(callback)
    
    def check_and_notify(self) -> Optional[MarketRegime]:
        """
        Check regime and notify subscribers if changed.
        
        Returns new regime if changed, None otherwise.
        """
        current = self.get_current_regime()
        
        if current != self._last_regime:
            self._last_regime = current
            for callback in self._subscribers:
                try:
                    callback(current)
                except Exception as e:
                    print(f"Error in regime change callback: {e}")
            return current
        
        return None
