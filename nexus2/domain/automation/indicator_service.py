"""
Indicator Service for Warrior Trading

Computes real-time quality indicators for Watchlist and Positions cards:
- Watchlist: Float, RVol, Gap, Catalyst, VWAP, Entry status
- Positions: MACD, 9/20/200 EMA, VWAP, Volume, Stop, Target

Based on Ross Cameron's methodology from "7 Candlestick Patterns" video.
"""

from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class IndicatorValue:
    """Single indicator with status and tooltip."""
    name: str           # "Float", "MACD", etc.
    status: str         # "green", "yellow", "red"
    value: float        # Actual numeric value
    tooltip: str        # "Float: 8.2M"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass  
class WatchlistIndicators:
    """Quality indicators for a watchlist candidate."""
    float_ind: IndicatorValue
    rvol_ind: IndicatorValue
    gap_ind: IndicatorValue
    catalyst_ind: IndicatorValue
    vwap_ind: IndicatorValue
    entry_ind: IndicatorValue
    
    def to_dict(self) -> dict:
        return {
            "float": self.float_ind.to_dict(),
            "rvol": self.rvol_ind.to_dict(),
            "gap": self.gap_ind.to_dict(),
            "catalyst": self.catalyst_ind.to_dict(),
            "vwap": self.vwap_ind.to_dict(),
            "entry": self.entry_ind.to_dict(),
        }


@dataclass
class PositionHealth:
    """Health indicators for an open position."""
    macd: IndicatorValue
    ema9: IndicatorValue
    ema20: IndicatorValue
    ema200: IndicatorValue
    vwap: IndicatorValue
    volume: IndicatorValue
    stop: IndicatorValue
    target: IndicatorValue
    
    def to_dict(self) -> dict:
        return {
            "macd": self.macd.to_dict(),
            "ema9": self.ema9.to_dict(),
            "ema20": self.ema20.to_dict(),
            "ema200": self.ema200.to_dict(),
            "vwap": self.vwap.to_dict(),
            "volume": self.volume.to_dict(),
            "stop": self.stop.to_dict(),
            "target": self.target.to_dict(),
        }


# =============================================================================
# Indicator Service
# =============================================================================

