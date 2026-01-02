import unittest
from unittest.mock import patch, MagicMock

from core.worker_controller import WorkerController
from core.scan_ep import EPScanner
from core.scan_trend_daily import TrendDailyScanner
from core.scan_htf import HTFScanner
from core.strategy_engine_v2 import StrategyEngineV2
from core.catalyst_engine import CatalystEngine


class TestScannerIntegration(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. All scanners run under WorkerController
    # ---------------------------------------------------------
    @patch.object(EPScanner, "run")
    @patch.object(TrendDailyScanner, "run")
    @patch.object(HTFScanner, "run")
    def test_all_scanners_run(
        self,
        mock_htf_run,
        mock_trend_run,
        mock_ep_run,
    ):
        mock_ep_run.return_value = [{"Symbol": "EP1", "StratScore": 80}]
        mock_trend_run.return_value = [{"Symbol": "TR1", "StratScore": 70}]
        mock_htf_run.return_value = [{"Symbol": "HT1", "StratScore": 60}]

        controller = WorkerController()

        controller.add_worker("EP", lambda: mock_ep_run())
        controller.add_worker("TREND", lambda: mock_trend_run())
        controller.add_worker("HTF", lambda: mock_htf_run())

        controller.run_all()

        # All workers should have completed
        self.assertEqual(len(controller.failures), 0)

    # ---------------------------------------------------------
    # 2. One scanner fails but others still run
    # ---------------------------------------------------------
    @patch.object(EPScanner, "run")
    @patch.object(TrendDailyScanner, "run")
    @patch.object(HTFScanner, "run")
    def test_scanner_failure_isolated(
        self,
        mock_htf_run,
        mock_trend_run,
        mock_ep_run,
    ):
        mock_ep_run.side_effect = ValueError("EP failed")
        mock_trend_run.return_value = [{"Symbol": "TR1"}]
        mock_htf_run.return_value = [{"Symbol": "HT1"}]

        controller = WorkerController()

        controller.add_worker("EP", lambda: mock_ep_run())
        controller.add_worker("TREND", lambda: mock_trend_run())
        controller.add_worker("HTF", lambda: mock_htf_run())

        controller.run_all()

        # EP should fail
        self.assertIn("EP", controller.failures)

        # TREND and HTF should still run
        self.assertNotIn("TREND", controller.failures)
        self.assertNotIn("HTF", controller.failures)

    # ---------------------------------------------------------
    # 3. Strategy Engine v2 + Catalyst Engine v2 invoked
    # ---------------------------------------------------------
    @patch.object(StrategyEngineV2, "score")
    @patch.object(CatalystEngine, "score")
    @patch.object(EPScanner, "run")
    def test_engines_invoked(
        self,
        mock_ep_run,
        mock_catalyst_score,
        mock_strategy_score,
    ):
        # Mock EP scanner to simulate a single entry
        mock_ep_run.return_value = [{"Symbol": "EP1"}]

        # Mock engines
        mock_catalyst_score.return_value = MagicMock(
            score=50, strength="Neutral", tags=[]
        )
        mock_strategy_score.return_value = MagicMock(
            score=70, conviction="B", components={}
        )

        controller = WorkerController()
        controller.add_worker("EP", lambda: mock_ep_run())
        controller.run_all()

        # Engines should have been called at least once
        self.assertTrue(mock_catalyst_score.called)
        self.assertTrue(mock_strategy_score.called)

    # ---------------------------------------------------------
    # 4. No deadlocks with multiple scanners
    # ---------------------------------------------------------
    @patch.object(EPScanner, "run")
    @patch.object(TrendDailyScanner, "run")
    @patch.object(HTFScanner, "run")
    def test_no_deadlocks(
        self,
        mock_htf_run,
        mock_trend_run,
        mock_ep_run,
    ):
        mock_ep_run.return_value = [{"Symbol": "EP1"}]
        mock_trend_run.return_value = [{"Symbol": "TR1"}]
        mock_htf_run.return_value = [{"Symbol": "HT1"}]

        controller = WorkerController()

        controller.add_worker("EP", lambda: mock_ep_run())
        controller.add_worker("TREND", lambda: mock_trend_run())
        controller.add_worker("HTF", lambda: mock_htf_run())

        # Should complete quickly without hanging
        controller.run_all()

        self.assertEqual(len(controller.failures), 0)

    # ---------------------------------------------------------
    # 5. Combined results aggregation (mocked)
    # ---------------------------------------------------------
    @patch.object(EPScanner, "run")
    @patch.object(TrendDailyScanner, "run")
    @patch.object(HTFScanner, "run")
    def test_combined_results(
        self,
        mock_htf_run,
        mock_trend_run,
        mock_ep_run,
    ):
        mock_ep_run.return_value = [{"Symbol": "EP1", "StratScore": 80}]
        mock_trend_run.return_value = [{"Symbol": "TR1", "StratScore": 70}]
        mock_htf_run.return_value = [{"Symbol": "HT1", "StratScore": 60}]

        controller = WorkerController()

        results = []

        controller.add_worker("EP", lambda: results.extend(mock_ep_run()))
        controller.add_worker("TREND", lambda: results.extend(mock_trend_run()))
        controller.add_worker("HTF", lambda: results.extend(mock_htf_run()))

        controller.run_all()

        self.assertEqual(len(results), 3)
        symbols = {r["Symbol"] for r in results}
        self.assertSetEqual(symbols, {"EP1", "TR1", "HT1"})


if __name__ == "__main__":
    unittest.main()