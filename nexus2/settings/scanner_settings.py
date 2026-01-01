"""
Scanner Settings

User-configurable settings for the scanner module.
All settings are editable in the dashboard via Settings UI.
Based on: scanner_architecture.md
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ScannerSettings:
    """
    Scanner criteria thresholds.
    
    All values are KK-aligned with verified ranges.
    Editable via dashboard Settings UI.
    """
    
    # Momentum (KK-aligned, verified from multiple sources)
    # Sources vary: 25%/50%/100% (conservative) vs 19%/30%/50% (aggressive)
    # KK uses these to build "master stock list" of top performers
    min_performance_1m: Decimal = Decimal("25.0")   # KK range: 19-25%
    min_performance_3m: Decimal = Decimal("50.0")   # KK range: 30-50%
    min_performance_6m: Decimal = Decimal("100.0")  # KK range: 50-150%
    
    # Volatility
    min_adr_percent: Decimal = Decimal("4.0")  # KK: 4-5%
    
    # Volume & Liquidity (20-day lookback is KK-aligned)
    min_avg_volume: int = 300_000              # KK: avgv20>300000
    volume_lookback_days: int = 20             # KK uses 20-day (also 14-day for EP)
    min_dollar_volume: Decimal = Decimal("5_000_000")  # KK: $3-10M
    
    # Price & Market Cap
    min_price: Decimal = Decimal("5.0")        # KK: ≥$5
    abs_min_price: Decimal = Decimal("2.0")    # Clay: $2 absolute minimum
    min_market_cap: Decimal = Decimal("300_000_000")  # KK: $300-500M
    
    # Technical
    require_above_50ma: bool = True
    require_above_200ma: bool = True
    
    # Proximity
    min_proximity_to_high: Decimal = Decimal("75.0")  # % of 52-week high


@dataclass
class DisqualifierSettings:
    """
    Settings for stock/setup disqualification.
    
    Stocks/setups failing these criteria are filtered out.
    """
    
    max_extension_pct: Decimal = Decimal("30.0")   # KK: 20-30% above MAs
    max_stop_atr_ratio: Decimal = Decimal("1.0")   # KK: ≤1x ATR
    earnings_buffer_days: int = 3                  # KK: sell before earnings
    min_float_shares: int = 0                      # Set to filter low float
    max_float_shares: int = 0                      # Set to filter high float (0 = no max)


@dataclass
class PatternSettings:
    """
    Settings for chart pattern detection.
    """
    
    htf_min_move_pct: Decimal = Decimal("90.0")    # KK: 90-100%
    flag_min_move_pct: Decimal = Decimal("30.0")   # KK: 30-100%
    flag_max_retracement_pct: Decimal = Decimal("25.0")  # KK: 15-25%
    min_consolidation_days: int = 7                # KK: >1 week
    max_consolidation_days: int = 60               # KK: up to 2 months
    volume_contraction_threshold: Decimal = Decimal("50.0")  # % of average


@dataclass
class QualityScoringSettings:
    """
    Settings for quality score calculation.
    
    Each factor contributes 1 point when met.
    Total score: 0-10.
    """
    
    # Quality score thresholds
    high_quality_min: int = 8   # Score 8-10 = High (green)
    medium_quality_min: int = 5  # Score 5-7 = Medium (yellow)
    # Score <5 = Low (red)
    
    # Individual factor weights (all default to 1)
    weight_price: int = 1
    weight_volume: int = 1
    weight_dollar_volume: int = 1
    weight_above_50ma: int = 1
    weight_above_200ma: int = 1
    weight_rs_percentile: int = 1
    weight_not_extended: int = 1
    weight_tight_consolidation: int = 1
    weight_volume_contraction: int = 1
    weight_stop_within_atr: int = 1