class IndicatorService:
    """Compute real-time indicators for Warrior Trading."""
    
    def __init__(self, get_quote=None, get_technicals=None):
        """
        Args:
            get_quote: Callback to get current quote for symbol
            get_technicals: Callback to get technical indicators (EMA, MACD)
        """
        self._get_quote = get_quote
        self._get_technicals = get_technicals
    
    def set_callbacks(self, get_quote=None, get_technicals=None):
        """Set data callbacks."""
        if get_quote:
            self._get_quote = get_quote
        if get_technicals:
            self._get_technicals = get_technicals
    
    # =========================================================================
    # Watchlist Indicators
    # =========================================================================
    
    def compute_watchlist_indicators(
        self,
        float_shares: Optional[float],
        rvol: float,
        gap_percent: float,
        catalyst_type: Optional[str],
        catalyst_desc: Optional[str],
        current_price: float,
        vwap: Optional[float],
        entry_status: str = "not_ready",  # not_ready, pending, triggered
        entry_price: Optional[float] = None,
    ) -> WatchlistIndicators:
        """Compute quality indicators for a watchlist candidate."""
        
        # Float indicator (< 10M green, 10-20M yellow, > 20M red)
        if float_shares is None:
            float_ind = IndicatorValue("Float", "gray", 0, "Float: N/A")
        elif float_shares < 10_000_000:
            float_ind = IndicatorValue("Float", "green", float_shares, f"Float: {float_shares/1e6:.1f}M")
        elif float_shares < 20_000_000:
            float_ind = IndicatorValue("Float", "yellow", float_shares, f"Float: {float_shares/1e6:.1f}M")
        else:
            float_ind = IndicatorValue("Float", "red", float_shares, f"Float: {float_shares/1e6:.1f}M")
        
        # RVol indicator (> 3x green, 2-3x yellow, < 2x red)
        if rvol >= 3.0:
            rvol_ind = IndicatorValue("RVol", "green", rvol, f"RVol: {rvol:.1f}x")
        elif rvol >= 2.0:
            rvol_ind = IndicatorValue("RVol", "yellow", rvol, f"RVol: {rvol:.1f}x")
        else:
            rvol_ind = IndicatorValue("RVol", "red", rvol, f"RVol: {rvol:.1f}x")
        
        # Gap indicator (> 15% green, 10-15% yellow, < 10% red)
        if gap_percent >= 15.0:
            gap_ind = IndicatorValue("Gap", "green", gap_percent, f"Gap: +{gap_percent:.1f}%")
        elif gap_percent >= 10.0:
            gap_ind = IndicatorValue("Gap", "yellow", gap_percent, f"Gap: +{gap_percent:.1f}%")
        else:
            gap_ind = IndicatorValue("Gap", "red", gap_percent, f"Gap: +{gap_percent:.1f}%")
        
        # Catalyst indicator (has catalyst = green, weak = yellow, none = red)
        if catalyst_type and catalyst_type.lower() not in ("none", "unknown", ""):
            catalyst_ind = IndicatorValue("Catalyst", "green", 1, catalyst_desc or catalyst_type)
        elif catalyst_desc:
            catalyst_ind = IndicatorValue("Catalyst", "yellow", 0.5, catalyst_desc)
        else:
            catalyst_ind = IndicatorValue("Catalyst", "red", 0, "No Catalyst")
        
        # VWAP indicator (above = green, at = yellow, below = red)
        if vwap is None:
            vwap_ind = IndicatorValue("VWAP", "gray", 0, "VWAP: N/A")
        elif current_price > vwap * 1.01:
            vwap_ind = IndicatorValue("VWAP", "green", vwap, f"VWAP: ${vwap:.2f} ✓")
        elif current_price >= vwap * 0.99:
            vwap_ind = IndicatorValue("VWAP", "yellow", vwap, f"VWAP: ${vwap:.2f}")
        else:
            vwap_ind = IndicatorValue("VWAP", "red", vwap, f"VWAP: ${vwap:.2f} ✗")
        
        # Entry indicator (triggered = green, pending = yellow, not_ready = red)
        if entry_status == "triggered":
            entry_tooltip = f"Entry @ ${entry_price:.2f}" if entry_price else "Entry Triggered"
            entry_ind = IndicatorValue("Entry", "green", 1, entry_tooltip)
        elif entry_status == "pending":
            entry_tooltip = f"Watching ${entry_price:.2f}" if entry_price else "Entry Pending"
            entry_ind = IndicatorValue("Entry", "yellow", 0.5, entry_tooltip)
        else:
            entry_ind = IndicatorValue("Entry", "red", 0, "Not Ready")
        
        return WatchlistIndicators(
            float_ind=float_ind,
            rvol_ind=rvol_ind,
            gap_ind=gap_ind,
            catalyst_ind=catalyst_ind,
            vwap_ind=vwap_ind,
            entry_ind=entry_ind,
        )
    
    # =========================================================================
    # Position Health Indicators
    # =========================================================================
    
    def compute_position_health(
        self,
        current_price: float,
        entry_price: float,
        stop_price: float,
        target_price: float,
        vwap: Optional[float] = None,
        ema9: Optional[float] = None,
        ema20: Optional[float] = None,
        ema200: Optional[float] = None,
        macd_value: Optional[float] = None,
        volume_ratio: Optional[float] = None,
    ) -> PositionHealth:
        """Compute health indicators for an open position."""
        
        # MACD (positive = green, flat = yellow, negative = red)
        if macd_value is None:
            macd = IndicatorValue("MACD", "gray", 0, "MACD: N/A")
        elif macd_value > 0.05:
            macd = IndicatorValue("MACD", "green", macd_value, f"MACD: +{macd_value:.2f}")
        elif macd_value >= -0.05:
            macd = IndicatorValue("MACD", "yellow", macd_value, f"MACD: {macd_value:.2f}")
        else:
            macd = IndicatorValue("MACD", "red", macd_value, f"MACD: {macd_value:.2f}")
        
        # 9 EMA (above = green, at = yellow, below = red)
        if ema9 is None:
            ema9_ind = IndicatorValue("9 EMA", "gray", 0, "9 EMA: N/A")
        elif current_price > ema9 * 1.005:
            ema9_ind = IndicatorValue("9 EMA", "green", ema9, f"9 EMA: ${ema9:.2f} ✓")
        elif current_price >= ema9 * 0.995:
            ema9_ind = IndicatorValue("9 EMA", "yellow", ema9, f"9 EMA: ${ema9:.2f}")
        else:
            ema9_ind = IndicatorValue("9 EMA", "red", ema9, f"9 EMA: ${ema9:.2f} ✗")
        
        # 20 EMA
        if ema20 is None:
            ema20_ind = IndicatorValue("20 EMA", "gray", 0, "20 EMA: N/A")
        elif current_price > ema20 * 1.005:
            ema20_ind = IndicatorValue("20 EMA", "green", ema20, f"20 EMA: ${ema20:.2f} ✓")
        elif current_price >= ema20 * 0.995:
            ema20_ind = IndicatorValue("20 EMA", "yellow", ema20, f"20 EMA: ${ema20:.2f}")
        else:
            ema20_ind = IndicatorValue("20 EMA", "red", ema20, f"20 EMA: ${ema20:.2f} ✗")
        
        # 200 EMA (ceiling/floor - above = green, near = yellow, below = red)
        if ema200 is None:
            ema200_ind = IndicatorValue("200 EMA", "gray", 0, "200 EMA: N/A")
        elif current_price > ema200 * 1.02:
            ema200_ind = IndicatorValue("200 EMA", "green", ema200, f"200 EMA: ${ema200:.2f} ✓")
        elif current_price >= ema200 * 0.98:
            ema200_ind = IndicatorValue("200 EMA", "yellow", ema200, f"200 EMA: ${ema200:.2f} (near)")
        else:
            ema200_ind = IndicatorValue("200 EMA", "red", ema200, f"200 EMA: ${ema200:.2f} (ceiling)")
        
        # VWAP
        if vwap is None:
            vwap_ind = IndicatorValue("VWAP", "gray", 0, "VWAP: N/A")
        elif current_price > vwap * 1.01:
            vwap_ind = IndicatorValue("VWAP", "green", vwap, f"VWAP: ${vwap:.2f} ✓")
        elif current_price >= vwap * 0.99:
            vwap_ind = IndicatorValue("VWAP", "yellow", vwap, f"VWAP: ${vwap:.2f}")
        else:
            vwap_ind = IndicatorValue("VWAP", "red", vwap, f"VWAP: ${vwap:.2f} ✗")
        
        # Volume (> 2x = green, 1-2x = yellow, < 1x = red)
        if volume_ratio is None:
            vol_ind = IndicatorValue("Volume", "gray", 0, "Vol: N/A")
        elif volume_ratio > 2.0:
            vol_ind = IndicatorValue("Volume", "green", volume_ratio, f"Vol: {volume_ratio:.1f}x")
        elif volume_ratio >= 1.0:
            vol_ind = IndicatorValue("Volume", "yellow", volume_ratio, f"Vol: {volume_ratio:.1f}x")
        else:
            vol_ind = IndicatorValue("Volume", "red", volume_ratio, f"Vol: {volume_ratio:.1f}x")
        
        # Stop distance (> 5% safe = green, 2-5% close = yellow, < 2% near = red)
        stop_distance_pct = ((current_price - stop_price) / current_price) * 100
        if stop_distance_pct > 5.0:
            stop_ind = IndicatorValue("Stop", "green", stop_distance_pct, f"Stop: ${stop_price:.2f} ({stop_distance_pct:+.1f}%)")
        elif stop_distance_pct > 2.0:
            stop_ind = IndicatorValue("Stop", "yellow", stop_distance_pct, f"Stop: ${stop_price:.2f} ({stop_distance_pct:+.1f}%)")
        else:
            stop_ind = IndicatorValue("Stop", "red", stop_distance_pct, f"Stop: ${stop_price:.2f} ({stop_distance_pct:+.1f}%)")
        
        # Target progress (> 80% near = green, 50-80% mid = yellow, < 50% far = red)
        if target_price > entry_price:
            target_range = target_price - entry_price
            progress = (current_price - entry_price) / target_range if target_range > 0 else 0
            progress_pct = progress * 100
        else:
            progress_pct = 0
        
        if progress_pct >= 80:
            target_ind = IndicatorValue("Target", "green", progress_pct, f"Target: ${target_price:.2f} ({progress_pct:.0f}%)")
        elif progress_pct >= 50:
            target_ind = IndicatorValue("Target", "yellow", progress_pct, f"Target: ${target_price:.2f} ({progress_pct:.0f}%)")
        else:
            target_ind = IndicatorValue("Target", "red", progress_pct, f"Target: ${target_price:.2f} ({progress_pct:.0f}%)")
        
        return PositionHealth(
            macd=macd,
            ema9=ema9_ind,
            ema20=ema20_ind,
            ema200=ema200_ind,
            vwap=vwap_ind,
            volume=vol_ind,
            stop=stop_ind,
            target=target_ind,
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_indicator_service: Optional[IndicatorService] = None


def get_indicator_service() -> IndicatorService:
    """Get or create the singleton indicator service."""
    global _indicator_service
    if _indicator_service is None:
        _indicator_service = IndicatorService()
    return _indicator_service
