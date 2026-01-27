"""
Trading Methodologies Registry

Defines the available trading methodologies (styles) that the Strategy Generator
can use when creating new strategies. Each methodology specifies:
- Preferred entry patterns
- Price range constraints
- Typical hold time
- Style description

Extensible - add new methodologies as needed.
"""

from typing import Dict, List, Optional, Tuple, Any


# Registry of all available methodologies
METHODOLOGIES: Dict[str, Dict[str, Any]] = {
    # ==========================================================================
    # ROSS CAMERON - WARRIOR TRADING
    # ==========================================================================
    "warrior": {
        "name": "Warrior (Ross Cameron)",
        "style": "Momentum scalping on low-float gappers",
        "description": "Day trading small-cap stocks with high relative volume, focusing on quick scalps off opening range breakouts and pullback entries.",
        "preferred_patterns": ["ORB_BREAK", "PMH_BREAK", "GAP_AND_GO", "MICRO_PULLBACK"],
        "price_range": (1.0, 20.0),  # Ross focuses on $1-$20
        "hold_time": "minutes to hours",
        "typical_risk": 0.10,  # $0.10 stops typical
        "max_positions": 3,
    },
    
    # ==========================================================================
    # KRISTJAN KULLAMÄGI (QULLAMAGGIE) - MULTIPLE STRATEGIES
    # ==========================================================================
    "kk_ep": {
        "name": "KK Episodic Pivot",
        "style": "Earnings-driven momentum on catalyst days",
        "description": "Trading stocks with strong earnings/news catalysts that create episodic pivots. Entry on break of opening range with tight stops.",
        "preferred_patterns": ["EP_BREAK", "CATALYST_BREAK"],
        "price_range": (5.0, None),  # No upper limit
        "hold_time": "days",
        "typical_risk": 0.50,  # ATR-based
        "max_positions": 5,
    },
    
    "kk_breakout": {
        "name": "KK Breakout",
        "style": "Technical breakout from multi-day consolidation",
        "description": "Trading breakouts from tight flag patterns, bases, and consolidation ranges. Focus on relative strength leaders.",
        "preferred_patterns": ["FLAG_BREAK", "BASE_BREAK", "RANGE_BREAK"],
        "price_range": (10.0, None),
        "hold_time": "days to weeks",
        "typical_risk": 0.75,
        "max_positions": 5,
    },
    
    "kk_htf": {
        "name": "KK High Tight Flag",
        "style": "High tight flag breakouts (90%+ prior move)",
        "description": "Trading stocks that have moved 90%+ in under 2 months and are now consolidating tightly near highs. Very selective.",
        "preferred_patterns": ["HTF_BREAK"],
        "price_range": (10.0, None),
        "hold_time": "days to weeks",
        "typical_risk": 1.0,
        "max_positions": 3,
    },
    
    # ==========================================================================
    # MEAN REVERSION / REVERSAL STRATEGIES
    # ==========================================================================
    "reversal": {
        "name": "Reversal",
        "style": "Mean reversion on overextended moves",
        "description": "Fading overextended stocks at key levels. Entry on reversal candle patterns with tight stops.",
        "preferred_patterns": ["REVERSAL_HAMMER", "REVERSAL_ENGULFING", "FAILED_BREAK_FADE"],
        "price_range": (5.0, None),
        "hold_time": "minutes to hours",
        "typical_risk": 0.30,
        "max_positions": 2,
    },
    
    # ==========================================================================
    # SWING TRADING
    # ==========================================================================
    "swing": {
        "name": "Swing",
        "style": "Multi-day momentum continuation",
        "description": "Holding winners for multiple days, scaling out on strength. Focus on trending stocks with strong RS.",
        "preferred_patterns": ["FLAG_BREAK", "BASE_BREAK", "EMA_BOUNCE"],
        "price_range": (10.0, None),
        "hold_time": "days to weeks",
        "typical_risk": 1.0,
        "max_positions": 5,
    },
    
    # ==========================================================================
    # CUSTOM - USER DEFINED
    # ==========================================================================
    "custom": {
        "name": "Custom",
        "style": "User-defined methodology",
        "description": "All patterns and parameters available. Define your own trading style.",
        "preferred_patterns": [],  # All patterns available
        "price_range": (1.0, None),
        "hold_time": "any",
        "typical_risk": 0.50,
        "max_positions": 5,
    },
}


def get_methodology(name: str) -> Optional[Dict[str, Any]]:
    """Get a methodology by name."""
    return METHODOLOGIES.get(name)


def get_all_methodologies() -> Dict[str, Dict[str, Any]]:
    """Get all available methodologies."""
    return METHODOLOGIES


def get_methodology_names() -> List[str]:
    """Get list of all methodology names."""
    return list(METHODOLOGIES.keys())


def format_methodologies_for_prompt() -> str:
    """Format methodologies for inclusion in LLM prompt."""
    lines = []
    for key, m in METHODOLOGIES.items():
        lines.append(f"- {key}: {m['name']} - {m['style']}")
        patterns = ', '.join(m['preferred_patterns']) or 'Any'
        lines.append(f"  Preferred patterns: {patterns}")
        min_price = m['price_range'][0]
        max_price = m['price_range'][1]
        max_price_str = 'No limit' if max_price is None else f'${max_price:.0f}'
        lines.append(f"  Price range: ${min_price:.0f} - {max_price_str}")
        lines.append(f"  Hold time: {m['hold_time']}")
        lines.append("")
    return "\n".join(lines)

