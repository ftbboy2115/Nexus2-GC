import unittest
from unittest.mock import patch, MagicMock

from core.scan_ep import EPScanner
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext
from core.catalyst_engine import CatalystEngine, CatalystContext


class TestEPScanner(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. Basic EP scan with mocked data
    # ---------------------------------------------------------
    @patch.object(CatalystEngine, "score")
    @patch.object(StrategyEngineV2, "score")
    @patch.object(EPScanner, "_get_screener_data")
    @patch.object(EPScanner, "_get_candles")
    def test_basic_ep_scan(
        self,
        mock_candles,
        mock_screener,
        mock_strategy_score,
        mock_catalyst_score,
    ):
        # Mock screener data
        mock_screener.return_value = [
            {"symbol": "EP1", "gap_pct": 12.0, "float_m": 20, "dollar_vol_m": 40}
        ]

        # Mock candles
        mock_candles.return_value = [
            {"open": 10.0, "close": 11.0, "high": 12.0, "low": 9.5}
        ]

        # Mock Catalyst Engine result
        mock_catalyst_score.return_value = MagicMock(
            score=70,
            strength="Strong",
            tags=["earnings_recent"]
        )

        # Mock Strategy Engine result
        mock_strategy_score.return_value = MagicMock(
            score=85,
            conviction="A",
            components={"catalyst": 15, "structure": 12}
        )

        scanner = EPScanner()
        results = scanner.run()

        self.assertEqual(len(results), 1)
        row = results[0]

        # Schema checks
        self.assertIn("Symbol", row)
        self.assertIn("Gap%", row)
        self.assertIn("StratScore", row)
        self.assertIn("StratConviction", row)
        self.assertIn("CatalystScore", row)
        self.assertIn("CatalystStrength", row)
        self.assertIn("CatalystTags", row)

        # Value checks
        self.assertEqual(row["Symbol"], "EP1")
        self.assertEqual(row["Gap%"], 12.0)
        self.assertEqual(row["StratScore"], 85)
        self.assertEqual(row["StratConviction"], "A")
        self.assertEqual(row["CatalystScore"], 70)

    # ---------------------------------------------------------
    # 2. Small gap should be filtered out
    # ---------------------------------------------------------
    @patch.object(EPScanner, "_get_screener_data")
    def test_small_gap_filtered(self, mock_screener):
        mock_screener.return_value = [
            {"symbol": "SMALL", "gap_pct": 2.0, "float_m": 20, "dollar_vol_m": 40}
        ]

        scanner = EPScanner()
        results = scanner.run()

        # Should filter out small gaps
        self.assertEqual(len(results), 0)

    # ---------------------------------------------------------
    # 3. Missing fields should not crash
    # ---------------------------------------------------------
    @patch.object(EPScanner, "_get_screener_data")
    def test_missing_fields(self, mock_screener):
        mock_screener.return_value = [
            {"symbol": "BROKEN"}  # missing gap_pct, float, etc.
        ]

        scanner = EPScanner()
        results = scanner.run()

        # Should skip invalid entries
        self.assertEqual(len(results), 0)

    # ---------------------------------------------------------
    # 4. Strategy Engine receives correct context
    # ---------------------------------------------------------
    @patch.object(StrategyEngineV2, "score")
    @patch.object(CatalystEngine, "score")
    @patch.object(EPScanner, "_get_screener_data")
    @patch.object(EPScanner, "_get_candles")
    def test_strategy_context_fields(
        self,
        mock_candles,
        mock_screener,
        mock_catalyst_score,
        mock_strategy_score,
    ):
        mock_screener.return_value = [
            {"symbol": "CTX", "gap_pct": 15.0, "float_m": 10, "dollar_vol_m": 50}
        ]
        mock_candles.return_value = [{"open": 5, "close": 6, "high": 7, "low": 4}]

        mock_catalyst_score.return_value = MagicMock(
            score=60,
            strength="Neutral",
            tags=[]
        )
        mock_strategy_score.return_value = MagicMock(
            score=70,
            conviction="B",
            components={}
        )

        scanner = EPScanner()
        scanner.run()

        # Ensure StrategyEngine was called with a StrategyContext
        args, kwargs = mock_strategy_score.call_args
        ctx = args[0]
        self.assertIsInstance(ctx, StrategyContext)
        self.assertEqual(ctx.scanner, "EP")
        self.assertEqual(ctx.gap_pct, 15.0)
        self.assertEqual(ctx.float_m, 10)
        self.assertEqual(ctx.dollar_vol_m, 50)


if __name__ == "__main__":
    unittest.main()