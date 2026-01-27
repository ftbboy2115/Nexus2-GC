"""
Strategy Patterns Library

Defines the building blocks for strategy generation:
- Entry patterns (when to enter)
- Stop strategies (how to manage risk)
- Target strategies (when to exit for profit)

The Strategy Generator combines these patterns to create new strategies.
"""

from typing import Dict, List, Any
from enum import Enum


# =============================================================================
# ENTRY PATTERNS
# =============================================================================

class EntryPattern(str, Enum):
    """Available entry pattern types."""
    ORB_BREAK = "ORB_BREAK"
    PMH_BREAK = "PMH_BREAK"
    GAP_AND_GO = "GAP_AND_GO"
    MICRO_PULLBACK = "MICRO_PULLBACK"
    ABCD = "ABCD"
    EP_BREAK = "EP_BREAK"
    CATALYST_BREAK = "CATALYST_BREAK"
    FLAG_BREAK = "FLAG_BREAK"
    BASE_BREAK = "BASE_BREAK"
    RANGE_BREAK = "RANGE_BREAK"
    HTF_BREAK = "HTF_BREAK"
    VWAP_BOUNCE = "VWAP_BOUNCE"
    EMA_BOUNCE = "EMA_BOUNCE"
    REVERSAL_HAMMER = "REVERSAL_HAMMER"
    REVERSAL_ENGULFING = "REVERSAL_ENGULFING"
    FAILED_BREAK_FADE = "FAILED_BREAK_FADE"


ENTRY_PATTERNS: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # MOMENTUM / GAP PATTERNS
    # =========================================================================
    "ORB_BREAK": {
        "name": "Opening Range Breakout",
        "description": "Enter when price breaks above/below the opening range (first 5-15 min) with volume confirmation",
        "timeframe": "intraday",
        "parameters": {
            "orb_minutes": {"default": 5, "min": 1, "max": 30},
            "volume_multiplier": {"default": 1.5, "min": 1.0, "max": 5.0},
        },
    },
    
    "PMH_BREAK": {
        "name": "Pre-Market High Breakout",
        "description": "Enter when price breaks above the pre-market high with volume",
        "timeframe": "intraday",
        "parameters": {
            "volume_multiplier": {"default": 1.5, "min": 1.0, "max": 5.0},
            "buffer_cents": {"default": 0.02, "min": 0.01, "max": 0.10},
        },
    },
    
    "GAP_AND_GO": {
        "name": "Gap and Go",
        "description": "Enter after first pullback following gap up, when price resumes upward",
        "timeframe": "intraday",
        "parameters": {
            "min_gap_percent": {"default": 5.0, "min": 2.0, "max": 20.0},
            "pullback_bars": {"default": 2, "min": 1, "max": 5},
        },
    },
    
    "MICRO_PULLBACK": {
        "name": "Micro Pullback",
        "description": "Enter on 1-2 bar pullback in strong trending stock (Ross-style)",
        "timeframe": "intraday",
        "parameters": {
            "max_pullback_bars": {"default": 2, "min": 1, "max": 3},
            "min_prior_move_percent": {"default": 3.0, "min": 1.0, "max": 10.0},
        },
    },
    
    "ABCD": {
        "name": "ABCD Pattern",
        "description": "Enter at D point completion of ABCD harmonic pattern",
        "timeframe": "intraday",
        "parameters": {
            "fib_level": {"default": 0.618, "min": 0.5, "max": 0.786},
        },
    },
    
    # =========================================================================
    # EPISODIC PIVOT / CATALYST PATTERNS
    # =========================================================================
    "EP_BREAK": {
        "name": "Episodic Pivot Breakout",
        "description": "Enter on break of opening range after strong earnings/news catalyst (KK-style)",
        "timeframe": "daily",
        "parameters": {
            "min_gap_percent": {"default": 10.0, "min": 5.0, "max": 30.0},
            "orb_minutes": {"default": 5, "min": 1, "max": 15},
            "require_catalyst": {"default": True},
        },
    },
    
    "CATALYST_BREAK": {
        "name": "Catalyst Breakout",
        "description": "Enter on breakout following significant news catalyst with volume surge",
        "timeframe": "daily",
        "parameters": {
            "volume_multiplier": {"default": 3.0, "min": 2.0, "max": 10.0},
            "require_news": {"default": True},
        },
    },
    
    # =========================================================================
    # TECHNICAL PATTERNS
    # =========================================================================
    "FLAG_BREAK": {
        "name": "Flag Breakout",
        "description": "Enter on breakout from tight flag/pennant consolidation",
        "timeframe": "daily",
        "parameters": {
            "min_consolidation_bars": {"default": 3, "min": 2, "max": 10},
            "max_range_percent": {"default": 10.0, "min": 5.0, "max": 20.0},
        },
    },
    
    "BASE_BREAK": {
        "name": "Base Breakout",
        "description": "Enter on breakout from multi-day/week base formation",
        "timeframe": "daily",
        "parameters": {
            "min_base_days": {"default": 5, "min": 3, "max": 20},
            "max_depth_percent": {"default": 15.0, "min": 5.0, "max": 30.0},
        },
    },
    
    "RANGE_BREAK": {
        "name": "Range Expansion Breakout",
        "description": "Enter when daily range expands significantly above recent average",
        "timeframe": "daily",
        "parameters": {
            "range_multiplier": {"default": 2.0, "min": 1.5, "max": 4.0},
            "lookback_days": {"default": 10, "min": 5, "max": 20},
        },
    },
    
    "HTF_BREAK": {
        "name": "High Tight Flag Breakout",
        "description": "Enter on breakout from tight flag after 90%+ move in under 2 months",
        "timeframe": "daily",
        "parameters": {
            "min_prior_move_percent": {"default": 90.0, "min": 70.0, "max": 150.0},
            "max_flag_depth_percent": {"default": 25.0, "min": 10.0, "max": 35.0},
        },
    },
    
    "VWAP_BOUNCE": {
        "name": "VWAP Bounce",
        "description": "Enter on bounce off VWAP support in uptrending stock",
        "timeframe": "intraday",
        "parameters": {
            "max_distance_from_vwap_percent": {"default": 0.5, "min": 0.1, "max": 2.0},
            "require_uptrend": {"default": True},
        },
    },
    
    "EMA_BOUNCE": {
        "name": "EMA Bounce",
        "description": "Enter on bounce off key EMA (20/50/200) support",
        "timeframe": "daily",
        "parameters": {
            "ema_period": {"default": 20, "min": 8, "max": 200},
            "max_distance_percent": {"default": 1.0, "min": 0.5, "max": 3.0},
        },
    },
    
    # =========================================================================
    # REVERSAL PATTERNS
    # =========================================================================
    "REVERSAL_HAMMER": {
        "name": "Hammer Reversal",
        "description": "Enter on hammer candle at support after downmove",
        "timeframe": "intraday",
        "parameters": {
            "min_tail_ratio": {"default": 2.0, "min": 1.5, "max": 4.0},
            "require_support": {"default": True},
        },
    },
    
    "REVERSAL_ENGULFING": {
        "name": "Engulfing Candle Reversal",
        "description": "Enter on bullish engulfing candle at support",
        "timeframe": "daily",
        "parameters": {
            "require_support": {"default": True},
            "min_body_ratio": {"default": 1.5, "min": 1.0, "max": 3.0},
        },
    },
    
    "FAILED_BREAK_FADE": {
        "name": "Failed Breakout Fade",
        "description": "Short/fade when breakout fails and price reverses back into range",
        "timeframe": "intraday",
        "parameters": {
            "max_time_above_level_bars": {"default": 3, "min": 1, "max": 10},
            "min_rejection_percent": {"default": 1.0, "min": 0.5, "max": 3.0},
        },
    },
}


