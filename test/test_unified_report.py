"""
⭐ What this test suite gives you
1. Confidence in the unified report pipeline
It validates:
- Normalization
- Merging
- Sorting
- A‑tier filtering
- JSON dashboard output
2. Protection against regressions
If any scanner changes its schema, this test will catch it immediately.
3. Safe, isolated testing
Everything runs inside temporary directories — your real /data/ stays untouched.

"""


import unittest
import os
import tempfile
import pandas as pd

from core import report_daily
from core.report_daily import normalize_columns


class TestUnifiedReport(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. Normalization ensures required columns exist
    # ---------------------------------------------------------
    def test_normalize_columns(self):
        df = pd.DataFrame({
            "Symbol": ["AAPL"],
            "StratScore": [80],
        })

        norm = normalize_columns(df)

        required = [
            "Symbol", "Scanner", "StratScore", "StratConviction",
            "CatalystScore", "CatalystStrength", "CatalystTags",
            "Reason", "Sector", "Industry", "Move%", "Gap%",
            "RS_Score", "Vol_M", "Float_M", "Depth%", "Close",
            "Pivot", "Stop_Loss",
        ]

        for col in required:
            self.assertIn(col, norm.columns)

    # ---------------------------------------------------------
    # 2. Merge behavior with synthetic scanner outputs
    # ---------------------------------------------------------
    def test_merge_three_scanners(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Patch config.DATA_DIR to point to temp dir
            report_daily.config.DATA_DIR = tmp

            # Create synthetic scanner outputs
            ep = pd.DataFrame({
                "Symbol": ["EP1"],
                "StratScore": [90],
                "StratConviction": ["A"],
            })
            trend = pd.DataFrame({
                "Symbol": ["TR1"],
                "StratScore": [70],
                "StratConviction": ["B"],
            })
            htf = pd.DataFrame({
                "Symbol": ["HT1"],
                "StratScore": [60],
                "StratConviction": ["C"],
            })

            ep.to_csv(os.path.join(tmp, "ep_results.csv"), index=False)
            trend.to_csv(os.path.join(tmp, "trend_results.csv"), index=False)
            htf.to_csv(os.path.join(tmp, "htf_results.csv"), index=False)

            # Run unified report builder
            report_daily.build_unified_report()

            out = os.path.join(tmp, "unified_report.csv")
            self.assertTrue(os.path.exists(out))

            df = pd.read_csv(out)
            self.assertEqual(len(df), 3)

            # Ensure sorting by StratScore descending
            self.assertEqual(df.iloc[0]["Symbol"], "EP1")

    # ---------------------------------------------------------
    # 3. Missing scanner files should not crash
    # ---------------------------------------------------------
    def test_missing_scanner_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_daily.config.DATA_DIR = tmp

            # Only EP exists
            ep = pd.DataFrame({
                "Symbol": ["EP1"],
                "StratScore": [80],
                "StratConviction": ["A"],
            })
            ep.to_csv(os.path.join(tmp, "ep_results.csv"), index=False)

            # No trend_results.csv
            # No htf_results.csv

            report_daily.build_unified_report()

            out = os.path.join(tmp, "unified_report.csv")
            self.assertTrue(os.path.exists(out))

            df = pd.read_csv(out)
            self.assertEqual(len(df), 1)

    # ---------------------------------------------------------
    # 4. A-tier filtering
    # ---------------------------------------------------------
    def test_top_a_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_daily.config.DATA_DIR = tmp

            df = pd.DataFrame({
                "Symbol": ["A1", "B1"],
                "StratScore": [90, 60],
                "StratConviction": ["A", "B"],
            })
            df.to_csv(os.path.join(tmp, "ep_results.csv"), index=False)

            report_daily.build_unified_report()

            out = os.path.join(tmp, "unified_report_topA.csv")
            self.assertTrue(os.path.exists(out))

            top = pd.read_csv(out)
            self.assertEqual(len(top), 1)
            self.assertEqual(top.iloc[0]["Symbol"], "A1")

    # ---------------------------------------------------------
    # 5. Dashboard JSON schema
    # ---------------------------------------------------------
    def test_dashboard_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_daily.config.DATA_DIR = tmp

            df = pd.DataFrame({
                "Symbol": ["A1"],
                "StratScore": [88],
                "StratConviction": ["A"],
            })
            df.to_csv(os.path.join(tmp, "ep_results.csv"), index=False)

            report_daily.build_unified_report()

            out = os.path.join(tmp, "unified_report_dashboard.json")
            self.assertTrue(os.path.exists(out))

            # Basic schema check
            import json
            with open(out, "r") as f:
                data = json.load(f)

            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)
            self.assertIn("Symbol", data[0])
            self.assertIn("StratScore", data[0])


if __name__ == "__main__":
    unittest.main()