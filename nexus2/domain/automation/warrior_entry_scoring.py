"""
Warrior Entry Pattern Scoring

Pattern Competition Framework for Warrior Trading entry logic.
Implements parallel pattern evaluation with quality scoring.

Dynamic scoring (Phase 2): Incorporates real-time price action data
alongside static scanner metadata to distinguish fresh breakouts from
fading re-entries.

Weight distribution (55% static / 45% dynamic):
- Pattern confidence: 35% (how textbook is the pattern?)
- Volume ratio: 10% (scanner RVOL)
- Catalyst: 8% (conviction)
- Time + Level + Spread: 7% (context)
- MACD momentum: 10% (histogram strength)
- EMA trend: 8% (9/20 EMA alignment)
- Re-entry decay: 8% (penalize 2nd, 3rd attempts)
- VWAP position: 6% (above VWAP = healthy)
- Volume expansion: 4% (current bar vs avg)
- Price extension: 4% (distance from PMH)
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from nexus2.domain.automation.warrior_engine_types import EntryTriggerType


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class PatternCandidate:
    """
    A pattern that matched with its quality score.
    
    Used for parallel pattern evaluation - all matching patterns are collected,
    scored, and the winner is selected for entry.
    
    Attributes:
        pattern: The EntryTriggerType that matched
        score: Composite quality score (0.0 to 1.0)
        factors: Debug dict showing what contributed to score
    """
    pattern: EntryTriggerType
    score: float  # 0.0 to 1.0
    factors: dict = field(default_factory=dict)  # Debug: what contributed to score


# =============================================================================
# CONSTANTS
# =============================================================================


# FAIL-CLOSED: Require minimum quality to enter
# 0.40 = 40% quality threshold
# This prevents entry on marginal patterns with weak factors
MIN_SCORE_THRESHOLD = 0.40


# =============================================================================
# DYNAMIC SCORING HELPER FUNCTIONS
# =============================================================================


def compute_macd_score(histogram: Optional[float]) -> float:
    """
    Score MACD histogram strength.
    
    Strong positive histogram = fresh momentum = high score.
    Weak/negative histogram = fading = low score.
    
    Args:
        histogram: MACD histogram value (positive = bullish)
    
    Returns:
        Score from 0.0 to 1.0
    """
    if histogram is None:
        return 0.5  # Unknown = neutral (backward compat)
    
    if histogram >= 0.3:
        return 1.0  # Very strong momentum
    elif histogram >= 0.1:
        return 0.8  # Strong
    elif histogram >= 0.01:
        return 0.6  # Moderate positive
    elif histogram >= -0.01:
        return 0.4  # Near zero (transitional)
    elif histogram >= -0.1:
        return 0.2  # Weakening
    else:
        return 0.0  # Fading/negative


def compute_ema_trend_score(is_above_ema9: bool, is_above_ema20: bool) -> float:
    """
    Score based on EMA 9/20 alignment.
    
    Ross Cameron uses 9 and 20 EMA to confirm trend:
    - Above both = strong uptrend
    - Above 20 only = weakening but still in trend
    - Below both = trend is over
    
    Args:
        is_above_ema9: True if price > 9 EMA
        is_above_ema20: True if price > 20 EMA
    
    Returns:
        1.0 (strong), 0.5 (weakening), 0.2 (bearish)
    """
    if is_above_ema9 and is_above_ema20:
        return 1.0  # Strong uptrend
    elif is_above_ema20:
        return 0.5  # Weakening - below fast EMA but above slow
    else:
        return 0.2  # Bearish - below both EMAs


def compute_reentry_decay(count: int) -> float:
    """
    Penalize re-entry attempts.
    
    Ross Cameron rarely takes more than 2-3 attempts on same stock.
    1st entry = full conviction, subsequent entries = decaying confidence.
    
    Args:
        count: Number of previous entry attempts on this symbol
    
    Returns:
        Score from 0.0 to 1.0 (decaying with attempts)
    """
    if count <= 0:
        return 1.0   # First attempt = full conviction
    elif count == 1:
        return 0.6   # Second attempt = reduced
    elif count == 2:
        return 0.3   # Third attempt = significant penalty
    else:
        return 0.15  # 4th+ = very low confidence


def compute_vwap_score(distance_pct: Optional[float]) -> float:
    """
    Score based on distance from VWAP.
    
    Ross Cameron prefers entries above VWAP. Being far above VWAP
    is good (momentum), but extremely far may indicate extension.
    Below VWAP = warning sign.
    
    Args:
        distance_pct: (price - vwap) / vwap * 100 (positive = above)
    
    Returns:
        Score from 0.0 to 1.0
    """
    if distance_pct is None:
        return 0.5  # Unknown = neutral
    
    if distance_pct < -2.0:
        return 0.0  # Well below VWAP
    elif distance_pct < 0:
        return 0.2  # Slightly below VWAP
    elif distance_pct < 1.0:
        return 0.6  # At VWAP (just crossed)
    elif distance_pct < 5.0:
        return 1.0  # Sweet spot: above VWAP in momentum
    elif distance_pct < 15.0:
        return 0.7  # Getting extended but still OK
    else:
        return 0.4  # Very extended from VWAP


def compute_volume_expansion_score(ratio: Optional[float]) -> float:
    """
    Score based on current bar volume vs average.
    
    Ross Cameron requires volume EXPLOSION on entries. Higher ratio = 
    more institutional interest = better entry.
    
    Args:
        ratio: current bar volume / average volume (e.g., 10.0 = 10x)
    
    Returns:
        Score from 0.0 to 1.0
    """
    if ratio is None:
        return 0.5  # Unknown = neutral
    
    if ratio >= 10.0:
        return 1.0  # Volume explosion
    elif ratio >= 5.0:
        return 0.8  # Strong volume
    elif ratio >= 3.0:
        return 0.6  # Moderate expansion
    elif ratio >= 1.5:
        return 0.4  # Mild expansion
    elif ratio >= 1.0:
        return 0.3  # Average volume
    else:
        return 0.1  # Below average (weak)


def compute_extension_score(pct: Optional[float]) -> float:
    """
    Score based on price extension from PMH.
    
    Near PMH = fresh breakout = good.
    Far above PMH = already extended = riskier entry.
    
    Args:
        pct: (price - pmh) / pmh * 100 (positive = above PMH)
    
    Returns:
        Score from 0.0 to 1.0
    """
    if pct is None:
        return 0.5  # Unknown = neutral
    
    if pct < 0:
        return 0.7  # Below PMH (dip-for-level, anticipatory)
    elif pct < 2.0:
        return 1.0  # Fresh breakout, near PMH
    elif pct < 5.0:
        return 0.8  # Slightly extended
    elif pct < 10.0:
        return 0.6  # Moderate extension
    elif pct < 20.0:
        return 0.4  # Getting extended
    else:
        return 0.2  # Very extended




# =============================================================================
# MAIN SCORING FUNCTION
# =============================================================================


def score_pattern(
    pattern: EntryTriggerType,
    volume_ratio: float,        # 3.0 = 3x average
    pattern_confidence: float,  # 0.0-1.0 (textbook pattern = 1.0)
    catalyst_strength: float,   # 0.0-1.0 (A+ = 1.0, none = 0.0)
    spread_pct: float,          # 0.5 = 0.5% spread
    level_proximity: float,     # 0.0-1.0 (at level = 1.0)
    time_score: float,          # 0.0-1.0 (ORB window = 1.0)
    blue_sky_pct: Optional[float] = None,  # % distance to 52-week high (0 = at ATH)
    # NEW: Dynamic factors (all optional for backward compatibility)
    macd_histogram: Optional[float] = None,       # From entry_snapshot
    reentry_count: int = 0,                        # From watched.entry_attempt_count
    ema_trend: Optional[str] = None,               # "strong"/"weakening"/"bearish"
    vwap_distance_pct: Optional[float] = None,     # (price - vwap) / vwap * 100
    volume_expansion: Optional[float] = None,      # current bar vol / avg vol ratio
    price_extension_pct: Optional[float] = None,   # (price - pmh) / pmh * 100
) -> float:
    """
    Calculate composite score for pattern quality.
    
    Phase 2.1 weights (55% static / 45% dynamic):
    - Pattern confidence: 35% (how textbook is the pattern?)
    - Volume ratio (scanner): 10% (confirmation)
    - Catalyst strength: 8% (conviction)
    - MACD momentum: 10% (histogram strength)
    - EMA trend (9/20): 8% (trend alignment)
    - Re-entry decay: 8% (penalize repeated attempts)
    - VWAP position: 6% (momentum indicator)
    - Volume expansion: 4% (current bar activity)
    - Price extension: 4% (distance from breakout level)
    - Time score: 4% (ORB window optimal)
    - Level proximity + spread: 3% (context)
    
    BONUS (not weighted, added on top):
    - Blue Sky: +0.10 boost when price is within 5% of 52-week high
    
    Args:
        pattern: The entry trigger type
        volume_ratio: Scanner RVOL (e.g., 3.0 = 3x)
        pattern_confidence: How well price fits the pattern (0.0-1.0)
        catalyst_strength: Strength of news catalyst (0.0-1.0)
        spread_pct: Bid-ask spread as percentage
        level_proximity: How close to psychological level (0.0-1.0)
        time_score: Time-based factor (ORB window = 1.0)
        blue_sky_pct: Distance to 52-week high (0 = at ATH)
        macd_histogram: MACD histogram value (positive = bullish)
        reentry_count: Number of previous entry attempts
        ema_trend: "strong"/"weakening"/"bearish" from EMA alignment
        vwap_distance_pct: Distance from VWAP as %
        volume_expansion: Current bar vol / avg vol ratio
        price_extension_pct: Distance from PMH as %
    
    Returns:
        Composite score from 0.0 to ~1.10 (with Blue Sky bonus)
    """
    # --- Static factors ---
    vol_normalized = min(volume_ratio / 20.0, 1.0)
    spread_score = max(0, 1.0 - (spread_pct / 2.0))
    
    # --- Dynamic factors ---
    macd_score = compute_macd_score(macd_histogram)
    
    # EMA trend: convert string to score, or use helper directly
    if ema_trend == "strong":
        ema_score = 1.0
    elif ema_trend == "weakening":
        ema_score = 0.5
    elif ema_trend == "bearish":
        ema_score = 0.2
    else:
        ema_score = 0.5  # Unknown = neutral (backward compat)
    
    reentry_score = compute_reentry_decay(reentry_count)
    vwap_score = compute_vwap_score(vwap_distance_pct)
    vol_expansion_score = compute_volume_expansion_score(volume_expansion)
    extension_score = compute_extension_score(price_extension_pct)
    
    # --- Weighted composite (55% static / 45% dynamic) ---
    score = (
        # Static factors (55%)
        pattern_confidence * 0.35 +    # Pattern quality
        vol_normalized * 0.10 +        # Scanner RVOL
        catalyst_strength * 0.08 +     # Catalyst
        time_score * 0.04 +            # Time
        # Dynamic factors (45%)
        macd_score * 0.10 +            # MACD momentum
        ema_score * 0.08 +             # EMA trend
        reentry_score * 0.08 +         # Re-entry decay
        vwap_score * 0.06 +            # VWAP position
        vol_expansion_score * 0.04 +   # Volume expansion
        extension_score * 0.04 +       # Price extension
        # Context (shared static/slow)
        spread_score * 0.015 +
        level_proximity * 0.015
    )
    
    # Blue Sky Bonus: no overhead resistance = smoother breakouts
    if blue_sky_pct is not None and blue_sky_pct <= 5.0:
        score += 0.10
    
    return round(score, 3)


def compute_level_proximity(price: Decimal) -> float:
    """
    Compute proximity to nearest psychological level (whole/half dollar).
    
    Args:
        price: Current stock price
    
    Returns:
        Score from 0.0 (far from level) to 1.0 (at level)
    """
    price_float = float(price)
    # Nearest $0.50 level
    nearest_level = round(price_float * 2) / 2
    # Distance from level, normalized (0.25 = max distance to be considered "near")
    distance = abs(price_float - nearest_level)
    return 1.0 - min(distance / 0.25, 1.0)


def compute_time_score(et_hour: int, et_minute: int) -> float:
    """
    Compute time-based score (ORB window is optimal).
    
    Ross Cameron's optimal trading window is 9:30 AM - 10:30 AM ET.
    Earlier pre-market and late morning are acceptable but less ideal.
    
    Args:
        et_hour: Eastern Time hour (0-23)
        et_minute: Eastern Time minute (0-59)
    
    Returns:
        Score from 0.0 to 1.0
    """
    # Convert to minutes since midnight for easier comparison
    et_minutes = et_hour * 60 + et_minute
    
    # ORB window: 9:30 - 10:30 = 570 - 630 minutes
    if 570 <= et_minutes <= 630:
        return 1.0
    # Extended prime window: 9:00 - 11:00 = 540 - 660 minutes
    elif 540 <= et_minutes <= 660:
        return 0.7
    # Pre-market/afternoon: acceptable but not ideal
    else:
        return 0.4


def compute_blue_sky_pct(price: Decimal, year_high: Optional[Decimal]) -> Optional[float]:
    """
    Compute distance from current price to 52-week high.
    
    "Blue Sky" = stock trading at or near all-time/52-week high.
    No overhead resistance leads to smoother breakouts.
    
    Args:
        price: Current stock price
        year_high: 52-week high price (from FMP quote)
    
    Returns:
        Percentage distance from 52-week high (0 = at ATH, 5 = 5% below)
        None if year_high is not available
    """
    if year_high is None or year_high <= 0:
        return None
    
    price_float = float(price)
    year_high_float = float(year_high)
    
    if price_float >= year_high_float:
        # At or above 52-week high = full Blue Sky
        return 0.0
    
    # Calculate percentage below 52-week high
    pct_below = ((year_high_float - price_float) / year_high_float) * 100
    return round(pct_below, 2)
