"""
Warrior Entry Pattern Scoring

Pattern Competition Framework for Warrior Trading entry logic.
Implements parallel pattern evaluation with quality scoring.

Ross Cameron methodology prioritizes pattern confidence as the PRIMARY differentiator:
- A textbook setup should win over a marginal setup
- Volume, catalyst, and context are supporting factors

Weights (per KI pattern_priority_framework.md):
- Pattern confidence: 50% (how textbook is the pattern?)
- Volume: 20% (confirmation)
- Catalyst: 15% (conviction)
- Spread + Level + Time: 15% (context)
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
# SCORING FUNCTIONS
# =============================================================================


def score_pattern(
    pattern: EntryTriggerType,
    volume_ratio: float,        # 3.0 = 3x average
    pattern_confidence: float,  # 0.0-1.0 (textbook pattern = 1.0)
    catalyst_strength: float,   # 0.0-1.0 (A+ = 1.0, none = 0.0)
    spread_pct: float,          # 0.5 = 0.5% spread
    level_proximity: float,     # 0.0-1.0 (at level = 1.0)
    time_score: float,          # 0.0-1.0 (ORB window = 1.0)
) -> float:
    """
    Calculate composite score for pattern quality.
    
    Weights (pattern confidence as PRIMARY differentiator):
    - Pattern confidence: 50% (how textbook is the pattern?)
    - Volume: 20% (confirmation)
    - Catalyst: 15% (conviction)
    - Spread + Level + Time: 15% (context)
    
    Args:
        pattern: The entry trigger type (for potential pattern-specific weights)
        volume_ratio: Current bar volume / average volume (e.g., 3.0 = 3x)
        pattern_confidence: How well price fits the pattern (0.0-1.0)
        catalyst_strength: Strength of news catalyst (0.0-1.0)
        spread_pct: Bid-ask spread as percentage (0.5 = 0.5%)
        level_proximity: How close to psychological level (0.0-1.0)
        time_score: Time-based factor (ORB window = 1.0)
    
    Returns:
        Composite score from 0.0 to 1.0
    """
    # Normalize volume ratio (cap at 20x for scoring)
    # >20x is great but doesn't need more weight
    vol_normalized = min(volume_ratio / 20.0, 1.0)
    
    # Spread penalty (lower is better)
    # 0.3% = excellent (score 0.85), 2% = poor (score 0.0)
    spread_score = max(0, 1.0 - (spread_pct / 2.0))
    
    # Weighted composite
    score = (
        pattern_confidence * 0.50 +  # PRIMARY: how well does price fit pattern?
        vol_normalized * 0.20 +
        catalyst_strength * 0.15 +
        spread_score * 0.05 +
        level_proximity * 0.05 +
        time_score * 0.05
    )
    
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
