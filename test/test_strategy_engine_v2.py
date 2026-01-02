"""
⭐ What this test suite gives you
1. Coverage of all major scoring components
- Catalyst
- RS
- RVOL
- Liquidity
- Float
- Structure
- Trend
2. Coverage of all scanners
- EP
- TREND
- HTF
3. Coverage of conviction logic
- A‑tier
- B‑tier
- C‑tier
4. Synthetic, deterministic inputs
No API calls, no randomness, no external dependencies.

"""


import unittest
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext


class TestStrategyEngineV2(unittest.TestCase):

    def setUp(self):
        self.engine = StrategyEngineV2()

    # ---------------------------------------------------------
    # 1. RS Monster + Weak Catalyst
    # ---------------------------------------------------------
    def test_rs_monster_weak_catalyst(self):
        ctx = StrategyContext(
            symbol="TEST",
            scanner="TREND",
            catalyst_score=5,        # weak catalyst
            rs_rank=98,              # RS monster
            rvol=1.2,
            trend_label="PERFECT",
            float_m=20,
            dollar_vol_m=50,
        )
        result = self.engine.score(ctx, catalyst_tags=[])

        self.assertGreater(result.components["rs"], 10)
        self.assertLess(result.components["catalyst"], 5)
        self.assertGreaterEqual(result.score, 55)
        self.assertIn(result.conviction, ["A", "B"])

    # ---------------------------------------------------------
    # 2. Strong Catalyst + Low Float + High RVOL
    # ---------------------------------------------------------
    def test_strong_catalyst_low_float(self):
        ctx = StrategyContext(
            symbol="LOWF",
            scanner="EP",
            catalyst_score=90,
            rs_rank=80,
            rvol=2.5,
            gap_pct=12,
            float_m=5,
            dollar_vol_m=40,
        )
        result = self.engine.score(ctx, catalyst_tags=["earnings_recent"])

        self.assertGreater(result.components["catalyst"], 10)
        self.assertGreater(result.components["float"], 5)
        self.assertGreater(result.components["rvol"], 10)
        self.assertGreaterEqual(result.score, 70)
        self.assertIn(result.conviction, ["A", "B"])

    # ---------------------------------------------------------
    # 3. Illiquid + High Float (should penalize)
    # ---------------------------------------------------------
    def test_illiquid_high_float(self):
        ctx = StrategyContext(
            symbol="BAD",
            scanner="TREND",
            catalyst_score=50,
            rs_rank=60,
            rvol=0.9,
            trend_label="SURFING",
            float_m=300,             # huge float
            dollar_vol_m=3,          # illiquid
        )
        result = self.engine.score(ctx, catalyst_tags=[])

        self.assertLess(result.components["liquidity"], 0)
        self.assertLess(result.components["float"], 0)
        self.assertLessEqual(result.score, 50)
        self.assertEqual(result.conviction, "C")

    # ---------------------------------------------------------
    # 4. HTF: Big Move + Clean Pullback
    # ---------------------------------------------------------
    def test_htf_structure(self):
        ctx = StrategyContext(
            symbol="HTF",
            scanner="HTF",
            catalyst_score=40,
            move_pct=120,            # strong move
            pullback_pct=18,         # ideal pullback
            float_m=25,
            dollar_vol_m=60,
        )
        result = self.engine.score(ctx, catalyst_tags=["sector_hot"])

        self.assertGreater(result.components["structure"], 8)
        self.assertGreaterEqual(result.score, 55)
        self.assertIn(result.conviction, ["A", "B"])

    # ---------------------------------------------------------
    # 5. EP: Small Gap Should Penalize
    # ---------------------------------------------------------
    def test_ep_small_gap(self):
        ctx = StrategyContext(
            symbol="EPX",
            scanner="EP",
            catalyst_score=60,
            rs_rank=70,
            rvol=1.1,
            gap_pct=2.5,             # too small
            float_m=40,
            dollar_vol_m=20,
        )
        result = self.engine.score(ctx, catalyst_tags=[])

        self.assertLess(result.components["structure"], 0)
        self.assertLessEqual(result.score, 60)

    # ---------------------------------------------------------
    # 6. Perfect Trend Label Bonus
    # ---------------------------------------------------------
    def test_trend_label_bonus(self):
        ctx = StrategyContext(
            symbol="TRENDBOOST",
            scanner="TREND",
            catalyst_score=50,
            rs_rank=75,
            rvol=1.3,
            trend_label="PERFECT",
            float_m=30,
            dollar_vol_m=40,
        )
        result = self.engine.score(ctx, catalyst_tags=[])

        self.assertGreater(result.components["trend"], 10)
        self.assertGreaterEqual(result.score, 60)

    # ---------------------------------------------------------
    # 7. Catalyst Tag Synergy
    # ---------------------------------------------------------
    def test_catalyst_tag_synergy(self):
        ctx = StrategyContext(
            symbol="TAGGY",
            scanner="EP",
            catalyst_score=50,
            rs_rank=70,
            rvol=1.5,
            gap_pct=8,
            float_m=15,
            dollar_vol_m=30,
        )
        result = self.engine.score(ctx, catalyst_tags=["earnings_recent", "sector_hot"])

        self.assertGreater(result.components["catalyst"], 8)
        self.assertGreaterEqual(result.score, 60)


if __name__ == "__main__":
    unittest.main()