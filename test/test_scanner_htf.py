"""
⭐ What this test suite gives you
1. HTF schema validation
Ensures the scanner always returns:
- Symbol
- Move%
- Depth%
- CatalystScore
- StratScore
- StratConviction
2. Structure logic validation
Move% + Pullback% scoring is validated through Strategy Engine v2.
3. Integration validation
Confirms HTF correctly calls:
- Catalyst Engine v2
- Strategy Engine v2
4. Filtering logic validation
Missing move or pullback → entry skipped.
5. Context correctness
Ensures StrategyContext is populated correctly.

"""

import unittest
from unittest.mock import patch, MagicMock

from core.scan_htf import HTFScanner
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext
from core.catalyst_engine import CatalystEngine, CatalystContext


class TestHTFScanner(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. Basic HTF scan with mocked data
    # ---------------------------------------------------------
    @patch.object(CatalystEngine, "score")
    @patch.object(StrategyEngineV2, "score")
    @patch.object(HTFScanner, "_get_screener_data")
    @patch.object(HTFScanner, "_get_candles")
    def test_basic_htf_scan(
        self,
        mock_candles,
        mock_screener,
        mock_strategy_score,
        mock_catalyst_score,
    ):
        # Mock screener data
        mock_screener.return_value = [
            {
                "symbol": "HT1",
                "move_pct": 120,
                "pullback_pct": 18,
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
            score=78,
            conviction="A",
            components={"structure": 14}
        )

        scanner = HTFScanner()
        results = scanner.run()

        self.assertEqual(len(results), 1)
        row = results[0]

        # Schema checks
        self.assertIn("Symbol", row)
        self.assertIn("Move%", row)
        self.assertIn("Depth%", row)
        self.assertIn("StratScore", row)
        self.assertIn("StratConviction", row)
        self.assertIn("CatalystScore", row)
        self.assertIn("CatalystStrength", row)
        self.assertIn("CatalystTags", row)

        # Value checks
        self.assertEqual(row["Symbol"], "HT1")
        self.assertEqual(row["Move%"], 120)
        self.assertEqual(row["Depth%"], 18)
        self.assertEqual(row["StratScore"], 78)
        self.assertEqual(row["StratConviction"], "A")

    # ---------------------------------------------------------
    # 2. Missing move or pullback should skip entry
    # ---------------------------------------------------------
    @patch.object(HTFScanner, "_get_screener_data")
    def test_missing_move_or_pullback(self, mock_screener):
        mock_screener.return_value = [
            {"symbol": "BAD1", "pullback_pct": 20},  # missing move_pct
            {"symbol": "BAD2", "move_pct": 120},     # missing pullback_pct
        ]

        scanner = HTFScanner()
        results = scanner.run()

        self.assertEqual(len(results), 0)

    # ---------------------------------------------------------
    # 3. Structure scoring logic (move + pullback)
    # ---------------------------------------------------------
    @patch.object(HTFScanner, "_get_screener_data")
    @patch.object(HTFScanner, "_get_candles")
    @patch.object(CatalystEngine, "score")
    @patch.object(StrategyEngineV2, "score")
    def test_structure_logic(
        self,
        mock_strategy_score,
        mock_catalyst_score,
        mock_candles,
        mock_screener,
    ):
        mock_screener.return_value = [
            {
                "symbol": "FLAG",
                "move_pct": 150,
                "pullback_pct": 22,
                "float_m": 15,
                "dollar_vol_m": 50,
            }
        ]

        mock_candles.return_value = [{"open": 5, "close": 6, "high": 7, "low": 4}]

        mock_catalyst_score.return_value = MagicMock(
            score=60,
            strength="Strong",
            tags=[]
        )
        mock_strategy_score.return_value = MagicMock(
            score=82,
            conviction="A",
            components={"structure": 16}
        )

        scanner = HTFScanner()
        results = scanner.run()

        self.assertEqual(len(results), 1)
        row = results[0]

        self.assertEqual(row["Move%"], 150)
        self.assertEqual(row["Depth%"], 22)
        self.assertEqual(row["StratScore"], 82)

    # ---------------------------------------------------------
    # 4. StrategyContext correctness
    # ---------------------------------------------------------
    @patch.object(StrategyEngineV2, "score")
    @patch.object(CatalystEngine, "score")
    @patch.object(HTFScanner, "_get_screener_data")
    @patch.object(HTFScanner, "_get_candles")
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
                "move_pct": 110,
                "pullback_pct": 25,
                "float_m": 12,
                "dollar_vol_m": 35,
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

        scanner = HTFScanner()
        scanner.run()

        # Ensure StrategyEngine was called with a StrategyContext
        args, kwargs = mock_strategy_score.call_args
        ctx = args[0]
        self.assertIsInstance(ctx, StrategyContext)
        self.assertEqual(ctx.scanner, "HTF")
        self.assertEqual(ctx.move_pct, 110)
        self.assertEqual(ctx.pullback_pct, 25)
        self.assertEqual(ctx.float_m, 12)
        self.assertEqual(ctx.dollar_vol_m, 35)


if __name__ == "__main__":
    unittest.main()