# =============================================================================
# STOP STRATEGIES
# =============================================================================

class StopStrategy(str, Enum):
    """Available stop loss strategies."""
    FIXED_CENTS = "FIXED_CENTS"
    FIXED_PERCENT = "FIXED_PERCENT"
    ATR_BASED = "ATR_BASED"
    TECHNICAL = "TECHNICAL"
    VWAP = "VWAP"
    EMA = "EMA"
    TRAILING = "TRAILING"


STOP_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "FIXED_CENTS": {
        "name": "Fixed Cents",
        "description": "Stop at fixed dollar amount below entry",
        "parameters": {
            "stop_cents": {"default": 0.15, "min": 0.05, "max": 1.00},
        },
    },
    
    "FIXED_PERCENT": {
        "name": "Fixed Percentage",
        "description": "Stop at fixed percentage below entry",
        "parameters": {
            "stop_percent": {"default": 2.0, "min": 0.5, "max": 10.0},
        },
    },
    
    "ATR_BASED": {
        "name": "ATR Multiple",
        "description": "Stop at multiple of ATR below entry",
        "parameters": {
            "atr_multiplier": {"default": 1.0, "min": 0.5, "max": 3.0},
            "atr_period": {"default": 14, "min": 5, "max": 20},
        },
    },
    
    "TECHNICAL": {
        "name": "Technical Level",
        "description": "Stop below key technical level (ORB low, flag low, etc.)",
        "parameters": {
            "level_type": {"default": "orb_low", "options": ["orb_low", "flag_low", "swing_low", "support"]},
            "buffer_cents": {"default": 0.05, "min": 0.01, "max": 0.20},
        },
    },
    
    "VWAP": {
        "name": "Below VWAP",
        "description": "Stop when price closes below VWAP",
        "parameters": {
            "buffer_cents": {"default": 0.03, "min": 0.01, "max": 0.10},
        },
    },
    
    "EMA": {
        "name": "Below EMA",
        "description": "Stop when price closes below key EMA",
        "parameters": {
            "ema_period": {"default": 9, "min": 5, "max": 50},
            "buffer_cents": {"default": 0.03, "min": 0.01, "max": 0.10},
        },
    },
    
    "TRAILING": {
        "name": "Trailing Stop",
        "description": "Trail stop as position moves in favor",
        "parameters": {
            "trail_percent": {"default": 1.5, "min": 0.5, "max": 5.0},
            "activation_r": {"default": 1.0, "min": 0.5, "max": 3.0},
        },
    },
}


