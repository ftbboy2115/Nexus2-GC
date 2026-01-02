"""
⭐ What this test suite gives you
1. Trend Daily schema validation
Ensures the scanner always returns:
- Symbol
- RS_Score
- RVOL
- TrendLabel
- CatalystScore
- StratScore
- StratConviction
2. Integration validation
Confirms Trend Daily correctly calls:
- Catalyst Engine v2
- Strategy Engine v2
3. Trend label logic validation
You now have a test that forces a PERFECT trend label and checks it.
4. Filtering logic validation
Missing RS or RVOL → entry skipped.
5. Context correctness
Ensures StrategyContext is populated correctly.

"""


import unittest
from unittest.mock import patch, MagicMock

from core.scan_trend_daily import TrendDailyScanner
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext
from core.catalyst_engine import CatalystEngine, CatalystContext


class TestTrendDailyScanner(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. Basic Trend Daily scan with mocked data
    # ---------------------------------------------------------
    @patch.object(CatalystEngine, "score")
    @patch.object(StrategyEngineV2, "score")
    @patch.object(TrendDailyScanner, "_get_screener_data")
    @patch.object(TrendDailyScanner, "_get_candles")
    def test_basic_trend_scan(
        self,
        mock_candles,
        mock_screener,
        mock_strategy_score,
        mock_catalyst_score,
    ):
        # Mock screener data
        mock_screener.return_value = [
            {
                "symbol": "TR1",
                "rs_rank": 85,
                "rvol": 1.4,
                "float_m": 25,
                "dollar_vol_m": 60,
            }
        ]

        # Mock candles
        mock_candles.return_value = [
            {"open": 10, "close": 11, "high": 12, "low": 9.5}
        ]

        # Mock Catalyst Engine result
        mock_catalyst_score.return_value = MagicMock(
            score=55,
            strength="Neutral",
            tags=["sector_hot"]
        )

        # Mock Strategy Engine result
        mock_strategy_score.return_value = MagicMock(
            score=72,
            conviction="B",
            components={"trend": 12}
        )

        scanner = TrendDailyScanner()
        results = scanner.run()

        self.assertEqual(len(results), 1)
        row = results[0]

        # Schema checks
        self.assertIn("Symbol", row)
        self.assertIn("RS_Score", row)
        self.assertIn("RVOL", row)
        self.assertIn("TrendLabel", row)
        self.assertIn("StratScore", row)
        self.assertIn("StratConviction", row)
        self.assertIn("CatalystScore", row)
        self.assertIn("CatalystStrength", row)
        self.assertIn("CatalystTags", row)

        # Value checks
        self.assertEqual(row["Symbol"], "TR1")
        self.assertEqual(row["StratScore"], 72)
        self.assertEqual(row["StratConviction"], "B")
        self.assertEqual(row["CatalystScore"], 55)

    # ---------------------------------------------------------
    # 2. Missing RS or RVOL should skip entry
    # ---------------------------------------------------------
    @patch.object(TrendDailyScanner, "_get_screener_data")
    def test_missing_rs_or_rvol(self, mock_screener):
        mock_screener.return_value = [
            {"symbol": "BAD1", "rvol": 1.2},  # missing rs_rank
            {"symbol": "BAD2", "rs_rank": 80},  # missing rvol
        ]

        scanner = TrendDailyScanner()
        results = scanner.run()

        self.assertEqual(len(results), 0)

    # ---------------------------------------------------------
    # 3. Trend label classification
    # ---------------------------------------------------------
    @patch.object(TrendDailyScanner, "_get_screener_data")
    @patch.object(TrendDailyScanner, "_get_candles")
    @patch.object(CatalystEngine, "score")
    @patch.object(StrategyEngineV2, "score")
    def test_trend_label_logic(
        self,
        mock_strategy_score,
        mock_catalyst_score,
        mock_candles,
        mock_screener,
    ):
        mock_screener.return_value = [
            {
                "symbol": "TRENDX",
                "rs_rank": 90,
                "rvol": 1.5,
                "float_m": 20,
                "dollar_vol_m": 50,
            }
        ]

        # Mock candles to force a PERFECT trend label
        mock_candles.return_value = [
            {"open": 10, "close": 11, "high": 12, "low": 10.5}
        ]

        mock_catalyst_score.return_value = MagicMock(
            score=60,
            strength="Strong",
            tags=[]
        )
        mock_strategy_score.return_value = MagicMock(
            score=80,
            conviction="A",
            components={"trend": 18}
        )

        scanner = TrendDailyScanner()
        results = scanner.run()

        self.assertEqual(len(results), 1)
        row = results[0]

        self.assertEqual(row["TrendLabel"], "PERFECT")
        self.assertEqual(row["StratScore"], 80)

    # ---------------------------------------------------------
    # 4. StrategyContext correctness
    # ---------------------------------------------------------
    @patch.object(StrategyEngineV2, "score")
    @patch.object(CatalystEngine, "score")
    @patch.object(TrendDailyScanner, "_get_screener_data")
    @patch.object(TrendDailyScanner, "_get_candles")
    def test_strategy_context_fields(
        self,
        mock_candles,
        mock_screener,
        mock_catalyst_score,
        mock_strategy_score,
    ):
        mock_screener.return_value = [
            {
                "symbol": "CTX",
                "rs_rank": 88,
                "rvol": 1.3,
                "float_m": 15,
                "dollar_vol_m": 40,
            }
        ]
        mock_candles.return_value = [{"open": 5, "close": 6, "high": 7, "low": 4}]

        mock_catalyst_score.return_value = MagicMock(
            score=50,
            strength="Neutral",
            tags=[]
        )
        mock_strategy_score.return_value = MagicMock(
            score=65,
            conviction="B",
            components={}
        )

        scanner = TrendDailyScanner()
        scanner.run()

        # Ensure StrategyEngine was called with a StrategyContext
        args, kwargs = mock_strategy_score.call_args
        ctx = args[0]
        self.assertIsInstance(ctx, StrategyContext)
        self.assertEqual(ctx.scanner, "TREND")
        self.assertEqual(ctx.rs_rank, 88)
        self.assertEqual(ctx.rvol, 1.3)
        self.assertEqual(ctx.float_m, 15)
        self.assertEqual(ctx.dollar_vol_m, 40)


if __name__ == "__main__":
    unittest.main()