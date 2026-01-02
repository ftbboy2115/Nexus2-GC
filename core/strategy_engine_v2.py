from __future__ import annotations

"""
Project: Strategy Engine v2
Filename: core/strategy_engine_v2.py
Version: 2.1.0
Author: Copilot, Gemini (Assistant) & [Your Name]
Date: 2025-12-16

Purpose:
    Unified scoring engine for all scanners (EP, TREND, HTF).

Design:
    - Balanced scoring curve (0–100).
    - Scanner-aware weights:
        * EP   → gap %, RS, catalyst, RVOL
        * TREND→ trend label, RS, liquidity, catalyst
        * HTF  → move %, pullback %, liquidity, catalyst
    - Penalties:
        * Weak/absent catalyst
        * Illiquid names
        * Excessive float
    - Bonuses:
        * Strong catalyst tags
        * Clean structure (gap / trend / move+pullback)
        * Reasonable float & liquidity

Output:
    StrategyResult:
        - score (0–100 int)
        - conviction ('A', 'B', 'C')
        - components: dict[str, float]
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class StrategyContext:
    """
    Unified context passed from scanners into Strategy Engine v2.

    All fields are optional except symbol & scanner; scanners only need to
    populate what they actually use.
    """

    symbol: str
    scanner: str  # 'EP', 'TREND', 'HTF', etc.

    # Core drivers
    catalyst_score: Optional[float] = None   # Raw catalyst score (0–100 or arbitrary)
    rs_rank: Optional[float] = None          # Relative strength percentile (0–100)
    rvol: Optional[float] = None             # Relative volume (1.5 = 150%)

    # Structural / pattern signals
    trend_label: Optional[str] = None        # 'PERFECT', 'COILING', 'SURFING', etc.
    move_pct: Optional[float] = None         # e.g., +90% = 90.0
    pullback_pct: Optional[float] = None     # e.g., -25% depth = 25.0
    gap_pct: Optional[float] = None          # e.g., +10% = 10.0

    # Liquidity / float
    float_m: Optional[float] = None          # float in millions
    dollar_vol_m: Optional[float] = None     # dollar volume in millions


@dataclass
class StrategyResult:
    """
    Standardized result from Strategy Engine v2.
    """

    score: int                      # 0–100 integer
    conviction: str                 # 'A', 'B', or 'C'
    components: Dict[str, float]    # detailed component scores


# ==============================================================================
# STRATEGY ENGINE V2
# ==============================================================================

class StrategyEngineV2:
    """
    Unified, scanner-aware strategy scoring engine.

    Notes:
        - Designed for "balanced" scoring – not hyper-conservative, not noisy.
        - All component scores are roughly in a [-10, +25] band.
        - Final score is normalized to [0, 100].
    """

    def __init__(self) -> None:
        # Base weights by scanner; used to slightly tilt priorities.
        self.scanner_profile: Dict[str, Dict[str, float]] = {
            "EP": {
                "catalyst": 1.2,
                "rs": 1.1,
                "rvol": 1.1,
                "liquidity": 1.0,
                "float": 1.0,
                "structure": 1.2,
                "trend": 1.0,
            },
            "TREND": {
                "catalyst": 1.0,
                "rs": 1.2,
                "rvol": 1.0,
                "liquidity": 1.1,
                "float": 1.1,
                "structure": 1.2,   # trend label is treated as structural
                "trend": 1.3,
            },
            "HTF": {
                "catalyst": 1.0,
                "rs": 0.9,
                "rvol": 0.9,
                "liquidity": 1.2,
                "float": 1.1,
                "structure": 1.4,   # move + pullback dominate
                "trend": 1.0,
            },
        }

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def score(self, ctx: StrategyContext, catalyst_tags: List[str]) -> StrategyResult:
        """
        Main entrypoint. Compute a unified score and conviction tier.

        Args:
            ctx: StrategyContext with scanner + metrics.
            catalyst_tags: list of tags from Catalyst Engine v2.

        Returns:
            StrategyResult with score, conviction, and component breakdown.
        """
        scanner_key = ctx.scanner.upper()
        profile = self.scanner_profile.get(scanner_key, self._default_profile())

        comp: Dict[str, float] = {}

        # Individual component scores (unweighted)
        comp["catalyst"] = self._score_catalyst(ctx, catalyst_tags)
        comp["rs"] = self._score_rs(ctx)
        comp["rvol"] = self._score_rvol(ctx)
        comp["liquidity"] = self._score_liquidity(ctx)
        comp["float"] = self._score_float(ctx)
        comp["structure"] = self._score_structure(ctx)
        comp["trend"] = self._score_trend(ctx)

        # Weighted sum
        raw_score = 0.0
        weight_sum = 0.0
        for k, v in comp.items():
            w = profile.get(k, 1.0)
            raw_score += v * w
            weight_sum += abs(w)

        # Normalize to 0–100
        # Tuned assuming typical raw component scores in [-10, 25]
        # and 6–7 components. The denominator (10.0) is chosen so that
        # strong setups land in the 60–80 range, matching test expectations.
        if weight_sum == 0:
            final_score = 0
        else:
            normalized = (raw_score / (weight_sum * 10.0)) * 100.0
            final_score = int(max(0, min(100, round(normalized))))

        conviction = self._score_to_conviction(final_score, comp, ctx, catalyst_tags)

        return StrategyResult(
            score=final_score,
            conviction=conviction,
            components=comp,
        )

    # ------------------------------------------------------------------
    # COMPONENT SCORERS
    # ------------------------------------------------------------------
    def _score_catalyst(self, ctx: StrategyContext, tags: List[str]) -> float:
        if ctx.catalyst_score is None:
            base = -5.0
        else:
            # Normalize arbitrary catalyst_score into roughly [-5, +20]
            scaled = max(0.0, min(100.0, ctx.catalyst_score))
            base = (scaled / 100.0) * 20.0 - 2.0  # small offset to keep mid-range modest

        # Tag-based bonuses
        tag_bonus = 0.0
        tag_map = {
            "earnings_recent": 4.0,
            "earnings_upcoming": 3.0,
            "high_short_interest": 3.0,
            "sector_hot": 2.0,
            "theme": 1.0,
            "insider_buying": 3.0,
            "institutional_buying": 3.0,
        }

        for t in tags:
            t_key = t.lower()
            tag_bonus += tag_map.get(t_key, 0.0)

        # Soft cap tag bonus to avoid runaway
        tag_bonus = min(tag_bonus, 8.0)

        score = base + tag_bonus
        return max(-10.0, min(25.0, score))

    def _score_rs(self, ctx: StrategyContext) -> float:
        if ctx.rs_rank is None:
            return 0.0

        rs = max(0.0, min(100.0, ctx.rs_rank))
        if rs < 50:
            return -3.0
        elif rs < 70:
            return 3.0
        elif rs < 85:
            return 8.0
        elif rs < 93:
            return 14.0
        else:
            return 20.0

    def _score_rvol(self, ctx: StrategyContext) -> float:
        if ctx.rvol is None:
            return 0.0

        r = ctx.rvol
        if r < 0.8:
            return -4.0
        elif r < 1.0:
            return -1.0
        elif r < 1.3:
            return 4.0
        elif r < 2.0:
            return 9.0
        else:
            return 14.0

    def _score_liquidity(self, ctx: StrategyContext) -> float:
        if ctx.dollar_vol_m is None:
            return 0.0

        dv = ctx.dollar_vol_m
        if dv < 5:
            return -6.0
        elif dv < 10:
            return -2.0
        elif dv < 30:
            return 4.0
        elif dv < 75:
            return 8.0
        else:
            return 12.0

    def _score_float(self, ctx: StrategyContext) -> float:
        if ctx.float_m is None:
            return 0.0

        f = ctx.float_m
        if f < 10:
            return 10.0
        elif f < 30:
            return 6.0
        elif f < 100:
            return 2.0
        elif f < 200:
            return -2.0
        else:
            return -6.0

    def _score_structure(self, ctx: StrategyContext) -> float:
        """
        Pattern/structure scoring:
            - EP: primarily gap_pct
            - TREND: handled via trend_label in _score_trend, structure is minor
            - HTF: move_pct + pullback_pct
        """
        scanner = ctx.scanner.upper()

        # EP: gap quality
        if scanner == "EP":
            if ctx.gap_pct is None:
                return 0.0
            g = ctx.gap_pct
            if g < 3:
                return -3.0
            elif g < 5:
                return 2.0
            elif g < 10:
                return 8.0
            elif g < 20:
                return 13.0
            else:
                return 10.0  # very large gaps get slightly damped

        # HTF: move + pullback quality
        if scanner == "HTF":
            if ctx.move_pct is None or ctx.pullback_pct is None:
                return 0.0

            move = ctx.move_pct
            pull = ctx.pullback_pct

            base = 0.0
            if move < 60:
                base -= 3.0
            elif move < 90:
                base += 4.0
            elif move < 150:
                base += 10.0
            else:
                base += 13.0

            # Pullback: 10–30% is ideal flag territory
            if pull < 5:
                base -= 1.0
            elif pull < 15:
                base += 4.0
            elif pull < 30:
                base += 6.0
            elif pull < 45:
                base += 1.0
            else:
                base -= 4.0

            return max(-10.0, min(20.0, base))

        # TREND / others: we mostly treat structure via trend_label
        return 0.0

    def _score_trend(self, ctx: StrategyContext) -> float:
        if not ctx.trend_label:
            return 0.0

        label = ctx.trend_label.upper()
        if label == "PERFECT":
            return 18.0
        elif label == "COILING":
            return 12.0
        elif label == "SURFING":
            return 10.0
        else:
            return 4.0

    # ------------------------------------------------------------------
    # CONVICTION LOGIC
    # ------------------------------------------------------------------
    def _score_to_conviction(
        self,
        score: int,
        comp: Dict[str, float],
        ctx: StrategyContext,
        tags: List[str],
    ) -> str:
        """
        Balanced conviction bands:

            - A: score >= 75 and no major red flags
            - B: score >= 55
            - C: everything else

        Major red flags:
            - Very weak catalyst component
            - Very poor liquidity / very large float
        """
        # Major red flags
        catalyst = comp.get("catalyst", 0.0)
        liquidity = comp.get("liquidity", 0.0)
        flt = comp.get("float", 0.0)

        weak_catalyst = catalyst < -2.0 and score < 85  # allow rare “raw RS monsters”
        illiquid = liquidity <= -4.0
        massive_float_penalty = flt <= -4.0

        has_red_flag = weak_catalyst or illiquid or massive_float_penalty

        if score >= 75 and not has_red_flag:
            return "A"
        elif score >= 55:
            return "B"
        else:
            return "C"

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------
    @staticmethod
    def _default_profile() -> Dict[str, float]:
        return {
            "catalyst": 1.0,
            "rs": 1.0,
            "rvol": 1.0,
            "liquidity": 1.0,
            "float": 1.0,
            "structure": 1.0,
            "trend": 1.0,
        }