# =============================================================================
# TARGET STRATEGIES
# =============================================================================

class TargetStrategy(str, Enum):
    """Available profit target strategies."""
    R_MULTIPLE = "R_MULTIPLE"
    TRAILING = "TRAILING"
    PARTIAL = "PARTIAL"
    EXTENSION = "EXTENSION"
    EOD = "EOD"
    RESISTANCE = "RESISTANCE"
    TIME_BASED = "TIME_BASED"


TARGET_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "R_MULTIPLE": {
        "name": "R-Multiple Target",
        "description": "Exit at fixed multiple of initial risk (e.g., 2R, 3R)",
        "parameters": {
            "target_r": {"default": 2.0, "min": 1.0, "max": 10.0},
        },
    },
    
    "TRAILING": {
        "name": "Trailing Exit",
        "description": "Trail profit after initial target hit, exit on trail break",
        "parameters": {
            "initial_target_r": {"default": 1.0, "min": 0.5, "max": 3.0},
            "trail_percent": {"default": 1.0, "min": 0.3, "max": 3.0},
        },
    },
    
    "PARTIAL": {
        "name": "Partial Scaling",
        "description": "Scale out at multiple levels (e.g., 1/3 at 1R, 1/3 at 2R, trail rest)",
        "parameters": {
            "scale_1_r": {"default": 1.0, "min": 0.5, "max": 2.0},
            "scale_1_percent": {"default": 33, "min": 20, "max": 50},
            "scale_2_r": {"default": 2.0, "min": 1.0, "max": 4.0},
            "scale_2_percent": {"default": 33, "min": 20, "max": 50},
        },
    },
    
    "EXTENSION": {
        "name": "Fibonacci Extension",
        "description": "Target Fibonacci extension level from prior move",
        "parameters": {
            "extension_level": {"default": 1.618, "min": 1.272, "max": 2.618},
        },
    },
    
    "EOD": {
        "name": "End of Day",
        "description": "Close all positions at end of day (day trade)",
        "parameters": {
            "exit_time": {"default": "15:50", "format": "HH:MM"},
        },
    },
    
    "RESISTANCE": {
        "name": "Resistance Target",
        "description": "Target previous day high or key resistance level",
        "parameters": {
            "level_type": {"default": "pdh", "options": ["pdh", "52w_high", "resistance"]},
        },
    },
    
    "TIME_BASED": {
        "name": "Time-Based Exit",
        "description": "Exit after holding for specified duration",
        "parameters": {
            "hold_minutes": {"default": 30, "min": 5, "max": 390},
        },
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_all_patterns() -> Dict[str, Dict[str, Any]]:
    """Get all patterns organized by category."""
    return {
        "entry": ENTRY_PATTERNS,
        "stop": STOP_STRATEGIES,
        "target": TARGET_STRATEGIES,
    }


def format_patterns_for_prompt() -> str:
    """Format all patterns for inclusion in LLM prompt."""
    lines = []
    
    lines.append("ENTRY PATTERNS:")
    for key, p in ENTRY_PATTERNS.items():
        lines.append(f"  - {key}: {p['description']}")
    
    lines.append("\nSTOP STRATEGIES:")
    for key, s in STOP_STRATEGIES.items():
        lines.append(f"  - {key}: {s['description']}")
    
    lines.append("\nTARGET STRATEGIES:")
    for key, t in TARGET_STRATEGIES.items():
        lines.append(f"  - {key}: {t['description']}")
    
    return "\n".join(lines)


def get_pattern_parameters(pattern_type: str, pattern_name: str) -> Dict[str, Any]:
    """Get the configurable parameters for a specific pattern."""
    if pattern_type == "entry":
        return ENTRY_PATTERNS.get(pattern_name, {}).get("parameters", {})
    elif pattern_type == "stop":
        return STOP_STRATEGIES.get(pattern_name, {}).get("parameters", {})
    elif pattern_type == "target":
        return TARGET_STRATEGIES.get(pattern_name, {}).get("parameters", {})
    return {}
